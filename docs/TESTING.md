# Testing and CI

## Local commands

```powershell
uv run ruff check .
uv run pytest
python -m smartdialer.cli simulate --mode progressive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --mode predictive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario no_available_agents --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario low_answer_rate --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario provider_outage --agents 4 --borrowers 20 --seed 42
uv run python -m smartdialer.cli load-test --agents 32 --borrowers 32 --workers 16 --seed 42
```

The provider-outage CLI scenario demonstrates an in-progress ringing call surviving an outage, new work being blocked while all providers are unavailable, a timed-out attempt entering bounded retry wait, the Safety Controller pausing predictive pacing, and the retry completing after recovery. Retry timing and retry exhaustion are also tested directly.

Tests use synthetic records and temporary databases. `test_competing_connections_cannot_double_allocate` uses two SQLite connections and threads against the same file to exercise allocation contention. `test_loadtest.py` validates load-test reservation invariants. Other tests cover explicit legal and illegal state edges, event idempotency/order, bounded recovery, estimator/safety boundaries, seeded provider replay, metrics, and the CLI.

The basic load test starts one task per agent and runs up to `--workers` threads. Each thread opens an independent SQLite connection. Expected reservations are `min(agents, borrowers)`. A passing run requires that exact count, zero duplicate borrower reservations, and zero worker errors. `reservations_per_second` and `elapsed_seconds` are observational local timing only; compare runs only on the same machine and setup. This is not a high-volume benchmark or production capacity claim.

Metric definitions: connection rate is connected plus completed calls divided by attempted calls; abandonment rate is cancelled calls divided by attempted plus cancelled calls; provider error rate counts mock provider `FAILED` events divided by attempts. The current scenarios do not simulate agent abandonment after an answer, so abandonment remains zero unless calls are explicitly cancelled. Throughput is simulated attempts per simulated elapsed minute; it is not wall-clock load-test throughput.

## CI behavior

GitHub Actions runs on pushes and pull requests targeting `main`, `feature/**`, or `fix/**`; it installs pinned `uv` and synchronizes the hash-locked `uv.lock`, then runs Ruff and pytest on Python 3.11, 3.12, and 3.13. `contents: read` is the only workflow permission. Third-party actions use full commit SHA pins. CI does not need the company dataset or secrets. This workflow has not been executed on GitHub from this workspace.

For repository settings, protect `main`, require the CI status check, require review, and disallow force pushes and branch deletion. Confirm the branch protection names match the configured job/check before enabling it.

## Current verification

The local environment has Python 3.15.1 available through its `uv` installation. Development tools were installed in the workspace virtual environment. The project supports Python 3.11+, and CI targets 3.11–3.13; only Python 3.15.1 was available for local execution, so the matrix versions and GitHub-hosted workflow remain unverified.

Reliability verification on Python 3.15.1: the focused storage/provider tests passed (30 tests), the full suite passed (78 tests), `uv run ruff check smartdialer tests` passed, and `uv run ruff format --check smartdialer tests` passed. The provider-outage CLI reported one timeout and one bounded retry, deferred it until recovery, preserved the existing call in `RINGING`, and showed a zero-rate `PAUSE` safety decision while both providers were unavailable. The 32-agent load test returned `PASS` with 32 unique reservations, zero duplicates, and zero worker errors; its measured 1.098 seconds (29.14 reservations/second) is one local observation, not a benchmark or capacity claim. Only Python 3.15.1 was available locally; other CI matrix versions and GitHub-hosted CI remain unverified.
