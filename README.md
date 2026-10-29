# Resolve SmartDialer Simulator

A deterministic, local-only simulator for Progressive and Predictive dialing, built with Python and SQLite. It demonstrates explainable pacing proposals, independent safety decisions, transactional allocation, and simulated provider outcomes; it is a prototype, not a production dialer or a guarantee of caller protection.

> [!IMPORTANT]
> All activities and metrics are **purely simulated**. SmartDialer never places real telephone calls, sends messages, or communicates with external paid telecom carriers.

---

## Final Summary

SmartDialer decouples call estimation from execution through a pipeline: **Campaign → Pacing Engine → Safety Controller → Call Allocator → Mock Provider**. The Predictive Pacing Engine proposes dial volume from available capacity, in-flight calls, and recent answer rates; the independent Safety Controller applies caps and may approve, reduce, reject, pause, or fall back to Progressive dialing under defined conditions. Progressive dialing reserves an agent before initiating; Predictive dialing reserves a borrower and claims an available agent when answered. If no agent can be claimed, the call is recorded as `ABANDONED_NO_AGENT`. These are local simulation behaviors, not production guarantees. Provider events use provider-scoped idempotency and sequence checks. Recovery safely requeues pre-provider reservations and quarantines provider-started calls as `UNCERTAIN`; reconciliation may require a later provider event, and this prototype does not provide production worker supervision or caller-protection/compliance controls.

---

## Quickstart & Environment Setup

SmartDialer requires **Python 3.11+** and uses standard virtual environments.

### 1. Create Virtual Environment and Install Dependencies

```powershell
# Using standard Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install uv
uv sync --locked --extra dev
```

### 2. Run Test Suite and Linters

```powershell
# Run the full unit and regression test suite
uv run pytest --basetemp=.test-tmp/pytest -o cache_dir=.test-tmp/pytest_cache

# Run linter and formatting checks
uv run ruff check .
uv run ruff format --check .

# Run concurrent SQLite load test (multi-worker race)
uv run python -m smartdialer.cli load-test --agents 32 --borrowers 32 --workers 16 --seed 42
```

---

## Running Simulations

The A, B, C, D, `agent-drop`, and `outage` scenario commands print a formatted terminal table and append or replace that scenario's section in [`docs/simulation_results.md`](docs/simulation_results.md). Re-running those commands therefore modifies the results document. Other `simulate` commands, including `provider_outage`, and the `load-test` command print JSON and do not write simulation results to that document.

```powershell
# Scenario A: 20% answer rate, 120s talk duration
uv run python -m smartdialer.cli simulate --scenario A --seed 42

# Scenario B: 50% answer rate, 90s talk duration
uv run python -m smartdialer.cli simulate --scenario B --seed 42

# Scenario C: 70% answer rate, 180s talk duration
uv run python -m smartdialer.cli simulate --scenario C --seed 42

# Scenario D: Dynamic mid-run shift (70% -> 10% answer rate, 180s -> 60s talk)
uv run python -m smartdialer.cli simulate --scenario D --seed 42

# Agent Drop Scenario: 100 agents start, 40 dropped at t=30s; checks adjustment latency
uv run python -m smartdialer.cli simulate --scenario agent-drop --seed 42

# Provider Outage Scenario: Outage at t=40s, recovery at t=80s; checks backoff & pause
uv run python -m smartdialer.cli simulate --scenario outage --seed 42
```

---

## Architectural Principles & Core Guarantees

1. **Atomic Conditional Reservations**:
   Progressive agent allocation uses `UPDATE agents SET state='RESERVED' WHERE id=? AND state='AVAILABLE'` with `changes() == 1` validation within `BEGIN IMMEDIATE` transactions. Predictive calls reserve a borrower only; when answered, a separate `BEGIN IMMEDIATE` transaction conditionally claims an available agent and links it to the call. Multi-threaded races cannot claim the same available agent twice.
2. **Strict Separation of ANSWERED and CONNECTED**:
   A simulated provider pickup event (`ANSWERED`) does not imply an agent audio bridge (`CONNECTED`). Calls are only marked `CONNECTED` once agent allocation is confirmed.
3. **Idempotency & Replay Resistance**:
   Every simulated provider event is scoped by `(provider, event_id)` and checked against monotonically increasing sequence numbers. Duplicates and out-of-order events produce zero state transitions.
4. **Tri-Point Crash Recovery**:
   - *Point 1 (Agent Reserved)*: Orphan reserved agents reset to `AVAILABLE`.
   - *Point 2 (Pre-Provider Call)*: Safely requeued to `QUEUED`. An associated agent is returned to `AVAILABLE` only if it is still `RESERVED`; if it became `PAUSED` before provider initiation, it remains `PAUSED`. Predictive reservations may have no agent assigned.
   - *Point 3 (Provider In-Flight)*: Call moved to `UNCERTAIN`; any assigned agent is `PAUSED` to avoid duplicate dialing.

---

## Documentation Index

- [System Architecture & Mermaid Diagrams](docs/ARCHITECTURE.md)
- [Architecture Decisions & Rationale](docs/DECISIONS.md)
- [Simulation Results Archive](docs/simulation_results.md)
- [Reliability & Crash Recovery](docs/RELIABILITY.md)
- [Testing & Quality Assurance](docs/TESTING.md)
