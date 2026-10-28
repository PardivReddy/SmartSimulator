# Resolve SmartDialer Simulator

A deterministic, safety-controlled predictive and progressive dialer simulator built with pure Python and SQLite. Designed for high reliability, explainable predictive pacing, and strict caller protection without external infrastructure dependencies.

> [!IMPORTANT]
> All activities and metrics are **purely simulated**. SmartDialer never places real telephone calls, sends messages, or communicates with external paid telecom carriers.

---

## Final Summary

SmartDialer decouples call estimation from execution through a unidirectional pipeline: **Campaign $\rightarrow$ Pacing Engine $\rightarrow$ Safety Controller $\rightarrow$ Call Allocator $\rightarrow$ Provider**. The predictive pacing engine uses a transparent, rule-based formula to propose dial volume based on expected free agents, active in-flight calls, and a recent sliding-window answer rate, always outputting an explainable one-line justification. The independent Safety Controller holds unconditional veto authority: it caps proposals so expected connections never exceed free agents, throttles dialing on sharp answer-rate drops or high abandonment, and automatically falls back to progressive 1:1 dialing when sample sizes are small or provider health degrades. Crucially, predictive logic cannot place calls; only the Call Allocator reserves agents and borrowers using atomic conditional updates under SQLite immediate write locks. Carrier webhooks are validated with provider-scoped idempotency keys and monotonic sequence numbers, rejecting stale or duplicate events without side effects. If a worker crashes mid-call, pre-provider reservations are safely requeued while in-flight provider calls are quarantined in an `UNCERTAIN` state, ensuring no borrower is ever double-dialed or stranded.

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
# Run full unit and regression test suite (91 tests)
uv run pytest --basetemp=.test-tmp/pytest -o cache_dir=.test-tmp/pytest_cache

# Run linter and formatting checks
uv run ruff check .
uv run ruff format --check .

# Run concurrent SQLite load test (multi-worker race)
uv run python -m smartdialer.cli load-test --agents 32 --borrowers 32 --workers 16 --seed 42
```

---

## Running Simulations

Run any of the required deterministic scenarios via CLI. Results are displayed as a formatted terminal table and automatically archived in [`docs/simulation_results.md`](docs/simulation_results.md).

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
   Agent allocation uses `UPDATE agents SET state='RESERVED' WHERE id=? AND state='AVAILABLE'` with `changes() == 1` validation within `BEGIN IMMEDIATE` transactions. Multi-threaded races guarantee exactly one winner.
2. **Strict Separation of ANSWERED and CONNECTED**:
   A carrier pickup event (`ANSWERED`) does not imply agent audio bridge (`CONNECTED`). Calls are only marked `CONNECTED` once agent allocation is confirmed.
3. **Idempotency & Replay Resistance**:
   Every carrier event is scoped by `(provider, event_id)` and checked against monotonically increasing sequence numbers. Duplicates and out-of-order events produce zero state transitions.
4. **Tri-Point Crash Recovery**:
   - *Point 1 (Agent Reserved)*: Orphan reserved agents reset to `AVAILABLE`.
   - *Point 2 (Pre-Provider Call)*: Safely requeued to `QUEUED`, agent returned to `AVAILABLE`.
   - *Point 3 (Provider In-Flight)*: Call moved to `UNCERTAIN`, agent `PAUSED` to avoid duplicate dialing.

---

## Documentation Index

- [System Architecture & Mermaid Diagrams](docs/ARCHITECTURE.md)
- [Architecture Decisions & Rationale](docs/DECISIONS.md)
- [Simulation Results Archive](docs/simulation_results.md)
- [Reliability & Crash Recovery](docs/RELIABILITY.md)
- [Testing & Quality Assurance](docs/TESTING.md)
