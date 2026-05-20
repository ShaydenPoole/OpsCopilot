"""FastAPI service surface for the agent.

- :mod:`app`         : FastAPI instance + lifespan + CORS
- :mod:`routes`      : ``/query``, ``/trace/{id}``, ``/healthz``, ``/version``
- :mod:`rate_limit`  : per-IP token bucket + daily token budget
- :mod:`models`      : request / SSE envelope / response Pydantic models
"""

from aviation_copilot.api.app import create_app

__all__ = ["create_app"]
