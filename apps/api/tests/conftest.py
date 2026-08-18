import os

# Settings has no defaults for security-relevant values by design (see
# app.core.config), so tests need these present before app.main is
# imported anywhere. Real connectivity is exercised against the docker
# compose / CI Postgres service, not this placeholder URL.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("SESSION_SECRET", "test-secret-do-not-use-in-production")
