"""Question-bank loader.

Reads every JSONL file under ``evals/questions/`` and converts each entry
into a typed :class:`EvalQuestion` plus an Inspect AI ``Sample``. The
question schema is the contract between the eval framework and the
question bank — kept here so adding new categories is a JSONL edit, not
a code change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

QuestionCategory = Literal[
    "factual", "multi_tool", "synthesis", "edge_cases", "refusals", "security_redteam"
]


class EvalQuestion(BaseModel):
    """One question + grading metadata.

    Lives in JSONL one-per-line under ``evals/questions/<category>.jsonl``.
    """

    id: str
    category: QuestionCategory
    question: str
    expected_tools: list[str] = Field(default_factory=list)
    """Tools that SHOULD be called (set intersection / order tolerance up to scorer)."""
    expected_retrieval_chunk_ids: list[str] = Field(default_factory=list)
    """For RAG-flavored questions, labeled correct chunks (used by retrieval_quality)."""
    expected_refusal: bool = False
    """When True, agent should decline and steer back to aviation."""
    expected_no_fabrication: bool = False
    """When True (e.g. AE2-style), agent must acknowledge missing data without invention."""
    forced_tool_failures: list[str] = Field(default_factory=list)
    """Tools to forcibly fail during this eval run, to exercise error handling."""
    rubric_focus: str | None = None
    """Optional one-line note steering the judge prompt (e.g. 'reconciles conflicting tools')."""
    ae_id: str | None = None
    """Optional origin Acceptance Example link (e.g. 'AE2'). Surfaces in results JSON."""


QUESTIONS_DIR = Path(__file__).resolve().parent / "questions"


def load_question_bank(directory: Path | None = None) -> list[EvalQuestion]:
    """Read every ``*.jsonl`` under ``directory`` (or default) into EvalQuestion list.

    Lines starting with ``#`` and blank lines are skipped. Each remaining
    line must be a JSON object matching :class:`EvalQuestion` (the
    ``category`` field is inferred from the filename when omitted).
    """
    base = directory or QUESTIONS_DIR
    if not base.exists():
        raise FileNotFoundError(f"Questions directory not found: {base}")
    questions: list[EvalQuestion] = []
    for path in sorted(base.glob("*.jsonl")):
        category = path.stem
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            data = json.loads(line)
            data.setdefault("category", category)
            questions.append(EvalQuestion.model_validate(data))
    return questions
