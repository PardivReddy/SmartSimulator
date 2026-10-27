# Testing and CI

## Local commands

```powershell
uv run ruff check .
uv run pytest
python -m smartdialer.cli simulate --mode progressive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario provider_outage --agents 4 --borrowers 20 --seed 42
```

Tests use synthetic records and temporary databases. `test_competing_connections_cannot_double_allocate` uses two SQLite connections and threads against the same file to exercise allocation contention. Other tests cover explicit legal and illegal state edges, event idempotency/order, bounded recovery, estimator/safety boundaries, seeded provider replay, and the CLI.

Metric definitions: connection rate is connected plus completed calls divided by attempted calls; abandonment rate is cancelled calls divided by attempted plus cancelled calls; provider error rate counts mock provider `FAILED` events divided by attempts. The current scenarios do not simulate agent abandonment after an answer, so abandonment remains zero unless calls are explicitly cancelled. Throughput is simulated attempts per simulated elapsed minute; it is not wall-clock load-test throughput.

## CI behavior

GitHub Actions runs on pushes and pull requests targeting `main`, `feature/**`, or `fix/**`; it installs pinned `uv` and synchronizes the hash-locked `uv.lock`, then runs Ruff and pytest on Python 3.11, 3.12, and 3.13. `contents: read` is the only workflow permission. Third-party actions use full commit SHA pins. CI does not need the company dataset or secrets. This workflow has not been executed on GitHub from this workspace.

For repository settings, protect `main`, require the CI status check, require review, and disallow force pushes and branch deletion. Confirm the branch protection names match the configured job/check before enabling it.

## Current verification

The local environment has Python 3.15.1 available through its `uv` installation. Development tools were installed in the workspace virtual environment. The project supports Python 3.11+, and CI targets 3.11–3.13; only Python 3.15.1 was available for local execution, so the matrix versions and GitHub-hosted workflow remain unverified.

Latest local results: Ruff passed; pytest passed all 57 tests. Progressive, predictive, no-agent, low-answer, and outage CLI scenarios produced simulated metrics. These results are local only and do not imply GitHub CI or load-test success.
