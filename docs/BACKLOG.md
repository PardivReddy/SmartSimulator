# Backlog

| ID | Item | State | Acceptance / evidence |
|---|---|---|---|
| B01 | Correct repository ignore rules and establish Python package | Done | `.gitignore`, `pyproject.toml` |
| B02 | Model agent and call state transitions | Done | `tests/test_domain.py` enumerates legal/illegal edges |
| B03 | Add transactional progressive allocation | Verified locally | SQLite `BEGIN IMMEDIATE`; multi-connection race test passed |
| B04 | Add pacing estimator and independent safety controller | Verified locally | boundary/staleness tests passed |
| B05 | Add seeded mock providers and simulation CLI | Verified locally | deterministic replay and CLI tests passed |
| B06 | Add event dedupe, ordering checks, and recovery | Partial | event checks and bounded recovery implemented; timeout/backoff/crash harness missing |
| B07 | Profile and map the private synthetic dataset safely | Docs drafted | aggregate-only docs; raw data remains ignored and untracked |
| B08 | Finish operational metrics and scenario suite | Partial | calls/rates/throughput, utilization/idle, provider failure counts, controller count and representative outage/recovery/no-agent scenarios implemented; queue timing is currently zero; extensive replay/load cases remain |
| B09 | Run full local lint and test suite | Verified on Python 3.15.1 | Ruff clean and all 57 pytest tests passed; supported CI versions not locally tested |
| B10 | Validate GitHub CI | Not run | requires a future push/PR; do not claim success |
| B11 | Compare behavior to original assignment PDF | Blocked by missing input | no PDF found locally |
