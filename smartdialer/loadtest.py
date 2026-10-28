"""Small local concurrency smoke test for SQLite reservations."""

from __future__ import annotations

import random
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from smartdialer.storage import Store


def run_load_test(
    *, agents: int = 32, borrowers: int = 32, workers: int = 16, seed: int = 42
) -> dict[str, int | float | str]:
    """Race independent SQLite connections to reserve synthetic borrowers once each."""
    if agents < 1 or borrowers < 1 or workers < 1:
        raise ValueError("agents, borrowers, and workers must be positive")
    if max(agents, borrowers, workers) > 1000:
        raise ValueError("basic load-test parameters are capped at 1000")

    worker_count = min(workers, agents)
    generator = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="smartdialer-load-") as temp_dir:
        database = Path(temp_dir) / "load.sqlite3"
        setup = Store(database)
        for index in range(agents):
            setup.add_agent(f"load-agent-{index:05d}")
        priorities = list(range(borrowers))
        generator.shuffle(priorities)
        for index, priority in enumerate(priorities):
            setup.add_borrower(f"load-borrower-{index:05d}", priority=priority)
        setup.close()

        start_barrier = threading.Barrier(worker_count)

        def reserve(agent_index: int) -> dict | None:
            store = Store(database)
            try:
                if agent_index < worker_count:
                    start_barrier.wait(timeout=10)
                return store.allocate(f"load-agent-{agent_index:05d}", now=0.0)
            finally:
                store.close()

        expected = min(agents, borrowers)
        began = time.perf_counter()
        errors = 0
        reservations: list[dict] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(reserve, index) for index in range(agents)]
            for future in futures:
                try:
                    result = future.result()
                    if result is not None:
                        reservations.append(result)
                except Exception:
                    errors += 1
        elapsed = max(time.perf_counter() - began, 1e-9)

    borrower_ids = [reservation["borrower_id"] for reservation in reservations]
    duplicates = len(borrower_ids) - len(set(borrower_ids))
    passed = len(reservations) == expected and duplicates == 0 and errors == 0
    return {
        "label": "LOCAL_SYNTHETIC_LOAD_TEST",
        "result": "PASS" if passed else "FAIL",
        "seed": seed,
        "agents": agents,
        "borrowers": borrowers,
        "workers": worker_count,
        "expected_reservations": expected,
        "reservations": len(reservations),
        "duplicate_borrower_reservations": duplicates,
        "worker_errors": errors,
        "elapsed_seconds": elapsed,
        "reservations_per_second": len(reservations) / elapsed,
    }
