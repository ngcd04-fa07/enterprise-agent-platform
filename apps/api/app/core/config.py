from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Matches secrets.token_urlsafe(32)-equivalent minimum length — a floor,
# not a real entropy check (see Settings._validate_session_secret_strength
# for why this deliberately doesn't try to detect low-entropy-but-long
# strings like "aaaa...aaaa").
_MIN_SESSION_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables.

    No defaults are provided for security-relevant values (session_secret,
    database_url) so that missing configuration fails at startup rather than
    silently falling back to an insecure or wrong value.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str
    session_secret: SecretStr

    api_cors_origins: list[str] = []

    # Filesystem-backed object storage root (see app/storage). Has a
    # working default, unlike database_url/session_secret, because it's
    # not security-relevant on its own — a wrong value fails loudly the
    # first time a file is written, not silently.
    storage_root: str = "./data/documents"
    max_upload_size_bytes: int = 25 * 1024 * 1024

    # Stage 20: a global ceiling on any request body, enforced at the ASGI
    # layer (app/security/body_size_limit.py) before any route/Pydantic
    # validation runs — closes the gap where only the upload route had a
    # bound. Must stay >= max_upload_size_bytes (validated below) so a
    # legitimate upload at exactly the configured limit is never rejected
    # by the global middleware before reaching the upload route's own,
    # more precise check; the gap above max_upload_size_bytes covers
    # multipart framing overhead (boundaries, headers, field names).
    max_request_body_bytes: int = 30 * 1024 * 1024

    # Stage 20: a ceiling on pages parsed from one uploaded PDF — file size
    # alone doesn't bound page count (many tiny pages fit in a small
    # file), and ingestion runs synchronously per request (see
    # IngestionService), so an unbounded page count is a real, if narrow,
    # resource-exhaustion vector. Surfaces as a clean ingestion failure
    # (document.status == "failed"), not a crash or a hang.
    max_pdf_pages: int = 500
    # A page-count ceiling doesn't directly bound the real cost (one
    # embedding call per chunk): a single pathological page could still
    # contain enough text to produce a huge number of chunks. This is
    # the direct bound on that actual cost, generous enough that no
    # realistic submission gets near it (2000 chunks * ~2000 chars is
    # already a multi-megabyte document of dense text).
    max_chunks_per_document: int = 2000

    # Stage 20: in-memory, per-process login/register throttling — see
    # app/security/rate_limiter.py. Deliberately not shared/distributed;
    # correct for this app's current single-instance deployment, same
    # reasoning as Stage 19's circuit breakers. Two independent buckets for
    # login: per-IP (throttles one source's overall attempt volume,
    # regardless of which account it targets) and per-(IP, identifier)
    # (slows a focused attempt against one account from one source) —
    # never keyed on the identifier alone, which would let an attacker
    # lock a *victim* out just by repeatedly guessing their email from
    # anywhere.
    login_rate_limit_per_ip_max_attempts: int = 10
    login_rate_limit_per_ip_window_seconds: float = 60.0
    login_rate_limit_per_identifier_max_attempts: int = 5
    login_rate_limit_per_identifier_window_seconds: float = 300.0
    # Registration has no "identifier" worth protecting the same way (the
    # identifier being registered doesn't exist yet) — IP-only throttling
    # is sufficient per docs/architecture.md's Stage 20 decision.
    register_rate_limit_per_ip_max_attempts: int = 5
    register_rate_limit_per_ip_window_seconds: float = 3600.0

    # Local, open-source LLM via Ollama (see app/llm_gateway) — no API key,
    # so nothing security-relevant to fail loudly on here. Defaults match
    # `ollama serve`'s default port and a model already used in dev; wrong
    # values fail loudly the first time extraction is actually called
    # (OllamaGateway raises LLMGenerationError), not silently.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    # The "capable" tier RoutingLLMGateway escalates to for complexity=COMPLEX
    # calls (triage synthesis, eval judging) and on fast-tier failure — see
    # docs/architecture.md, model routing decision. Same no-API-key rationale
    # as ollama_model; just a second, larger local model.
    ollama_capable_model: str = "qwen2.5:14b"
    # Stage 19: previously hardcoded constants in OllamaGateway, now
    # tunable without a redeploy. Same defaults as before this stage.
    ollama_timeout_seconds: float = 60.0
    ollama_max_attempts: int = 2
    # Stage 19: per-tier circuit breaker thresholds (see
    # app/llm_gateway/circuit_breaker.py) — how many consecutive
    # *transient* failures (never content/permanent ones) open a tier's
    # breaker, and how long it stays open before a half-open probe.
    llm_breaker_failure_threshold: int = 3
    llm_breaker_cooldown_seconds: float = 30.0

    @model_validator(mode="after")
    def _validate_session_secret_strength(self) -> "Settings":
        """A floor, not a real entropy check: length alone doesn't prove a
        secret is unpredictable (a repeated character string of the same
        length would pass this and still be worthless), but rolling
        anything resembling actual entropy detection would be unreliable
        and give a false sense of assurance. This just enforces the
        documented deployment expectation — generate the value randomly
        (e.g. `openssl rand -base64 32` or `python3 -c
        "import secrets; print(secrets.token_urlsafe(32))"`) — and fails
        loudly at startup for the one mistake this check can actually
        catch: a short, clearly-inadequate value ("changeme", "test",
        the literal placeholder in .env.example).
        """
        if len(self.session_secret.get_secret_value()) < _MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"SESSION_SECRET must be at least {_MIN_SESSION_SECRET_LENGTH} characters — "
                "generate one randomly, e.g. "
                '`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. '
                "This is a minimum-length floor, not an entropy guarantee: a random value "
                "of adequate length is still the deployer's responsibility."
            )
        return self

    @model_validator(mode="after")
    def _validate_body_limit_covers_uploads(self) -> "Settings":
        if self.max_request_body_bytes < self.max_upload_size_bytes:
            raise ValueError(
                "max_request_body_bytes must be >= max_upload_size_bytes — otherwise the "
                "global request-body limit would reject legitimate uploads before the "
                "upload route's own, more precise size check ever runs."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
