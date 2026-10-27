# Contributing

## Local workflow

Use Python 3.11–3.13. Install the pinned `uv==0.13.5` tool, then run `uv sync --locked --extra dev`. Run `uv run ruff check .` and `uv run pytest` before proposing a change.

Keep tests deterministic and offline. Use synthetic records, temporary SQLite databases, and seeded random generators. Never copy company data, credentials, contact details, or database files into tracked files, test snapshots, logs, or commits. Do not add real telecom credentials or integrations.

## Change expectations

Update the relevant architecture, reliability, testing, backlog, and changelog documents when behavior changes. Keep each state transition explicit and fail closed on stale or invalid control inputs. CI runs on pushes and pull requests for `main`, `feature/**`, and `fix/**`; it runs Ruff and pytest on Python 3.11, 3.12, and 3.13.
