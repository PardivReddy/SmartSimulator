import threading

from smartdialer.storage import Store


def populated_store(path=":memory:"):
    store = Store(path)
    store.add_agent("agent-a")
    store.add_agent("agent-b")
    store.add_borrower("borrower-a", 10)
    store.add_borrower("borrower-b", 5)
    return store


def test_progressive_allocation_priority_and_single_active_call():
    store = populated_store()
    first = store.allocate("agent-a", now=1)
    assert first["borrower_id"] == "borrower-a"
    assert store.allocate("agent-a", now=2) is None
    second = store.allocate("agent-b", now=2)
    assert second["borrower_id"] == "borrower-b"


def test_unavailable_agent_is_never_allocated():
    store = populated_store()
    store.set_agent_state("agent-a", "PAUSED")
    assert store.allocate("agent-a") is None
    skipped = store._connection.execute(
        "SELECT detail FROM event_history WHERE kind='ALLOCATION_SKIPPED'"
    ).fetchone()
    assert skipped["detail"] == "agent_unavailable"


def test_ineligible_borrower_is_skipped():
    store = Store()
    store.add_agent("agent-a")
    store.add_borrower("blocked", priority=100, eligible=False)
    store.add_borrower("eligible", priority=1)
    assert store.allocate("agent-a")["borrower_id"] == "eligible"


def test_event_idempotency_and_out_of_order_rejection():
    store = populated_store()
    call = store.allocate("agent-a", now=1)
    assert store.process_event(call["id"], "ev1", 1, "INITIATED", now=2) == "APPLIED"
    assert store.process_event(call["id"], "ev1", 1, "INITIATED", now=3) == "DUPLICATE"
    assert store.process_event(call["id"], "ev0", 0, "RINGING", now=4) == "STALE"
    assert store.process_event(call["id"], "ev2", 2, "COMPLETED", now=5) == "INVALID_TRANSITION"
    assert store.call(call["id"])["state"] == "INITIATED"


def test_event_state_machine_and_terminal_agent_release():
    store = populated_store()
    call = store.allocate("agent-a", now=1)
    for seq, state in enumerate(("INITIATED", "RINGING", "ANSWERED", "CONNECTED", "COMPLETED"), 1):
        assert store.process_event(call["id"], f"e{seq}", seq, state, now=seq + 1) == "APPLIED"
    store.transition_agent("agent-a", "AVAILABLE")
    assert store.allocate("agent-a", now=10) is not None


def test_recovery_requeues_only_reservations_that_never_reached_a_provider():
    store = populated_store()
    call = store.allocate("agent-a", now=1)
    assert store.recover() == 1
    assert store.call(call["id"])["state"] == "QUEUED"
    assert store.recover() == 0
    assert store.call(call["id"])["recovery_count"] == 1
    assert (
        store._connection.execute("SELECT state FROM agents WHERE id='agent-a'").fetchone()["state"]
        == "AVAILABLE"
    )
    resumed = store.claim_queued("agent-a", now=2)
    assert resumed["id"] == call["id"]
    assert resumed["borrower_id"] == "borrower-a"
    next_call = store.allocate("agent-b", now=2)
    assert next_call["borrower_id"] == "borrower-b"
    assert (
        store._connection.execute(
            "SELECT COUNT(*) FROM calls WHERE borrower_id='borrower-a'"
        ).fetchone()[0]
        == 1
    )


def test_recovery_quarantines_provider_started_call_until_late_completion():
    store = populated_store()
    call = store.allocate("agent-a", now=1)
    for sequence, state in enumerate(
        ("INITIATED", "RINGING", "ANSWERED", "CONNECTED"),
        start=1,
    ):
        assert (
            store.process_event(
                call["id"],
                f"evt-{sequence}",
                sequence,
                state,
                now=sequence,
                provider="mock",
            )
            == "APPLIED"
        )

    assert store.recover() == 0
    recovered = store.call(call["id"])
    assert recovered["state"] == "UNCERTAIN"
    assert recovered["recovery_count"] == 1
    assert (
        store._connection.execute("SELECT state FROM agents WHERE id='agent-a'").fetchone()["state"]
        == "PAUSED"
    )
    assert store.allocate("agent-a", now=10) is None
    assert store.allocate("agent-b", now=10)["borrower_id"] == "borrower-b"

    assert (
        store.process_event(
            call["id"],
            "evt-5",
            5,
            "COMPLETED",
            now=11,
            provider="mock",
        )
        == "APPLIED"
    )
    assert store.call(call["id"])["state"] == "COMPLETED"
    assert (
        store._connection.execute("SELECT state FROM agents WHERE id='agent-a'").fetchone()["state"]
        == "WRAP_UP"
    )


