# Reliability and safety notes

- **Allocation:** one SQLite immediate transaction reserves one available agent and one eligible borrower. Rechecking availability inside the transaction handles agents who became unavailable before allocation.
- **Duplicate work:** allocation filters borrowers with active call states. Terminal and queued records are not considered active. This sample does not model legal contact windows or suppression lists.
- **Events:** `event_id` is the idempotency key; `(call_id, seq)` is unique. Repeated IDs return `DUPLICATE`; old sequence values return `STALE`; invalid transitions return `INVALID_TRANSITION`.
- **Safety:** predictive output is a proposal only. Safety applies configured rate/concurrency caps and pauses on stale/low-sample estimates or unhealthy providers. The abandonment estimate is a deliberately simple illustrative heuristic, not a regulatory calculation.
- **Provider failure:** mocks can fail or be toggled unavailable. Failure becomes a simulated failed attempt after the mock timeout interval. Production timeout handling and exponential backoff are not implemented.
- **Worker recovery:** `Store.recover()` requeues stranded active calls once and marks a repeated stranded retry failed. It is a deterministic local recovery hook, not process supervision or a crash-safe distributed scheduler.
- **Logs and privacy:** no names, phone numbers, email addresses, or raw dataset rows are logged. Only synthetic identifiers and aggregates should enter simulator output.
- **Limitations:** real-time contention, multi-host recovery, retention, provider callback authentication, timezone contact policy, opt-out/suppression enforcement, and compliance review are outside this prototype.
