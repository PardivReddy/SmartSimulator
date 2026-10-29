# Changelog

## 0.1.0 – project foundation and simulator prototype

- Replaced malformed ignore-file content with project data and Python artifact safeguards.
- Added explicit agent/call states, SQLite reservation and event storage, seeded mock providers, pacing proposal and safety gate, simulation CLI, and initial tests.
- Added repository, architecture, reliability, dataset, project planning, and CI documentation.
- Assignment PDF remains unavailable; simulator behavior follows the supplied master prompt.

## Audit follow-up

- Added a dependency-light threaded SQLite reservation load test and focused tests.
- Added runtime and state-machine Mermaid diagrams and recorded the exact load-test command and interpretation limits.
- Historical verification snapshots: 61 tests passed in an earlier audit (exact date and revision not recorded), followed by 103 tests passed on 2026-10-28 on Python 3.15.1 (tested revision not recorded). A later supplied final-correctness report states 107 full-suite and 53 focused tests passed, with Ruff lint, Ruff format, and `git diff --check` passing; those results were not independently rerun during this documentation cleanup, and the tested revision was not recorded. GitHub CI remains unverified.