def test_provider_event_identity_is_scoped_by_provider():
    store = populated_store()
    first = store.allocate("agent-a", now=1)
    second = store.allocate("agent-b", now=1)

    assert (
        store.process_event(first["id"], "same-id", 1, "INITIATED", provider="north") == "APPLIED"
    )
    assert (
        store.process_event(second["id"], "same-id", 1, "INITIATED", provider="south") == "APPLIED"
    )
    assert store.call(first["id"])["state"] == "INITIATED"
    assert store.call(second["id"])["state"] == "INITIATED"


def test_provider_events_migrate_with_call_foreign_key(tmp_path):
    database = tmp_path / "events-migration.sqlite3"
    store = populated_store(database)
    call = store.allocate("agent-a", now=1)
    store._connection.execute("DROP TABLE events")
    store._connection.execute(
        """CREATE TABLE events(
             provider TEXT NOT NULL, event_id TEXT NOT NULL, call_id TEXT NOT NULL,
             seq INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
             received_at REAL NOT NULL, PRIMARY KEY(provider,event_id),
             UNIQUE(call_id,provider,seq)
           )"""
    )
    store._connection.execute(
        """INSERT INTO events
           (provider,event_id,call_id,seq,kind,payload,received_at)
           VALUES('north','legacy',?,1,'INITIATED','{}',2)""",
        (call["id"],),
    )
    store.close()

    migrated = Store(database)
    event = migrated._connection.execute("SELECT provider,event_id,call_id FROM events").fetchone()
    foreign_keys = migrated._connection.execute("PRAGMA foreign_key_list(events)").fetchall()
    assert tuple(event) == ("north", "legacy", call["id"])
    assert any(row["table"] == "calls" and row["from"] == "call_id" for row in foreign_keys)
    assert (
        migrated.process_event(
            call["id"],
            "legacy",
            1,
            "INITIATED",
            provider="north",
        )
        == "DUPLICATE"
    )
    migrated.close()


def test_legacy_provider_events_migrate_into_default_provider_scope(tmp_path):
    database = tmp_path / "legacy-events.sqlite3"
    store = populated_store(database)
    call = store.allocate("agent-a", now=1)
    store._connection.execute("DROP TABLE events")
    store._connection.execute(
        """CREATE TABLE events(
             event_id TEXT PRIMARY KEY, call_id TEXT NOT NULL, seq INTEGER NOT NULL,
             kind TEXT NOT NULL, payload TEXT NOT NULL, received_at REAL NOT NULL,
             UNIQUE(call_id,seq)
           )"""
    )
    store._connection.execute(
        """INSERT INTO events
           (event_id,call_id,seq,kind,payload,received_at)
           VALUES('legacy',?,1,'INITIATED','{}',2)""",
        (call["id"],),
    )
    store.close()

    migrated = Store(database)
    event = migrated._connection.execute("SELECT provider,event_id FROM events").fetchone()
    assert tuple(event) == ("default", "legacy")
    assert (
        migrated.process_event(
            call["id"],
            "legacy",
            1,
            "INITIATED",
            provider="default",
        )
        == "DUPLICATE"
    )
    migrated.close()


def test_unknown_or_invalid_event_has_no_partial_writes():
    store = populated_store()
    call = store.allocate("agent-a", now=1)
    event_count = store._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    assert store.process_event("missing", "unknown", 1, "INITIATED") == "UNKNOWN_CALL"
    assert store.process_event(call["id"], "invalid", 1, "CONNECTED") == "INVALID_TRANSITION"
    assert store.call(call["id"])["state"] == "RESERVED"
    assert store._connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == event_count
    assert (
        store._connection.execute("SELECT state FROM agents WHERE id='agent-a'").fetchone()["state"]
        == "RESERVED"
    )


def test_competing_transitions_require_the_observed_state(tmp_path):
    database = tmp_path / "transition-race.sqlite3"
    setup = Store(database)
    setup.add_agent("agent-a")
    setup.add_borrower("borrower-a")
    call = setup.allocate("agent-a", now=1)
    assert setup.transition_call(call["id"], "INITIATED", now=2)
    setup.close()

    barrier = threading.Barrier(2)
    results = []

    def transition_call(target):
        store = Store(database)
        try:
            barrier.wait(timeout=10)
            results.append(
                store.transition_call(
                    call["id"],
                    target,
                    now=3,
                    expected_state="INITIATED",
                )
            )
        finally:
            store.close()

    threads = [
        threading.Thread(target=transition_call, args=(target,)) for target in ("RINGING", "FAILED")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results) == 1
    verify = Store(database)
    assert verify.call(call["id"])["state"] in {"RINGING", "FAILED"}
    verify.close()


