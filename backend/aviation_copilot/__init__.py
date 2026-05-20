"""Aviation Ops Copilot — tool-using LLM agent for aviation operations.

Implementation lives in:
- ``agent/``           — Pydantic-AI orchestration (U4)
- ``tools/``           — flight_data, weather, notam, corpus_search (U5)
- ``corpus/``          — chunking, embedding, LanceDB index (U3)
- ``data/``            — DuckDB client and schema (U2)
- ``api/``             — FastAPI service (U6)
- ``observability/``   — Langfuse integration (U8)
"""

__version__ = "0.1.0"
