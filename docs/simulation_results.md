# SmartDialer Simulation Results

Deterministic runs executed via CLI (`python -m smartdialer.cli simulate --scenario ... --seed 42`):

### Scenario A (Seed 42)
```text
==========================================================================
SCENARIO: A | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 59.83%
Calls Initiated                        | 183
Calls Connected                        | 35
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 2/162/75/1
Stranded Calls (Target: 0)             | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] proposed 150: free=30, answer_rate=0.20 (window=50), in_flight=0 -> ceil(30/0.20)=150
  [Pacing] [t=2s] proposed 141: free=21, answer_rate=0.05 (window=50), in_flight=0 -> ceil(21/0.05)=420
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] paused: no available agents
==========================================================================
```

### Scenario B (Seed 42)
```text
==========================================================================
SCENARIO: B | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 66.49%
Calls Initiated                        | 117
Calls Connected                        | 58
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 0/154/85/1
Stranded Calls (Target: 0)             | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] proposed 60: free=30, answer_rate=0.50 (window=50), in_flight=0 -> ceil(30/0.50)=60
  [Pacing] [t=2s] proposed 134: free=14, answer_rate=0.05 (window=50), in_flight=0 -> ceil(14/0.05)=280
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] paused: no available agents
==========================================================================
```

### Scenario C (Seed 42)
```text
==========================================================================
SCENARIO: C | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 93.07%
Calls Initiated                        | 70
Calls Connected                        | 53
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 0/54/183/3
Stranded Calls (Target: 0)             | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] proposed 43: free=30, answer_rate=0.70 (window=50), in_flight=0 -> ceil(30/0.70)=43
  [Pacing] [t=2s] proposed 9: free=6, answer_rate=0.70 (window=50), in_flight=0 -> ceil(6/0.70)=9
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] paused: no available agents
==========================================================================
```

### Scenario D (Seed 42)
```text
==========================================================================
SCENARIO: D | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 77.62%
Calls Initiated                        | 52
Calls Connected                        | 40
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 49/7/183/1
Stranded Calls (Target: 0)             | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] proposed 58: free=40, answer_rate=0.70 (window=50), in_flight=0 -> ceil(40/0.70)=58
  [Pacing] [t=2s] proposed 171: free=11, answer_rate=0.05 (window=50), in_flight=0 -> ceil(11/0.05)=220
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] paused: no available agents
==========================================================================
```

### Scenario agent-drop (Seed 42)
```text
==========================================================================
SCENARIO: agent-drop | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 68.80%
Calls Initiated                        | 439
Calls Connected                        | 219
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 0/152/87/1
Stranded Calls (Target: 0)             | 0
Adjustment Latency (ticks)             | 1 tick(s)
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] proposed 200: free=100, answer_rate=0.50 (window=50), in_flight=0 -> ceil(100/0.50)=200
  [Pacing] [t=2s] proposed 250: free=50, answer_rate=0.05 (window=50), in_flight=0 -> ceil(50/0.05)=1000
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] paused: no available agents
==========================================================================
```

### Scenario outage (Seed 42)
```text
==========================================================================
SCENARIO: outage | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 66.49%
Calls Initiated                        | 117
Calls Connected                        | 58
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 0/154/85/1
Stranded Calls (Target: 0)             | 0
New Calls Blocked During Outage        | YES (0 placed)
Retries Scheduled During Outage        | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] proposed 60: free=30, answer_rate=0.50 (window=50), in_flight=0 -> ceil(30/0.50)=60
  [Pacing] [t=2s] proposed 134: free=14, answer_rate=0.05 (window=50), in_flight=0 -> ceil(14/0.05)=280
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] paused: no available agents
==========================================================================
```