def test_provider_retry_waits_for_backoff_and_stops_at_retry_limit():
    store = Store()
    store.add_agent("agent-a")
    store.add_borrower("borrower-a")
    call = store.allocate("agent-a", now=1)
    store.transition_call(call["id"], "INITIATED", now=2)
    store.transition_call(call["id"], "RINGING", now=3)
    store.transition_call(call["id"], "FAILED", reason="provider_timeout", now=4)

    assert store.schedule_retry(call["id"], retry_at=9, max_retries=1, now=4)
    assert store.claim_retry(call["id"], now=8) is None
    retry = store.claim_retry(call["id"], now=9)
    assert retry["borrower_id"] == "borrower-a"
    assert retry["agent_id"] == "agent-a"
    store.transition_call(call["id"], "INITIATED", now=10)
    store.transition_call(call["id"], "RINGING", now=11)
    store.transition_call(call["id"], "FAILED", reason="provider_timeout", now=12)

    assert not store.schedule_retry(call["id"], retry_at=17, max_retries=1, now=12)
    assert store.call(call["id"])["state"] == "FAILED"
    assert store.call(call["id"])["retry_count"] == 1
    assert store._connection.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1


def test_non_provider_failure_is_not_eligible_for_retry():
    store = Store()
    store.add_agent("agent-a")
    store.add_borrower("borrower-a")
    call = store.allocate("agent-a", now=1)
    store.transition_call(call["id"], "INITIATED", now=2)
    store.transition_call(call["id"], "RINGING", now=3)
    store.transition_call(call["id"], "FAILED", reason="NO_ANSWER", now=4)

    assert not store.schedule_retry(call["id"], retry_at=9, max_retries=1, now=4)
    assert store.call(call["id"])["state"] == "FAILED"
    assert store.call(call["id"])["retry_count"] == 0


