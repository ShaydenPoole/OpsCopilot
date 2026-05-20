"""End-to-end integration tests for the agent service (U10).

These exercise the full stack — FastAPI route → agent loop → real tool code →
structured trace → SSE envelope — with deterministic, offline stand-ins for
the two non-deterministic dependencies:

- the LLM, replaced by a scripted Pydantic-AI ``FunctionModel`` (see
  ``cassettes/README.md`` for why scripted models are this project's
  "recorded-response cassettes");
- upstream HTTP APIs, replaced by ``respx`` mocks.

So they run free, fast, and reproducibly in CI.
"""
