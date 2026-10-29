# Testing and CI

## Local commands

```powershell
uv run ruff check .
uv run pytest --basetemp=.test-tmp/pytest -o cache_dir=.test-tmp/pytest_cache
uv run ruff format --check .
python -m smartdialer.cli simulate --mode progressive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --mode predictive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario no_available_agents --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario low_answer_rate --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario provider_outage --agents 4 --borrowers 20 --seed 42
uv run python -m smartdialer.cli load-test --agents 32 --borrowers 32 --workers 16 --seed 42
uv run python -m smartdialer.cli load-test --agents 1000 --borrowers 1000 --workers 8 --seed 42
```

For a reproducible mode comparison, run the progressive and predictive commands above
with identical agent, borrower, and seed inputs. The seed-42 4-agent/20-borrower
single-batch comparison is recorded in [`simulation_results.md`](simulation_results.md);
it is illustrative, not a statistical performance benchmark.

The provider-outage CLI scenario demonstrates an in-progress ringing call surviving an outage, new work being blocked while all providers are unavailable, a timed-out attempt entering bounded retry wait, the Safety Controller pausing predictive pacing, and the retry completing after recovery. Retry timing and retry exhaustion are also tested directly.

Tests use synthetic records and temporary databases. `test_competing_connections_cannot_double_allocate` uses two SQLite connections and threads against the same file to exercise allocation contention. `test_loadtest.py` validates load-test reservation invariants. Other tests cover explicit legal and illegal state edges, event idempotency/order, bounded recovery, estimator/safety boundaries, seeded provider replay, metrics, and the CLI.

The basic load test starts one task per agent and runs up to `--workers` threads. Each thread opens an independent SQLite connection. Expected reservations are `min(agents, borrowers)`. A passing run requires that exact count, zero duplicate borrower reservations, and zero worker errors. `reservations_per_second` and `elapsed_seconds` are observational local timing only; compare runs only on the same machine and setup. At 1,000 agents/borrowers, 8 workers passed three local repetitions; 16 workers intermittently encountered `sqlite3.OperationalError: database is locked` at `BEGIN IMMEDIATE`. Use the 8-worker command above for the repeatable 1,000-agent smoke check in this environment. This is not a high-volume benchmark or production capacity claim; the 10,000-agent scale has not been measured.

Metric definitions: connection rate is connected plus completed calls divided by attempted calls; abandonment rate is `(CANCELLED + ABANDONED_NO_AGENT) / (attempted + CANCELLED)`. `ABANDONED_NO_AGENT` is an attempted call that was answered but could not be connected to an agent; `CANCELLED` retains its existing contribution and is added to the denominator because it is not included in attempted calls. Provider error rate counts mock provider `FAILED` events divided by attempts. Whether predictive scenarios produce no-agent abandonment depends on the scenario and is not guaranteed. Throughput is simulated attempts per simulated elapsed minute; it is not wall-clock load-test throughput.

## CI behavior

GitHub Actions runs on pushes and pull requests targeting `main`, `feature/**`, or `fix/**`; it installs pinned `uv` and synchronizes the hash-locked `uv.lock`, then runs Ruff and pytest on Python 3.11, 3.12, and 3.13. `contents: read` is the only workflow permission. Third-party actions use full commit SHA pins. CI does not need the company dataset or secrets. This workflow has not been executed on GitHub from this workspace.

For repository settings, protect `main`, require the CI status check, require review, and disallow force pushes and branch deletion. Confirm the branch protection names match the configured job/check before enabling it.

## Current verification

The earlier recorded full-suite verification from 2026-10-28 had 103 tests pass on Python 3.15.1 using a repository-local pytest temporary directory; the default Windows temp location was not writable in that environment. A later supplied final-correctness report states that 107 full-suite tests and 53 focused tests passed, and that Ruff lint, Ruff format, and `git diff --check` passed. Those later results were not independently rerun during this documentation cleanup, and their exact tested Git revision was not recorded. The 103-test result is historical; the project supports Python 3.11+, and CI targets 3.11–3.13, which remain unverified on GitHub.
