# Recommended Claude Code permissions

Principle: routine, repository-local development is streamlined; anything
destructive, privileged, external, or production-affecting requires explicit
human approval each time. This mirrors the rules already stated in
`CLAUDE.md` and the project bootstrap prompt — this file is the concrete
allow/deny mapping for Claude Code's permission system.

## Suggested allow list (safe to run without prompting)

Read-only / local-inspection:
`git status`, `git diff`, `git log`, `git branch`, `ls`, `find`, `grep`,
`rg`, `cat`, `sed -n` (inspection only, not in-place edit)

Local dev/build/test loop:
`python`, `pytest`, `ruff`, `mypy` / `pyright`, `npm install`, `npm test`,
`npm run lint`, `npm run build`, `npx`, `alembic` (upgrade/downgrade against
the local dev database only), `docker`, `docker compose`, `psql` (against
`localhost`/the local dev database only), `curl` against `localhost`

## Requires explicit approval every time (never pre-authorized)

- `git push`, `git push --force` (force push never auto-approved)
- `git reset --hard`
- Deleting branches, especially any branch that may contain work
- Rewriting shared git history
- `rm -rf` outside clearly generated/local build artifacts (`node_modules`,
  `.venv`, `dist`, `__pycache__`, etc.)
- Deleting files the user didn't create this session
- `sudo` / any system-level configuration change
- Installing system-wide (non-project) packages
- Modifying SSH keys or credential stores
- Destructive SQL, or any SQL, against a non-local database
- Deploying to production, creating cloud resources, creating paid services
- Publishing packages, sending emails, modifying external SaaS data
  (real Gmail/Drive/Slack/GitHub write actions once MCP integrations land)
- Committing or pushing anything touching `.env`, secrets, or credentials
- Modifying GitHub repository settings: visibility, branch protection,
  secrets/Actions secrets, ownership/transfer, releases

## Notes

- This project has no CI-affecting or production deploy target yet
  (Stages 0–8 are entirely local). This file will be revisited once Docker
  Compose (Stage 1) and CI (Stage 8+) exist, and again before Stage 21
  (deployment).
- If Claude Code's settings support project-level allow/deny rules
  (`.claude/settings.json`), the lists above should be encoded there rather
  than relied on as prose — flagged here as a follow-up, not done as part of
  Stage 0 planning.
