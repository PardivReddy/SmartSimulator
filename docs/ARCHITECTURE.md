# Architecture

## Runtime flow

`cli` creates a `Simulation`, which owns a `Store`, mock providers, and a `SafetyController`. Progressive allocation calls `Store.allocate`, where an immediate SQLite transaction verifies agent availability, selects the highest-priority eligible borrower without an active call, reserves the agent, and writes a call/event-history row. Predictive mode first asks the pure pacing estimator for a proposal, then asks the independent safety controller to cap it. Only the simulator orchestration uses the approved quantity to decide how many local mock attempts to model.

`domain` declares agent and call transition graphs. `providers` exposes seeded, local event outcomes. `storage` persists agents, synthetic borrowers, calls, provider events, and audit history. `metrics` reports aggregates tagged `SIMULATED`.

## State model

Call states are `QUEUED -> RESERVED -> INITIATED -> RINGING -> ANSWERED -> CONNECTED -> COMPLETED`, with safe failure/cancellation paths. `ANSWERED` and `CONNECTED` are separate. Agent states include `OFFLINE`, `AVAILABLE`, `RESERVED`, `DIALING`, `CONNECTED`, `WRAP_UP`, and `PAUSED`. See the transition graphs in `smartdialer/domain.py`.

## Consistency

SQLite `BEGIN IMMEDIATE` serializes allocation transactions across connections to one database file. The transaction checks agent state and active reservations before inserting a call. A unique event ID and `(call_id, seq)` constraint prevent duplicate event application; event sequences not newer than the latest accepted event are rejected. The domain transition graph also rejects impossible forward events. This provides local database consistency, not distributed leases, leader election, or exactly-once delivery across external systems.

The recovery helper retries stranded reservations once and then fails them. It does not implement a scheduled exponential backoff worker. Data durability depends on the local filesystem and SQLite configuration; WAL is enabled for file-backed databases.
