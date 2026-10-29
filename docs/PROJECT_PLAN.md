# Project plan

The plan follows the assignment requirements supplied by the user. The source PDF is not stored in the workspace; the supplied assignment text has been audited and the simulation results and submission guidance reconciled against the current implementation.

| Milestone | Acceptance criteria | Status |
|---|---|---|
| 1. Repository foundation | Safe ignores, Python package metadata, local setup guide, CI | Implemented; local Python 3.15 Ruff and pytest checks run |
| 2. Domain and persistence | Explicit state graphs; SQLite records; atomic reservation; event history | Implemented as a prototype; limits in reliability notes |
| 3. Progressive dialer | Priority/eligibility scheduling; one active call per agent; concurrency race coverage | Implemented; race test passed |
| 4. Predictive and safety | Proposal separated from approval; caps, stale-data and provider-health failsafes | Implemented; calibration is illustrative only |
| 5. Providers/events | Two deterministic mock profiles; duplicate, stale, invalid event rejection | Implemented at local simulation scope |
| 6. Reliability/recovery | Bounded recovery and persistence/replay behavior | Partial; local retry/backoff simulation and recovery tests exist, but there is no production-grade retry scheduler or real worker crash harness |
| 7. Scenarios/metrics/load | Scenario coverage and aggregate simulated metrics | Partial; normal/predictive, no-agent, low-answer, outage/recovery scenarios, utilization/idle aggregates, and a basic SQLite contention load test implemented; extensive fault replay and high-volume load remain |
| 8. CI/docs/final verification | CI lint/test matrix and complete documentation | Docs and workflow drafted; local checks passed; GitHub execution unverified |

## Current blockers and follow-up

- The source assignment PDF itself is not in the repository; the assignment requirements were supplied in the conversation and reviewed.
- Local verification ran on Python 3.15.1; GitHub CI targets Python 3.11 through 3.13 and has not been run from this workspace.
- CI has not been executed on GitHub because no push or PR was authorized.
- Strengthen process-level crash/recovery and fault-injection coverage and add high-volume load checks before treating the prototype as complete. Bounded provider retry/backoff and timeout simulation are implemented locally; a production-grade scheduler and worker supervision are not.
