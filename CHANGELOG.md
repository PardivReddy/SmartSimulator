# Changelog

## 0.1.0 – project foundation and simulator prototype

- Replaced malformed ignore-file content with project data and Python artifact safeguards.
- Added explicit agent/call states, SQLite reservation and event storage, seeded mock providers, pacing proposal and safety gate, simulation CLI, and initial tests.
- Added repository, architecture, reliability, dataset, project planning, and CI documentation.
- Assignment PDF remains unavailable; simulator behavior follows the supplied master prompt.

## Audit follow-up

- Added a dependency-light threaded SQLite reservation load test and focused tests.
- Added runtime and state-machine Mermaid diagrams and recorded the exact load-test command and interpretation limits.
- Verified locally on Python 3.15.1: Ruff clean, 61 tests passed, five simulation scenarios run, and 32/32 load reservations passed. GitHub CI remains unverified.
