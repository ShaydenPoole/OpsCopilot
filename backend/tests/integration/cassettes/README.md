# Integration test cassettes

A "cassette" here is a **scripted Pydantic-AI `FunctionModel` conversation** —
a small function that, given the message history so far, returns the next
`ModelResponse` (a tool call, then eventually a final answer).

This is the project's deliberate implementation of the plan's
"recorded-LLM-response cassettes / custom Pydantic-AI test recorder":

- **Deterministic** — the same script always produces the same run.
- **Free & offline** — no OpenRouter calls, no API key, no network.
- **Committed** — the script lives in the test file, reviewable in the diff.
- **No re-record step** — unlike VCR-style HTTP recordings, a scripted model
  never drifts against a live API, so there is no `record_cassettes.py` to
  run. To change a scenario you edit the script directly.

Real LLM behaviour (answer quality, the no-fabrication invariant, tool-choice
accuracy) is verified separately by the Inspect AI eval suite in `evals/`,
which runs against a real model. The integration tests here verify the
**plumbing** — that tool calls, tool errors, traces, and the SSE stream are
wired together correctly.

The scripts currently live inline in `test_agent_end_to_end.py`. If they grow,
extract them into modules in this directory.
