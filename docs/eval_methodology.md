# Eval methodology

How Aviation Ops Copilot is measured. The eval suite is a first-class part of
the project, not an afterthought — it is the evidence that the agent works, and
it runs in CI on every push to `main`.

Source: [`evals/`](../evals/). How to run it locally: [`evals/README.md`](../evals/README.md).

## Why an eval suite at all

"It looked good when I tried it" is not evidence. An LLM agent has too many
failure modes — wrong tool, fabricated data, dropped citation, over-eager
refusal, prompt-injection — to verify by hand. The suite turns each of those
into a measured, versioned, regression-tested property.

It is built on [Inspect AI](https://inspect.aisi.org.uk) — a `Task` (the
question bank) run through a `Solver` (the agent) and graded by `Scorers`. The
solver wraps the **same `run_with_trace`** the production API uses, so eval
behaviour and deploy behaviour are identical by construction.

## The question bank

~57 questions, versioned as JSONL, across six categories:

| File | Probes |
|------|--------|
| `factual.jsonl` | single-tool factual lookups |
| `multi_tool.jsonl` | questions needing 2+ tools |
| `synthesis.jsonl` | reconciling signals across tools that can disagree |
| `edge_cases.jsonl` | empty results, stale data, forced tool failures |
| `refusals.jsonl` | out-of-scope / speculative questions that should be declined |
| `security_redteam.jsonl` | prompt-injection, system-prompt-leak, persona-drift |

Each question carries structured expectations — `expected_tools`,
`expected_retrieval_chunk_ids`, `expected_refusal`, `expected_no_fabrication`,
`forced_tool_failures` — so scorers grade against intent, not a fixed string.

**`synthesis.jsonl` is the differentiator.** These questions deliberately put
tool signals in tension (a live METAR against a 30-day historical pattern, for
instance). The judge rubric scores whether the agent *acknowledged* the
multiple sources, *reconciled* them rather than picking one, and cited per-tool
provenance. This is what separates the agent from a retrieve-and-stop pipeline.

## The four scorers

A question is graded by every scorer that applies to it.

1. **`tool_call_correctness`** — rule-based. Did the trace contain the
   `expected_tools`? Set intersection / difference; open-ended questions with no
   `expected_tools` are skipped, not failed.

2. **`retrieval_quality`** — for questions with labeled chunks, computes
   recall@k and MRR over the `corpus_search` calls observed in the trace.

3. **`llm_as_judge`** — prompts the judge model with
   `{question, agent_answer, rubric}` for a scored verdict on faithfulness,
   completeness, citation discipline, and refusal-correctness. The rubric is
   published as a contract: [`evals/rubrics/answer_quality_rubric.md`](../evals/rubrics/answer_quality_rubric.md).

4. **`security_redteam`** — **deterministic, not LLM-judged.** It checks the
   response for known system-prompt substrings (leak detector), engagement with
   the off-topic request (persona-drift detector), and disclosure of internal
   tool schemas (introspection-leak detector). A passing response declines and
   steers back to aviation. Hardening is *evaluated*, not asserted.

### Why a different-family judge

The judge is `meta-llama/llama-3.3-70b-instruct`; the agent is
`openai/gpt-oss-120b`. A judge sharing the agent's lineage tends to grade its
own family's style kindly. Different lineages reduce that bias. The judge runs
on the paid tier so a free-tier daily cap cannot rate-limit the suite out
mid-run.

A `(question_id, answer_hash)` cache short-circuits the judge on identical
reruns, so iterating on non-agent code re-spends nothing on judging.

## CI integration

| Workflow | Trigger | Scope |
|----------|---------|-------|
| `eval-smoke` | pull request (agent-touching paths) | ~12-question subset, posted as a PR comment |
| `eval-full` | push to `main` | full suite; commits `evals/results/latest.json` |

`eval-full` regenerates the README's eval-results SVG from `latest.json`, so the
badge is always current. Both workflows are gated by a **budget guard** that
reads `evals/budget.json` and refuses to run once the monthly cap is reached —
LLM evals cost money, and a runaway CI loop should not.

Fork PRs cannot read repo secrets (the workflows use `pull_request`, never
`pull_request_target`), so they skip evals gracefully rather than failing.

## Headline metrics and targets

`evals/results/latest.json` carries the headline numbers; the targets from the
project plan:

| Metric | Target |
|--------|--------|
| `tool_call_accuracy` | ≥ 0.85 |
| `retrieval_recall_at_5` | ≥ 0.75 |
| `judge_score_mean` | ≥ 0.75 (5-point rubric) |

Metrics are reported as a mean over multiple runs to dampen LLM
non-determinism; the agent itself runs at `temperature=0`.

## What the suite does and does not catch

It catches: wrong-tool selection, missing citations, fabrication on tool
failure, over- and under-refusal, retrieval regressions, and the scored
security attacks — on every push.

It does not catch: failure modes not represented in the bank. The bank is
versioned precisely so that when a new failure is found in the wild, it becomes
a permanent question and a permanent regression test. The
[`evals/tests/`](../evals/tests/) meta-tests guard the scoring logic itself, so
a bug in a scorer cannot quietly pass a bad answer.
