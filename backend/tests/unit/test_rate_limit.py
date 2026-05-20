"""Tests for the rate limiter and daily budget."""

from __future__ import annotations

import pytest
from aviation_copilot.api.rate_limit import DailyBudget, RateLimiter, TokenBucket


class TestTokenBucket:
    def test_consumes_when_tokens_available(self) -> None:
        b = TokenBucket(rate=1.0, burst=5.0, tokens=5.0, last_refill=0.0)
        for _ in range(5):
            assert b.take(now=0.0)
        # 6th call would exhaust the bucket.
        assert not b.take(now=0.0)

    def test_refills_over_time(self) -> None:
        b = TokenBucket(rate=2.0, burst=5.0, tokens=0.0, last_refill=0.0)
        # 1 second elapsed -> 2 tokens added.
        assert b.take(cost=1.0, now=1.0)
        # Now 1 token, second call costs 1 -> ok.
        assert b.take(cost=1.0, now=1.0)
        # Empty now.
        assert not b.take(cost=1.0, now=1.0)

    def test_caps_at_burst(self) -> None:
        b = TokenBucket(rate=10.0, burst=3.0, tokens=0.0, last_refill=0.0)
        # 10s elapsed would give 100 tokens, but burst caps at 3.
        assert b.take(cost=3.0, now=10.0)
        assert not b.take(cost=1.0, now=10.0)

    def test_retry_after_returns_deficit_over_rate(self) -> None:
        b = TokenBucket(rate=1.0, burst=1.0, tokens=0.0, last_refill=0.0)
        retry = b.retry_after_seconds(cost=1.0)
        assert retry == pytest.approx(1.0)


class TestRateLimiter:
    def test_first_request_allowed(self) -> None:
        rl = RateLimiter(rate_per_second=1.0, burst=5.0)
        allowed, retry = rl.check("1.1.1.1")
        assert allowed
        assert retry == 0.0

    def test_burst_then_throttle(self) -> None:
        rl = RateLimiter(rate_per_second=0.5, burst=3.0)
        for _ in range(3):
            assert rl.check("1.1.1.1")[0]
        # 4th hits the bucket bottom; allowed depends on refill since first call.
        # We can't be sure within a millisecond, but a 5th call definitely throttles.
        # Consume any leftover then verify throttle.
        rl.check("1.1.1.1")
        allowed, retry = rl.check("1.1.1.1")
        assert not allowed
        assert retry > 0

    def test_different_ips_have_separate_buckets(self) -> None:
        rl = RateLimiter(rate_per_second=0.1, burst=1.0)
        a = rl.check("1.1.1.1")
        b = rl.check("2.2.2.2")
        assert a[0] and b[0]
        # Both exhausted now, both throttled.
        assert not rl.check("1.1.1.1")[0]
        assert not rl.check("2.2.2.2")[0]


class TestDailyBudget:
    def test_constructor_rejects_zero(self) -> None:
        with pytest.raises(ValueError):
            DailyBudget(max_tokens_per_day=0)

    def test_allow_under_cap(self) -> None:
        db = DailyBudget(max_tokens_per_day=1000)
        assert db.allow(requested_tokens=100)

    def test_blocks_when_over_cap(self) -> None:
        db = DailyBudget(max_tokens_per_day=100)
        db.add(80)
        assert db.allow(requested_tokens=15)
        db.add(15)
        # 95 used; another 10 would push to 105 > cap.
        assert not db.allow(requested_tokens=10)

    def test_reset_clears_used(self) -> None:
        db = DailyBudget(max_tokens_per_day=100)
        db.add(50)
        db.reset()
        assert db.used_today == 0
        assert db.allow(requested_tokens=99)
