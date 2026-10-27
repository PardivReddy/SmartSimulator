# Decisions

## D1. Python standard library and SQLite

The simulator has no runtime dependencies. SQLite supports local durable state and atomic allocation transactions without adding a service. It does not coordinate independent hosts.

## D2. Dataset is context, not runtime input

The extracted dataset describes historical synthetic records with intentionally inconsistent identifiers, duplicated events, mixed zones, and absent fields. Historical agent sessions do not establish current availability, and historical call outcomes do not establish causal effects. Simulation uses small synthetic IDs and seeded provider behavior instead of loading private records.

## D3. Predictive estimates cannot dial

`estimate_pacing` returns an offered-load proposal. The safety controller independently applies configuration, freshness, sample, provider health, and abandonment limits. The CLI uses the approved rate to bound a sample scenario; no real call initiation exists.

## D4. Answered and connected remain distinct

A borrower/provider answer does not by itself establish an agent-borrower connection. State transitions require an explicit `ANSWERED -> CONNECTED` event.

## D5. SHA-pinned CI actions

Checkout v7.0.1 and setup-python v7.1.0 are pinned to verified full commit hashes. These versions are current upstream releases checked during implementation; the trade-off is explicit update work when upstream versions change. Checkout does not persist credentials. CI has read-only repository permission and no secrets.

## D6. Locked development dependencies

`uv.lock` records exact development and build dependency versions and artifact hashes. CI installs a pinned uv version and runs with `--locked`, so dependency drift cannot silently rewrite the lockfile during checks.
