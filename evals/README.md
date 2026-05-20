# Evals

First-class eval suite built on [Inspect AI](https://inspect.aisi.org.uk/). Lands in U7.

## Layout (after U7 lands)

```
evals/
├── questions/
│   ├── factual.jsonl
│   ├── multi_tool.jsonl
│   ├── synthesis.jsonl          # the architectural differentiator
│   ├── edge_cases.jsonl
│   ├── refusals.jsonl
│   └── security_redteam.jsonl   # public-deploy hardening
├── scorers/
│   ├── tool_call_correctness.py
│   ├── retrieval_quality.py
│   ├── llm_as_judge.py          # uses meta-llama/llama-3.3-70b-instruct (paid)
│   └── security_redteam.py      # deterministic — leak/drift/introspection detectors
├── rubrics/
│   └── answer_quality_rubric.md
├── results/
│   └── latest.json              # auto-committed by CI on main pushes
├── budget.json                  # month-to-date OpenRouter spend tracking
├── run_eval.py                  # Inspect AI Task definition + runner
└── tests/test_scorers.py        # meta-tests for scoring logic
```

## Running locally

```bash
cd backend
uv run --extra eval inspect eval ../evals/run_eval.py --model openrouter/openai/gpt-oss-120b
```

Requires `OPENROUTER_API_KEY` in env. Full suite runs in ~5-10 min and costs <$0.10 with judge caching.
