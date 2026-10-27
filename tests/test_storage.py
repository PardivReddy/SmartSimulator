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


def test_recovery_requeues_abandoned_work_with_bounded_attempts():
    store = populated_store()
    call = store.allocate("agent-a", now=1)
    assert store.recover() == 1
    assert store.call(call["id"])["state"] == "QUEUED"
    assert store.recover() == 0
    assert store.call(call["id"])["state"] == "FAILED"


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
