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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
