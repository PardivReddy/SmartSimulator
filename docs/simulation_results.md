# SmartDialer Simulation Results

Deterministic runs executed via CLI (`python -m smartdialer.cli simulate --scenario ... --seed 42`):

### Scenario A (Seed 42)
```text
==========================================================================
SCENARIO: A | Seed: 42 | Duration: 240s
==========================================================================
Metric                                 | Value                         
---------------------------------------+-------------------------------
Agent Utilization                      | 94.97%
Calls Initiated                        | 314
Calls Connected                        | 60
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 0/72/0/12
Stranded Calls (Target: 0)             | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] window=0/50 < 10 -> using prior 0.50, raw=ceil(30/0.50)=60 -> proposed 60
  [Pacing] [t=2s] window=21/50, raw=ceil(21/0.01)=2100, capped to 141 by pending_calls=141 -> proposed 141
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] idle: no available agents
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
Agent Utilization                      | 98.89%
Calls Initiated                        | 80
Calls Connected                        | 60
Abandoned Connected Calls              | 0
Pacing Proposals Evaluated             | 240
Safety (Approve/Red/Rej/FB)            | 0/3/0/7
Stranded Calls (Target: 0)             | 0
--------------------------------------------------------------------------
Sample Reason Lines:
  [Pacing] [t=0s] window=0/50 < 10 -> using prior 0.50, raw=ceil(30/0.50)=60 -> proposed 60
  [Pacing] [t=2s] window=6/50 < 10 -> using prior 0.50, raw=ceil(6/0.50)=12 -> proposed 12
  [Safety] [t=0s] fallback to progressive: sample size 0 < min 10
  [Safety] [t=1s] idle: no available agents
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

