from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.security.rate_limiter import InMemoryRateLimiter, RateLimitExceeded


def _client_ip(request: Request) -> str:
    """Deliberately `request.client.host`, never X-Forwarded-For/X-Real-IP
    — same reasoning as app/api/routes/auth.py's `_client_ip`: this app
    has no reverse proxy in front of it whose trusted-hop count is
    defined, so trusting a client-settable header would let any visitor
    simply forge their own bucket.
    """
    return request.client.host if request.client is not None else "unknown"


@lru_cache
def _demo_llm_ip_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        max_attempts=settings.demo_llm_rate_limit_per_ip_max_attempts,
        window_seconds=settings.demo_llm_rate_limit_per_ip_window_seconds,
    )


def reset_demo_rate_limiter_for_tests() -> None:
    """Test-support only — mirrors conftest.py's reset of the auth.py
    limiters. Not called by application code.
    """
    _demo_llm_ip_limiter.cache_clear()


def enforce_demo_llm_rate_limit(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """FastAPI dependency for the two routes that actually spend LLM
    tokens (extraction trigger, triage trigger) — a no-op unless
    Settings.demo_mode is on, so every non-demo deployment (local dev,
    CI, a future non-public deployment) is completely unaffected. On the
    public demo, every visitor shares one pre-seeded account, so
    per-account limiting would do nothing to separate visitors from each
    other — per-IP is the key that actually bounds one visitor's ability
    to run up LLM cost, same reasoning as Stage 20's login/register
    limiters, just applied to a different pair of expensive routes.
    """
    if not settings.demo_mode:
        return
    try:
        _demo_llm_ip_limiter().check(_client_ip(request))
    except RateLimitExceeded as exc:
        retry_after = int(exc.retry_after_seconds) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "This is a public demo with a limited quota for AI-generating actions. "
            "Please try again later.",
            headers={"Retry-After": str(retry_after)},
        ) from exc
