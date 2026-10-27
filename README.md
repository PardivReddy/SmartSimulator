# Resolve SmartDialer Simulator

A local Python prototype for progressive and safety-controlled predictive dialing. It uses seeded mock providers and SQLite only. It does not place calls, message people, use borrower contact details, or connect to a telecom service. All reported results are **simulated**.

The original assignment PDF was not present in the workspace when this implementation began. Requirements below follow the supplied master prompt and should be checked against the assignment PDF if it becomes available.

## Windows setup

Install Python 3.12 and Git, and make sure the Python launcher (`py`) is available. From PowerShell in the repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
py -3.12 -m pip install uv==0.13.5
uv sync --locked --extra dev
```

Run checks and simulations:

```powershell
uv run ruff check .
uv run pytest
python -m smartdialer.cli simulate --mode progressive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --mode predictive --agents 4 --borrowers 20 --seed 42
python -m smartdialer.cli simulate --scenario provider_outage --agents 4 --borrowers 20 --seed 42
```

To retain a local SQLite run database, add `--database .\simulation.sqlite3`. Databases are ignored by Git. Use only synthetic IDs in local scenarios.

## What it models

- Validated agent and call state transition graphs, including separate `ANSWERED` and `CONNECTED` states.
- Progressive allocation to available agents using priority ordering, eligibility flags, duplicate-active-call checks, and SQLite `BEGIN IMMEDIATE` transactions.
- A predictive rate proposal that never starts calls, followed by an independent safety controller with rate, concurrency, provider health, abandonment-risk, sample-size, and freshness limits.
- Two seeded local mock provider profiles with different simulated answer, failure, delay, duration, rate, and concurrency settings.
- Idempotency keys and monotonically increasing event sequence numbers for duplicate and stale event handling, plus a bounded local recovery routine.
- Aggregate simulated metrics, including call outcomes, connection/abandonment/provider failure rates, agent utilization/idle time, and simulated throughput. These values are illustrative and are not performance or compliance claims.

## Design limits

This is an educational simulator, not a production dialer. SQLite serializes allocation transactions on a single local database; this is not a distributed lock or multi-host coordination service. The prototype does not provide a real-time worker pool, telephony adapter, timezone-aware contact policy, consent/suppression enforcement, production-grade retry scheduler, audit retention policy, or dashboard. The synthetic dataset is profiled for context but is intentionally not loaded into simulation state. Predictive pacing uses a simple capacity estimate and conservative gates; it is not trained or calibrated against real-world outcomes.

See [architecture](docs/ARCHITECTURE.md), [reliability notes](docs/RELIABILITY.md), [testing](docs/TESTING.md), [dataset inventory](docs/dataset_inventory.md), [data profile](docs/data_profile.md), [data mapping](docs/data_mapping.md), and [interview demonstration](docs/DEMO.md).
