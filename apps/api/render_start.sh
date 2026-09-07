#!/bin/sh
# Render-specific start command (single-instance free/starter tier, so
# the multi-replica migration race docker-compose's separate `migrate`
# service exists to prevent doesn't apply here — see docs/deployment.md).
# A committed script rather than an inline "alembic upgrade head &&
# uvicorn ..." string in Render's Docker Command field: that field's
# exact quoting/tokenization of `&&` and nested quotes isn't reliably
# verifiable from the dashboard alone, and produced a real
# "sh: 1: <whole string>: not found" failure when tried inline. A bare
# `sh render_start.sh` with no quotes or shell operators for Render to
# mis-tokenize is unambiguous regardless of how that field splits its
# input.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
