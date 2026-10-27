# Interview demonstration (about five minutes)

1. Explain that the application is a local-only collections dialer simulator. It never calls a phone number and every result is marked simulated.
2. Show the agent and call transition graphs. Demonstrate that a provider answer is separate from an established agent-borrower connection.
3. Run `python -m smartdialer.cli simulate --mode progressive --agents 4 --borrowers 20 --seed 42` and explain priority allocation and one-call-per-agent reservations.
4. Run the same command with `--mode predictive`. Explain that the estimator proposes a rate and the safety controller independently caps or pauses it.
5. Show two mock providers and seeded replay. Describe SQLite immediate transactions, event IDs, sequence ordering, and the multi-connection contention test.
6. Close with limitations: the pacing formula is illustrative, no real-time worker/telephony adapter exists, local SQLite is not distributed coordination, and dataset history cannot prove live availability or causal performance.
