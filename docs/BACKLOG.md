# Backlog

| ID | Item | State | Acceptance / evidence |
|---|---|---|---|
| B01 | Correct repository ignore rules and establish Python package | Done | `.gitignore`, `pyproject.toml` |
| B02 | Model agent and call state transitions | Done | `tests/test_domain.py` enumerates legal/illegal edges |
| B03 | Add transactional progressive allocation | Verified locally | SQLite `BEGIN IMMEDIATE`; multi-connection race test passed |
| B04 | Add pacing estimator and independent safety controller | Verified locally | boundary/staleness tests passed |
| B05 | Add seeded mock providers and simulation CLI | Verified locally | deterministic replay and CLI tests passed |
| B06 | Add event dedupe, ordering checks, and recovery | Partial | provider-scoped event checks, bounded local retry/backoff simulation, and recovery tests are implemented; production-grade retry scheduling, worker supervision, and a process-level crash harness are not |
| B07 | Profile and map the private synthetic dataset safely | Docs drafted | aggregate-only docs; raw data remains ignored and untracked |
| B08 | Finish operational metrics and scenario suite | Partial | calls/rates/throughput, utilization/idle, provider failure counts, controller count, representative scenarios, a seed-42 progressive-vs-predictive baseline comparison (`docs/simulation_results.md`), and basic contention load smoke test implemented; queue timing is currently zero; extensive replay/load cases remain |
| B09 | Run full local lint and test suite | Verified locally: 2026-10-29 | 111 pytest tests passed; Ruff lint and format checks passed on Python 3.15. Supported CI versions remain unverified on GitHub |
| B10 | Validate GitHub CI | Not run | requires a future push/PR; do not claim success |
| B11 | Compare behavior to original assignment | Complete from supplied requirements | Assignment text was supplied in the conversation and reviewed; source PDF is not stored locally |
| B12 | Add reproducible basic SQLite load test | Recorded local smoke observations | The 32-agent/32-borrower/16-worker/seed-42 command passed in a recorded local run. At 1,000 agents/borrowers, `--workers 8 --seed 42` passed three recorded repetitions (1,000 reservations each, zero errors; about 39.65–40.17 reservations/s). At 16 workers, intermittent `database is locked` errors occurred at `BEGIN IMMEDIATE`; one observed run had 998 reservations and 2 errors. These observations were not independently reverified in this documentation-only task, are not capacity claims, and 10,000 agents remain unmeasured |
