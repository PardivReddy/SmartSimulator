# SmartDialer Simulation Results

These are deterministic local simulator results recorded on 2026-10-28. They
are not production measurements and were not rerun during this documentation
update; the exact source revision was not recorded. The scenario runner uses a
240-second, one-second-tick run, an in-memory SQLite database, and two seeded
mock providers.
The commands below use seed 42; scenario profiles set their own agent and borrower
counts, answer probabilities, and talk times (the general CLI `--agents` and
`--borrowers` options do not override those profiles).

## Metric and outcome definitions

- **Initiated** is the discrete-time runner's counter for newly allocated calls
  started in its main dialing loop. It does not necessarily include later
  initiation events for retries; use it as that runner's start counter, not as a
  total provider-attempt count.
- **Connected** counts calls for which an answer was followed by an available
  agent claim and a connection event. It is not the same as answered or completed.
- **Unanswered** calls receive a `FAILED` state with a `NO_ANSWER` reason in the
  scenario runner. No separate unanswered total is reported in the results table.
- **Failed** is a persisted call state that can include `NO_ANSWER` as well as
  provider failures or timeouts. The scenario results table does not report a
  separate failed-call count or breakdown by reason.
- **Abandoned** in this scenario runner means an answered predictive call could
  not claim an available agent and was recorded as `ABANDONED_NO_AGENT`. It does
  not mean unanswered or provider-failed. The reported counts do not include a
  separate cancellation total.
- **Pending borrowers** are eligible borrowers without a call in an active state
  at the time the runner calculates pacing. Calls still in nonterminal states,
  such as ringing, retry wait, or uncertain, are separate outstanding work. The
  archived scenario table reports neither a final pending-borrower count nor a
  total of outstanding calls, so neither is inferred here.
- **Retried** work reuses the same call record after a failure and backoff. The
  discrete-time runner processes due retries separately from its main
  `calls_initiated` counter; therefore the table's initiated value does not
  necessarily count retry initiations. The dedicated provider-outage flow reports
  its attempts and retry counts separately below.

## Reproducible scenario runs

Run from the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario A --seed 42
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario B --seed 42
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario C --seed 42
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario D --seed 42
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario agent-drop --seed 42
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario outage --seed 42
```

| Scenario | Agents / borrowers | Answer probability and talk time | Additional setting |
|---|---:|---|---|
| A | 30 / 150 | 20% / 120 s | — |
| B | 30 / 150 | 50% / 90 s | — |
| C | 30 / 150 | 70% / 180 s | — |
| D | 40 / 200 | 70% / 180 s initially | At t=120 s, answer probability changes to 10% and talk time to 60 s |
| agent-drop | 100 / 300 | 50% / 90 s | Agents 60–99 are taken offline at t=30 s |
| outage | 30 / 150 | 50% / 90 s | Both mock providers are unavailable from t=40 s through t=79 s |

Recorded output from those commands (not independently reverified in this
documentation update):

| Scenario | Agent utilization | Initiated | Connected | Abandoned | Safety decisions: approve / reduce / reject / pause / fallback | Stranded | Additional result |
|---|---:|---:|---:|---:|---|---:|---|
| A | 91.35% | 312 | 58 | 1 | 0 / 223 / 0 / 0 / 14 | 0 | — |
| B | 92.57% | 176 | 87 | 1 | 0 / 166 / 0 / 0 / 12 | 0 | — |
| C | 95.75% | 80 | 59 | 1 | 0 / 173 / 0 / 0 / 4 | 0 | — |
| D | 90.52% | 487 | 76 | 0 | 0 / 233 / 0 / 0 / 3 | 0 | Answer rate dropped at t=120 s; no no-agent abandonment occurred |
| agent-drop | 93.33% | 599 | 295 | 1 | 0 / 149 / 0 / 0 / 4 | 0 | Adjustment latency: 1 tick |
| outage | 92.42% | 176 | 87 | 1 | 0 / 133 / 0 / 40 / 13 | 0 | 0 new calls placed and 0 retries scheduled during the outage |

Safety counts are recorded actions during the run; idle decisions are not included
in these action counts. The `outage` scenario is the 240-second scenario-runner
profile. Its zero new calls during the outage reflects the providers being
unavailable; it scheduled no retries in this particular seeded run.

The D run did not produce an abandoned answer after its answer-rate reduction.
`ABANDONED_NO_AGENT` is counted only when a call is answered and no free agent can
be atomically claimed. The reduced answer rate and the available-agent capacity in
this seeded run did not produce that condition. This result is reported as observed;
the scenario is not forced to create an abandonment.

### Dedicated provider-outage flow

The CLI also has a separate `provider_outage` path, distinct from the 240-second
`outage` profile above. It uses explicit 4-agent/20-borrower inputs and seed 42:

```powershell
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --scenario provider_outage --agents 4 --borrowers 20 --seed 42
```

Recorded local result: 3 calls attempted, 1 failure, 1 timeout, 1 retry scheduled,
1 new call blocked during the outage, and 1 retry deferred while the provider was
unavailable. The Safety action was `PAUSE` with `provider_health_limit` and an
approved rate of 0 calls/minute. The retry was not due before its 5-second backoff,
was deferred during the outage, then completed after provider recovery.

## Progressive-versus-predictive comparison

The current CLI can run both modes through the same legacy batch runner with the
same seed, agent and borrower counts, and simulated time. These matching-input
single runs are reproducible but too small to establish general performance:

```powershell
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --mode progressive --agents 4 --borrowers 20 --seed 42
.\.venv\Scripts\python.exe -m smartdialer.cli simulate --mode predictive --agents 4 --borrowers 20 --seed 42
```

| Metric | Progressive | Predictive |
|---|---:|---:|
| Calls attempted | 4 | 1 |
| Connected | 3 | 1 |
| Failed | 1 | 0 |
| Connection rate | 75% | 100% |
| Agent utilization | 100% | 27.19% |
| Simulated throughput | 3.00 calls/min | 0.75 calls/min |
| Safety interventions | 0 | 1 |

Both runs use 4 agents, 20 borrowers, seed 42, and 80 simulated seconds. The
predictive runner converts the approved pacing rate into a discrete batch, which
produces only one attempt here. These are comparable inputs, but one run per mode
does not provide a statistically meaningful estimate or demonstrate predictive
superiority. Utilization and throughput also reflect this runner's simplified
elapsed-time accounting.

## Assignment design recommendation

Use Progressive dialing as the deterministic baseline and fallback, while enabling
predictive pacing only as a bounded overlay when provider health and a sufficiently
large, fresh answer-rate sample pass Safety checks. Cap approved starts and
concurrency, and tighten the abandonment limit so Safety reduces pacing and then
falls back to Progressive when risk rises. Predictive calls can reserve a borrower
without reserving an agent; at `ANSWERED`, atomically claim one available agent.
If none is available, record `ABANDONED_NO_AGENT` and include it in the abandonment
metric. This retains predictive utilization opportunities within explicit risk
limits without weakening Progressive's one-agent-per-call safety behavior.
