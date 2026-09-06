from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
