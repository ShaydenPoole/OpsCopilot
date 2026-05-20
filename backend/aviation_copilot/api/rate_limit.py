"""In-memory rate limit and daily budget guard.

Two layers:

1. **Per-IP token bucket** — bounded request rate so one client can't
   monopolize the service.
2. **Global daily token budget** — bounded total OpenRouter spend so an
   abuse spike can't blow the $25/mo active-development cap.

Both are in-memory; on container restart counters reset. Production
deploys behind Modal can persist via a small Modal Dict if cross-restart
durability ever matters (it doesn't at portfolio scale).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class TokenBucket:
    """Standard token bucket.

    ``rate`` tokens are added per second up to ``burst`` capacity. ``take``
    returns True when at least ``cost`` tokens are available and consumed.
    """

    rate: float
    """Tokens added per second."""
    burst: float
    """Maximum tokens that can accumulate."""
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def take(self, cost: float = 1.0, *, now: float | None = None) -> bool:
        t = now if now is not None else time.monotonic()
        elapsed = t - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = t
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after_seconds(self, cost: float = 1.0) -> float:
        deficit = max(0.0, cost - self.tokens)
        return deficit / self.rate if self.rate > 0 else 0.0


class RateLimiter:
    """Per-IP token bucket, with bucket parameters fixed at construction."""

    DEFAULT_RATE_PER_SECOND = 0.5  # 30 requests / min
    DEFAULT_BURST = 10.0

    def __init__(
        self,
        *,
        rate_per_second: float = DEFAULT_RATE_PER_SECOND,
        burst: float = DEFAULT_BURST,
    ) -> None:
        self._rate = rate_per_second
        self._burst = burst
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, ip: str) -> tuple[bool, float]:
        """Try to consume one token for ``ip``.

        Returns ``(allowed, retry_after_seconds)``. When ``allowed`` is
        False the caller should respond 429 with the suggested Retry-After.
        """
        bucket = self._buckets.get(ip)
        if bucket is None:
            bucket = TokenBucket(rate=self._rate, burst=self._burst, tokens=self._burst)
            self._buckets[ip] = bucket
        if bucket.take():
            return True, 0.0
        return False, bucket.retry_after_seconds()

    def reset(self) -> None:
        self._buckets.clear()


class DailyBudget:
    """Tracks an integer token count against a per-day cap.

    Resets at UTC midnight. ``allow`` returns False once the day's cap is
    reached; the API returns 429 with a cost-guard message.
    """

    def __init__(self, *, max_tokens_per_day: int) -> None:
        if max_tokens_per_day <= 0:
            raise ValueError("max_tokens_per_day must be positive.")
        self._cap = max_tokens_per_day
        self._used = 0
        self._day = self._today()

    def _today(self) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def _rollover_if_new_day(self) -> None:
        today = self._today()
        if today != self._day:
            self._used = 0
            self._day = today

    def allow(self, requested_tokens: int = 0) -> bool:
        """Return True iff used + requested would still be under cap."""
        self._rollover_if_new_day()
        return (self._used + requested_tokens) <= self._cap

    def add(self, used_tokens: int) -> None:
        """Record usage. Caller must check :meth:`allow` first."""
        self._rollover_if_new_day()
        self._used += max(0, used_tokens)

    @property
    def used_today(self) -> int:
        self._rollover_if_new_day()
        return self._used

    @property
    def cap(self) -> int:
        return self._cap

    def reset(self) -> None:
        self._used = 0
        self._day = self._today()
