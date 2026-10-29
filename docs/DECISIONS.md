# SmartDialer Architecture Decisions

This document details the core architectural decisions made in SmartDialer, covering what was chosen, the rationale, problems solved, and operational trade-offs, concluding with honest engineering assessments.

---

## 1. SQLite Storage Engine

- **What I chose**: An embedded SQLite database running with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and foreign key constraints enabled.
- **Why**: Zero external infrastructure dependencies; completely deterministic local testing; atomic file transactions; and instant test execution without Docker or PostgreSQL services.
- **What problem it solves**: Eliminates race conditions in single-host deployments by serializing write transactions cleanly with `BEGIN IMMEDIATE` and transaction rollbacks.
- **What it makes harder**: Horizontal scaling across multiple physical nodes is impossible with a standard filesystem; concurrency is bound by SQLite's single-writer lock.

---

## 2. Rule-Based Pacing Formula

- **What I chose**: An explainable proposal rule:
  $$\text{calls\_to\_start} = \min\left(\text{pending\_calls}, \max\left(0, \left\lceil \frac{\text{expected\_free\_agents}}{\text{effective\_answer\_rate}} \right\rceil - \text{calls\_in\_flight}\right)\right)$$
  `expected_free_agents` includes currently available agents and agents expected to finish soon. `effective_answer_rate` uses the recent 50-call window after the minimum sample is reached; before then the estimator uses a 0.50 prior, and it floors the rate at 0.01. The proposed calls-per-minute rate is also bounded by estimated capacity and provider health. The independent Safety Controller then applies its own caps, risk-adjusted answer-capacity bound, and safety decisions. Every proposal and safety decision logs a plain-text reason line.
- **Why**: Machine learning models or complex queuing solvers introduce non-deterministic edge cases, black-box failure modes, and training cold-start lags. A rule-based approach is auditable, explainable to operators in real-time, and easily constrained by hard safety gates.
- **What problem it solves**: Prevents dialer stagnation and under-dialing while maintaining continuous visibility into why every dial was proposed.
- **What it makes harder**: Rapidly non-stationary environments (e.g. erratic carrier call blocking) require explicit safety triggers (like sharp drop thresholds) rather than continuous smooth statistical adaptation.

---

## 3. Atomic Conditional Updates

- **What I chose**: Atomic conditional SQL statements verifying state preconditions at write time:
  ```sql
  UPDATE agents SET state = 'RESERVED' WHERE id = ? AND state = 'AVAILABLE';
  ```
  verified with immediate validation that affected rows equal 1 (`changes() == 1`).
- **Why**: Guarantees that regardless of thread scheduling or worker race conditions, an agent is never allocated to more than one call at the same time.
- **What problem it solves**: Eliminates double-allocation, race conditions, and phantom reservations without requiring application-level distributed locks.
- **What it makes harder**: Complex multi-table operations must be carefully orchestrated inside single transactions to avoid locking contention and deadlocks. Predictive calls use a distinct answer-time transaction to claim an available agent and link it to an already answered call.

---

## 4. Provider-Scoped Event Deduplication & Monotonic Sequences

- **What I chose**: A composite primary key on `(provider, event_id)` and unique constraint on `(call_id, provider, seq)` with monotonic sequence validation:
  - If event ID exists for the provider $\rightarrow$ `DUPLICATE`.
  - If event sequence $\le \text{MAX}(seq)$ $\rightarrow$ `STALE`.
  - If state transition violates `CALL_TRANSITIONS` $\rightarrow$ `INVALID_TRANSITION`.
- **Why**: The simulator's provider-event pipeline needs deterministic handling of duplicate, out-of-order, and late events, including after simulated worker recovery.
- **What problem it solves**: Prevents duplicate state-machine advancements (e.g., ringing counted twice or double completions) and models protection against replayed events and retries without integrating with real carriers.
- **What it makes harder**: Requires maintaining sequence state per provider call, rejecting out-of-order events rather than buffering and reassembling them into a delayed reordering queue.

---

## 5. The `UNCERTAIN` State and Crash Recovery

- **What I chose**: A tri-point crash recovery model:
  1. **Point 1 (Orphan Agent Reserved)**: Pre-call agent reservations with no active call are reset to `AVAILABLE`.
  2. **Point 2 (Pre-Provider Call Reserved)**: Calls that never reached a provider are safely moved to `QUEUED`; any agent reserved for the call is returned to `AVAILABLE`. Predictive reservations may have no agent assigned.
  3. **Point 3 (Provider Initiated/In-Flight)**: Calls that were handed to a provider (`INITIATED`, `RINGING`, `ANSWERED`, `CONNECTED`) are quarantined into `UNCERTAIN`. Any assigned agent is set to `PAUSED` until a simulated provider event reconciles the outcome.
- **Why**: Never assume a call failed just because a local server crashed. If a carrier dialed a real borrower, redialing immediately causes illegal duplicate calls and caller harassment.
- **What problem it solves**: Prevents abandoned connections, silent carrier leaks, and double-calling during unexpected server restarts.
- **What it makes harder**: Requires reconciliation processes or manual supervisor intervention if carrier webhooks are lost permanently.

---

## What I'm Least Confident About

The 50-call sliding window for answer rate estimation during extreme regime changes. If carrier call-blocking or a network outage drops answer rates from 70% to 5% instantly, the sliding window takes several dozen call attempts before the arithmetic mean drops fully, relying heavily on the Safety Controller's sharp-drop trigger rather than continuous statistical Bayesian inference.

---

## What I'd Do With Another Week

1. **Carrier Event Ingestion Buffer**: Build an asynchronous webhook inbox queue (e.g., Redis Streams / SQLite WAL inbox) that decouples carrier HTTP callbacks from internal state transitions.
2. **PostgreSQL Adapter with Row-Level Locking**: Implement `SELECT ... FOR UPDATE SKIP LOCKED` to allow seamless multi-worker clustering without lock thrashing.
3. **Adaptive Predictive Pacing**: Incorporate Bayesian priors (beta distribution on answer rate) so small sample sizes smoothly transition between progressive and predictive pacing instead of a step-function fallback.
4. **Agent Shift & Skill Matching**: Extend allocator priority ordering to match borrower debt attributes with specialized agent skill queues.