def test_competing_retry_claims_reserve_only_one_agent(tmp_path):
    database = tmp_path / "retry-race.sqlite3"
    setup = Store(database)
    setup.add_agent("agent-a")
    setup.add_agent("agent-b")
    setup.add_borrower("borrower-a")
    call = setup.allocate("agent-a", now=1)
    setup.transition_call(call["id"], "INITIATED", now=2)
    setup.transition_call(call["id"], "RINGING", now=3)
    setup.transition_call(call["id"], "FAILED", reason="provider_timeout", now=4)
    assert setup.schedule_retry(call["id"], retry_at=5, max_retries=1, now=4)
    setup.close()

    barrier = threading.Barrier(2)
    results = []

    def claim_retry():
        store = Store(database)
        try:
            barrier.wait(timeout=10)
            results.append(store.claim_retry(call["id"], now=5))
        finally:
            store.close()

    threads = [threading.Thread(target=claim_retry) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(result is not None for result in results) == 1
    verify = Store(database)
    assert verify.call(call["id"])["state"] == "RESERVED"
    assert (
        verify._connection.execute("SELECT COUNT(*) FROM agents WHERE state='RESERVED'").fetchone()[
            0
        ]
        == 1
    )
    assert verify._connection.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 1
    verify.close()


def test_competing_connections_cannot_double_allocate(tmp_path):
    database = tmp_path / "race.sqlite3"
    seed_store = populated_store(database)
    seed_store._connection.execute("DELETE FROM borrowers WHERE id='borrower-b'")
    seed_store.close()
    barrier = threading.Barrier(2)
    results = []

    def allocate(agent_id):
        store = Store(database)
        barrier.wait()
        results.append(store.allocate(agent_id, now=1))
        store.close()

    threads = [threading.Thread(target=allocate, args=(agent,)) for agent in ("agent-a", "agent-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(result is not None for result in results) == 1


def test_state_and_event_history_survive_reopen(tmp_path):
    database = tmp_path / "durable.sqlite3"
    store = Store(database)
    store.add_agent("agent-a")
    store.add_borrower("borrower-a")
    call = store.allocate("agent-a", now=1)
    store.close()

    reopened = Store(database)
    assert reopened.call(call["id"])["state"] == "RESERVED"
    assert reopened.event_count() == 1
    reopened.close()


def test_concurrent_reservation_of_one_agent_by_n_workers(tmp_path):
    database = tmp_path / "single-agent-race.sqlite3"
    setup = Store(database)
    setup.add_agent("target-agent")
    for i in range(10):
        setup.add_borrower(f"borrower-{i}", priority=10 - i)
    setup.close()

    workers = 8
    barrier = threading.Barrier(workers)
    allocations = []

    def worker_race():
        store = Store(database)
        try:
            barrier.wait(timeout=5)
            res = store.allocate("target-agent", now=1.0)
            allocations.append(res)
        finally:
            store.close()

    threads = [threading.Thread(target=worker_race) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successful = [a for a in allocations if a is not None]
    assert len(successful) == 1
    assert successful[0]["agent_id"] == "target-agent"
    assert successful[0]["borrower_id"] == "borrower-0"

    verify = Store(database)
    agent = verify._connection.execute(
        "SELECT state FROM agents WHERE id='target-agent'"
    ).fetchone()
    assert agent["state"] == "RESERVED"
    calls = verify._connection.execute(
        "SELECT COUNT(*) FROM calls WHERE agent_id='target-agent'"
    ).fetchone()[0]
    assert calls == 1
    verify.close()


def test_crash_recovery_at_all_three_points():
    store = Store()
    store.add_agent("agent-pt1")
    store.add_agent("agent-pt2")
    store.add_agent("agent-pt3")
    store.add_borrower("borrower-pt2", priority=10)
    store.add_borrower("borrower-pt3", priority=5)

    # Point 1: Agent reserved, but crashed before borrower or call was recorded
    store._connection.execute("UPDATE agents SET state='RESERVED' WHERE id='agent-pt1'")

    # Point 2: Borrower and agent reserved (call in RESERVED, pre-provider)
    call_pt2 = store.allocate("agent-pt2", now=1.0)
    assert call_pt2 is not None

    # Point 3: Call initiated to provider (provider outcome in-flight)
    call_pt3 = store.allocate("agent-pt3", now=2.0)
    assert call_pt3 is not None
    assert store.process_event(call_pt3["id"], "evt-init", 1, "INITIATED", now=2.5) == "APPLIED"

    # Execute Crash Recovery
    requeued = store.recover()
    assert requeued == 1  # only Point 2 is requeued to QUEUED

    # Verify Point 1: orphan reserved agent safely restored to AVAILABLE
    agent1 = store._connection.execute("SELECT state FROM agents WHERE id='agent-pt1'").fetchone()
    assert agent1["state"] == "AVAILABLE"

    # Verify Point 2: pre-provider reservation requeued, agent AVAILABLE
    c2 = store.call(call_pt2["id"])
    assert c2["state"] == "QUEUED"
    assert c2["recovery_count"] == 1
    agent2 = store._connection.execute("SELECT state FROM agents WHERE id='agent-pt2'").fetchone()
    assert agent2["state"] == "AVAILABLE"

    # Verify Point 3: in-flight provider call quarantined to UNCERTAIN, agent PAUSED
    c3 = store.call(call_pt3["id"])
    assert c3["state"] == "UNCERTAIN"
    assert c3["recovery_count"] == 1
    agent3 = store._connection.execute("SELECT state FROM agents WHERE id='agent-pt3'").fetchone()
    assert agent3["state"] == "PAUSED"


def test_duplicate_and_out_of_order_events_comprehensive():
    store = Store()
    store.add_agent("agent-x")
    store.add_borrower("borrower-x")
    call = store.allocate("agent-x", now=1.0)
    cid = call["id"]

    # 1. Initiated
    assert store.process_event(cid, "ev-1", 1, "INITIATED", now=2.0) == "APPLIED"
    assert store.call(cid)["state"] == "INITIATED"

    # 2. Duplicate event
    assert store.process_event(cid, "ev-1", 1, "INITIATED", now=2.1) == "DUPLICATE"
    assert store.call(cid)["state"] == "INITIATED"

    # 3. Out-of-order sequence regression (seq 0 after seq 1)
    assert store.process_event(cid, "ev-0", 0, "RINGING", now=2.2) == "STALE"
    assert store.call(cid)["state"] == "INITIATED"

    # 4. Out-of-order state leap: COMPLETED before ANSWERED
    assert store.process_event(cid, "ev-2", 2, "COMPLETED", now=2.3) == "INVALID_TRANSITION"
    assert store.call(cid)["state"] == "INITIATED"

    # 5. Proper sequence: RINGING -> ANSWERED -> CONNECTED
    assert store.process_event(cid, "ev-3", 3, "RINGING", now=3.0) == "APPLIED"
    assert store.process_event(cid, "ev-4", 4, "ANSWERED", now=4.0) == "APPLIED"
    assert store.process_event(cid, "ev-5", 5, "CONNECTED", now=4.5) == "APPLIED"
    assert store.call(cid)["state"] == "CONNECTED"

    # 6. Out-of-order: RINGING after CONNECTED
    assert store.process_event(cid, "ev-6", 6, "RINGING", now=5.0) == "INVALID_TRANSITION"
    assert store.call(cid)["state"] == "CONNECTED"
