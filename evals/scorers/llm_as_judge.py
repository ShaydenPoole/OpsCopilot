"""LLM-as-judge scorer using Llama 3.3 70B via OpenRouter.

Reads the rubric from ``evals/rubrics/answer_quality_rubric.md``, prompts
the judge with ``{question, agent_answer, rubric, question_metadata}``,
and expects strict JSON back.

Cache layer: judge results are cached by ``(question_id, sha256(answer))``
in a small JSON file so identical reruns (e.g., CI without code changes)
don't re-spend on the judge model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
JUDGE_MODEL = "meta-llama/llama-3.3-70b-instruct"

RUBRIC_PATH = (
    Path(__file__).resolve().parents[1] / "rubrics" / "answer_quality_rubric.md"
)
CACHE_PATH = Path(__file__).resolve().parents[1] / ".judge_cache.json"


# ----------------------------------------------------------------------
# Cache
# ----------------------------------------------------------------------


def _cache_load() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _cache_save(cache: dict[str, dict[str, Any]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _cache_key(question_id: str, answer: str) -> str:
    digest = hashlib.sha256(answer.encode("utf-8")).hexdigest()[:16]
    return f"{question_id}::{digest}"


# ----------------------------------------------------------------------
# Judge prompt + parsing
# ----------------------------------------------------------------------


JUDGE_SYSTEM = """You are an evaluator scoring an aviation operations LLM agent's answer against the published rubric. \
Return ONLY a strict JSON object matching the schema in the rubric. Do not include code fences, prose, or apologies.\
"""


def build_judge_prompt(
    *,
    question: str,
    answer: str,
    rubric: str,
    question_metadata: dict[str, Any],
) -> str:
    return (
        "RUBRIC (the contract you grade against):\n"
        "---\n"
        f"{rubric}\n"
        "---\n\n"
        f"QUESTION METADATA: {json.dumps(question_metadata, default=str)}\n\n"
        f"QUESTION: {question}\n\n"
        f"AGENT ANSWER:\n---\n{answer}\n---\n\n"
        "Produce the JSON score now."
    )


def parse_judge_response(text: str) -> dict[str, Any]:
    """Extract the JSON object from the judge's response. Tolerant of
    surrounding prose / code fences / leading 'Here is the score:' chatter.
    """
    # Try direct parse first.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # Find the first {...} block.
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"Judge response did not contain JSON: {text[:120]!r}")
    return json.loads(match.group(0))


# ----------------------------------------------------------------------
# OpenRouter call
# ----------------------------------------------------------------------


async def call_judge(prompt: str, *, api_key: str, model: str = JUDGE_MODEL) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{OPENROUTER_BASE}/chat/completions", headers=headers, json=payload
        )
        resp.raise_for_status()
        data = resp.json()
    return str(data["choices"][0]["message"]["content"])


def load_rubric() -> str:
    if not RUBRIC_PATH.exists():
        raise FileNotFoundError(f"Rubric not found at {RUBRIC_PATH}")
    return RUBRIC_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# Inspect AI scorer
# ----------------------------------------------------------------------


def llm_as_judge_scorer():  # noqa: ANN201
    from inspect_ai.scorer import NOANSWER, Score, Target, mean, scorer
    from inspect_ai.solver import TaskState

    @scorer(metrics=[mean()])
    def _scorer():  # noqa: ANN202
        async def score(state: TaskState, target: Target) -> Score:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                return Score(
                    value=NOANSWER,
                    explanation="OPENROUTER_API_KEY not set — judge skipped.",
                )
            metadata = state.metadata or {}
            qid = str(metadata.get("question_id", "unknown"))
            answer = state.output.completion

            cache = _cache_load()
            key = _cache_key(qid, answer)
            cached = cache.get(key)
            if cached is not None:
                return Score(
                    value=float(cached.get("score", 0.0)),
                    explanation=f"[cached] {cached.get('reasoning', '')}",
                    metadata=cached,
                )

            prompt = build_judge_prompt(
                question=metadata.get("question", ""),
                answer=answer,
                rubric=load_rubric(),
                question_metadata={
                    "category": metadata.get("category"),
                    "expected_refusal": metadata.get("expected_refusal"),
                    "expected_no_fabrication": metadata.get("expected_no_fabrication"),
                    "rubric_focus": metadata.get("rubric_focus"),
                },
            )
            try:
                raw = await call_judge(prompt, api_key=api_key)
                parsed = parse_judge_response(raw)
            except (httpx.HTTPError, ValueError) as exc:
                return Score(
                    value=NOANSWER,
                    explanation=f"Judge call failed: {exc!r}",
                )
            score_val = float(parsed.get("score", 0.0))
            cache[key] = parsed
            _cache_save(cache)
            return Score(
                value=score_val,
                explanation=str(parsed.get("reasoning", "")),
                metadata=parsed,
            )

        return score

    return _scorer()
