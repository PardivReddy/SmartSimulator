"""SQLite persistence with atomic, cross-connection allocation."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._connection.execute("PRAGMA foreign_keys=ON")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents(
              id TEXT PRIMARY KEY, state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS borrowers(
              id TEXT PRIMARY KEY, priority INTEGER NOT NULL, eligible INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS calls(
              id TEXT PRIMARY KEY, borrower_id TEXT NOT NULL REFERENCES borrowers(id),
              agent_id TEXT REFERENCES agents(id), state TEXT NOT NULL,
              created_at REAL NOT NULL, updated_at REAL NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              provider TEXT, reason TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0, retry_at REAL,
              recovery_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS calls_state ON calls(state);
            CREATE TABLE IF NOT EXISTS event_history(
              id INTEGER PRIMARY KEY AUTOINCREMENT, call_id TEXT, kind TEXT NOT NULL,
              detail TEXT NOT NULL, occurred_at REAL NOT NULL
            );
            """
        )
        call_columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(calls)")}
        if "retry_count" not in call_columns:
            self._connection.execute(
                "ALTER TABLE calls ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"
            )
        if "retry_at" not in call_columns:
            self._connection.execute("ALTER TABLE calls ADD COLUMN retry_at REAL")
        if "recovery_count" not in call_columns:
            self._connection.execute(
                "ALTER TABLE calls ADD COLUMN recovery_count INTEGER NOT NULL DEFAULT 0"
            )
        event_info = self._connection.execute("PRAGMA table_info(events)").fetchall()
        event_columns = {row["name"] for row in event_info}
        if not event_columns:
            self._connection.execute(
                """CREATE TABLE events(
                     provider TEXT NOT NULL, event_id TEXT NOT NULL,
                     call_id TEXT NOT NULL REFERENCES calls(id),
                     seq INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                     received_at REAL NOT NULL, PRIMARY KEY(provider,event_id),
                     UNIQUE(call_id,provider,seq)
                   )"""
            )
        else:
            event_foreign_keys = self._connection.execute(
                "PRAGMA foreign_key_list(events)"
            ).fetchall()
            if "provider" not in event_columns or not any(
                row["table"] == "calls" and row["from"] == "call_id" for row in event_foreign_keys
            ):
                provider_column = "provider" if "provider" in event_columns else "'default'"
                self._migrate_events_table(provider_column)

    def _migrate_events_table(self, provider_column: str) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    """CREATE TABLE events_migrated(
                         provider TEXT NOT NULL, event_id TEXT NOT NULL,
                         call_id TEXT NOT NULL REFERENCES calls(id),
                         seq INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
                         received_at REAL NOT NULL, PRIMARY KEY(provider,event_id),
                         UNIQUE(call_id,provider,seq)
                       )"""
                )
                self._connection.execute(
                    f"""INSERT INTO events_migrated
                       (provider,event_id,call_id,seq,kind,payload,received_at)
                       SELECT {provider_column},event_id,call_id,seq,kind,payload,received_at
                       FROM events"""
                )
                self._connection.execute("DROP TABLE events")
                self._connection.execute("ALTER TABLE events_migrated RENAME TO events")
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def close(self) -> None:
        self._connection.close()

    def add_agent(self, agent_id: str, state: str = "AVAILABLE") -> None:
        with self._connection:
            self._connection.execute("INSERT INTO agents(id,state) VALUES(?,?)", (agent_id, state))

    def set_agent_state(self, agent_id: str, state: str) -> None:
        if not self.transition_agent(agent_id, state):
            raise ValueError(f"Invalid agent state change for {agent_id}: {state}")

    def transition_agent(self, agent_id: str, state: str) -> bool:
        from smartdialer.domain import AGENT_TRANSITIONS, AgentState, InvalidTransition, transition

        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT state FROM agents WHERE id=?", (agent_id,)).fetchone()
                if row is None:
                    db.rollback()
                    return False
                try:
                    transition(AgentState(row["state"]), AgentState(state), AGENT_TRANSITIONS)
                except (InvalidTransition, ValueError):
                    db.rollback()
                    return False
                if state == "AVAILABLE":
                    active = db.execute(
                        """SELECT 1 FROM calls WHERE agent_id=? AND state IN
                           ('RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED','UNCERTAIN')""",
                        (agent_id,),
                    ).fetchone()
                    if active:
                        db.rollback()
                        return False
                updated = db.execute(
                    "UPDATE agents SET state=? WHERE id=? AND state=?",
                    (state, agent_id, row["state"]),
                ).rowcount
                if updated != 1:
                    db.rollback()
                    return False
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise

    def add_borrower(self, borrower_id: str, priority: int = 0, eligible: bool = True) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO borrowers(id,priority,eligible) VALUES(?,?,?)",
                (borrower_id, priority, int(eligible)),
            )

    def allocate(self, agent_id: str, now: float | None = None) -> dict | None:
        """Atomically reserve one available agent and highest-priority eligible borrower."""
        now = time.time() if now is None else now
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                agent = db.execute("SELECT state FROM agents WHERE id=?", (agent_id,)).fetchone()
                if not agent or agent["state"] != "AVAILABLE":
                    reason = "agent_missing" if agent is None else "agent_unavailable"
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(NULL,?,?,?)",
                        ("ALLOCATION_SKIPPED", reason, now),
                    )
                    db.commit()
                    return None
                borrower = db.execute(
                    """SELECT b.id,b.priority FROM borrowers b
                       WHERE b.eligible=1 AND NOT EXISTS
                       (SELECT 1 FROM calls c WHERE c.borrower_id=b.id AND c.state IN
                        ('QUEUED','RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED',
                         'RETRY_WAIT','UNCERTAIN'))
                       AND NOT EXISTS
                       (SELECT 1 FROM calls f WHERE f.borrower_id=b.id AND f.state='FAILED'
                        AND f.reason IN
                        ('provider_timeout','provider_unavailable','provider_failure'))
                       ORDER BY b.priority DESC,b.id LIMIT 1"""
                ).fetchone()
                if not borrower:
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(NULL,?,?,?)",
                        ("ALLOCATION_SKIPPED", "no_eligible_borrower", now),
                    )
                    db.commit()
                    return None
                active = db.execute(
                    "SELECT 1 FROM calls WHERE agent_id=? AND state IN "
                    "('RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED','UNCERTAIN')",
                    (agent_id,),
                ).fetchone()
                if active:
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(NULL,?,?,?)",
                        ("ALLOCATION_SKIPPED", "agent_has_active_call", now),
                    )
                    db.commit()
                    return None
                call_id = str(uuid.uuid4())
                db.execute(
                    "UPDATE agents SET state='RESERVED' WHERE id=? AND state='AVAILABLE'",
                    (agent_id,),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    return None
                db.execute(
                    "INSERT INTO calls(id,borrower_id,agent_id,state,created_at,updated_at) "
                    "VALUES(?,?,?,'RESERVED',?,?)",
                    (call_id, borrower["id"], agent_id, now, now),
                )
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, "ALLOCATED", "priority=" + str(borrower["priority"]), now),
                )
                db.commit()
                return {
                    "id": call_id,
                    "borrower_id": borrower["id"],
                    "agent_id": agent_id,
                    "state": "RESERVED",
                    "priority": borrower["priority"],
                }
            except Exception:
                db.rollback()
                raise

    def allocate_borrower(self, now: float | None = None) -> dict | None:
        """Atomically reserve highest-priority eligible borrower without binding an agent upfront."""
        now = time.time() if now is None else now
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                borrower = db.execute(
                    """SELECT b.id,b.priority FROM borrowers b
                       WHERE b.eligible=1 AND NOT EXISTS
                       (SELECT 1 FROM calls c WHERE c.borrower_id=b.id AND c.state IN
                        ('QUEUED','RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED',
                         'RETRY_WAIT','UNCERTAIN'))
                       AND NOT EXISTS
                       (SELECT 1 FROM calls f WHERE f.borrower_id=b.id AND f.state='FAILED'
                        AND f.reason IN
                        ('provider_timeout','provider_unavailable','provider_failure'))
                       ORDER BY b.priority DESC,b.id LIMIT 1"""
                ).fetchone()
                if not borrower:
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(NULL,?,?,?)",
                        ("ALLOCATION_SKIPPED", "no_eligible_borrower", now),
                    )
                    db.commit()
                    return None
                call_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO calls(id,borrower_id,agent_id,state,created_at,updated_at) "
                    "VALUES(?,?,NULL,'RESERVED',?,?)",
                    (call_id, borrower["id"], now, now),
                )
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, "BORROWER_ALLOCATED", "priority=" + str(borrower["priority"]), now),
                )
                db.commit()
                return {
                    "id": call_id,
                    "borrower_id": borrower["id"],
                    "agent_id": None,
                    "state": "RESERVED",
                    "priority": borrower["priority"],
                }
            except Exception:
                db.rollback()
                raise

    def claim_agent_for_call(self, call_id: str, *, now: float | None = None) -> str | None:
        """Atomically claim one available agent for an answered predictive call."""
        now = time.time() if now is None else now
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                call = db.execute(
                    "SELECT state,agent_id FROM calls WHERE id=?", (call_id,)
                ).fetchone()
                if not call:
                    db.rollback()
                    return None
                if call["agent_id"] is not None:
                    db.rollback()
                    return str(call["agent_id"])
                agent = db.execute(
                    "SELECT id FROM agents WHERE state='AVAILABLE' ORDER BY id LIMIT 1"
                ).fetchone()
                if not agent:
                    db.rollback()
                    return None
                changed = db.execute(
                    "UPDATE agents SET state='CONNECTED' WHERE id=? AND state='AVAILABLE'",
                    (agent["id"],),
                ).rowcount
                if changed != 1:
                    db.rollback()
                    return None
                db.execute(
                    "UPDATE calls SET agent_id=?, updated_at=? WHERE id=?",
                    (agent["id"], now, call_id),
                )
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, "AGENT_CLAIMED_ON_ANSWER", f"agent={agent['id']}", now),
                )
                db.commit()
                return str(agent["id"])
            except Exception:
                db.rollback()
                raise

    def call(self, call_id: str) -> dict | None:
        row = self._connection.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
        return dict(row) if row else None

    def transition_call(
        self,
        call_id: str,
        state: str,
        *,
        provider: str | None = None,
        reason: str | None = None,
        now: float | None = None,
        expected_state: str | None = None,
    ) -> bool:
        now = time.time() if now is None else now
        from smartdialer.domain import (
            AGENT_TRANSITIONS,
            CALL_TRANSITIONS,
            AgentState,
            CallState,
            InvalidTransition,
            transition,
        )

        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT state,agent_id FROM calls WHERE id=?", (call_id,)
                ).fetchone()
                if row is None:
                    db.rollback()
                    return False
                previous = row["state"]
                if expected_state is not None and previous != expected_state:
                    db.rollback()
                    return False
                if state == "RETRY_WAIT":
                    db.rollback()
                    return False
                try:
                    transition(CallState(previous), CallState(state), CALL_TRANSITIONS)
                except (InvalidTransition, ValueError):
                    db.rollback()
                    return False
                updated = db.execute(
                    """UPDATE calls
                       SET state=?,provider=COALESCE(?,provider),
                           reason=CASE WHEN ? THEN NULL ELSE COALESCE(?,reason) END,
                           updated_at=?,
                           attempts=attempts+?
                       WHERE id=? AND state=?""",
                    (
                        state,
                        provider,
                        state in {"INITIATED", "RINGING", "ANSWERED", "CONNECTED", "COMPLETED"},
                        reason,
                        now,
                        int(state == "INITIATED"),
                        call_id,
                        previous,
                    ),
                ).rowcount
                if updated != 1:
                    db.rollback()
                    return False
                agent_row = db.execute(
                    "SELECT state FROM agents WHERE id=?", (row["agent_id"],)
                ).fetchone()
                if agent_row is None:
                    db.rollback()
                    return False
                agent_state = self._next_agent_state(previous, state, agent_row["state"])
                requires_agent_update = (
                    state
                    in {
                        "INITIATED",
                        "UNCERTAIN",
                        "QUEUED",
                        "COMPLETED",
                    }
                    or (state == "CONNECTED" and previous != "UNCERTAIN")
                    or (
                        state in {"FAILED", "CANCELLED"}
                        and previous
                        in {
                            "RESERVED",
                            "INITIATED",
                            "RINGING",
                            "ANSWERED",
                            "CONNECTED",
                            "UNCERTAIN",
                        }
                    )
                )
                if requires_agent_update and agent_state is None:
                    db.rollback()
                    return False
                if agent_state is not None:
                    try:
                        transition(
                            AgentState(agent_row["state"]),
                            AgentState(agent_state),
                            AGENT_TRANSITIONS,
                        )
                    except (InvalidTransition, ValueError):
                        db.rollback()
                        return False
                    changed = db.execute(
                        "UPDATE agents SET state=? WHERE id=? AND state=?",
                        (agent_state, row["agent_id"], agent_row["state"]),
                    ).rowcount
                    if changed != 1:
                        db.rollback()
                        return False
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise

    @staticmethod
    def _next_agent_state(
        previous_call_state: str, next_call_state: str, current_agent_state: str
    ) -> str | None:
        if next_call_state == "INITIATED":
            return "DIALING" if current_agent_state == "RESERVED" else None
        if next_call_state == "CONNECTED":
            return "CONNECTED" if current_agent_state == "DIALING" else None
        if next_call_state == "UNCERTAIN":
            return "PAUSED"
        if next_call_state == "QUEUED":
            return "AVAILABLE" if current_agent_state == "RESERVED" else None
        if next_call_state == "COMPLETED":
            return "WRAP_UP" if current_agent_state in {"DIALING", "CONNECTED", "PAUSED"} else None
        if next_call_state in {"FAILED", "CANCELLED"} and previous_call_state not in {
            "FAILED",
            "COMPLETED",
            "CANCELLED",
        }:
            return (
                "AVAILABLE"
                if current_agent_state
                in {
                    "RESERVED",
                    "DIALING",
                    "CONNECTED",
                    "PAUSED",
                }
                else None
            )
        return None

    def schedule_retry(
        self, call_id: str, *, retry_at: float, max_retries: int, now: float
    ) -> bool:
        """Move a failed call into bounded retry wait without releasing its borrower twice."""
        if max_retries < 0:
            raise ValueError("max_retries must be zero or greater")
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT state,retry_count,reason FROM calls WHERE id=?", (call_id,)
                ).fetchone()
                if (
                    row is None
                    or row["state"] != "FAILED"
                    or row["reason"]
                    not in {"provider_timeout", "provider_unavailable", "provider_failure"}
                ):
                    db.rollback()
                    return False
                if row["retry_count"] >= max_retries:
                    db.execute(
                        """UPDATE calls SET reason='provider_retry_exhausted',updated_at=?
                           WHERE id=? AND state='FAILED'""",
                        (now, call_id),
                    )
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(?,?,?,?)",
                        (call_id, "RETRY_EXHAUSTED", f"limit={max_retries}", now),
                    )
                    db.commit()
                    return False
                from smartdialer.domain import CALL_TRANSITIONS, CallState, transition

                transition(CallState(row["state"]), CallState("RETRY_WAIT"), CALL_TRANSITIONS)
                retry_count = row["retry_count"] + 1
                db.execute(
                    "UPDATE calls SET state='RETRY_WAIT',retry_count=?,retry_at=?,"
                    "reason='provider_retry',updated_at=? WHERE id=?",
                    (retry_count, retry_at, now, call_id),
                )
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, "RETRY_SCHEDULED", f"retry={retry_count};at={retry_at}", now),
                )
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise

    def claim_retry(self, call_id: str, *, now: float) -> dict | None:
        """Atomically reserve one free agent for a due retry of the same borrower."""
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                call = db.execute(
                    "SELECT borrower_id,retry_count,retry_at,state FROM calls WHERE id=?",
                    (call_id,),
                ).fetchone()
                if (
                    call is None
                    or call["state"] != "RETRY_WAIT"
                    or call["retry_at"] is None
                    or call["retry_at"] > now
                ):
                    db.rollback()
                    return None
                agent = db.execute(
                    """SELECT a.id FROM agents a
                       WHERE a.state='AVAILABLE' AND NOT EXISTS
                       (SELECT 1 FROM calls c WHERE c.agent_id=a.id AND c.state IN
                        ('RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED','UNCERTAIN'))
                       ORDER BY a.id LIMIT 1"""
                ).fetchone()
                if agent is None:
                    db.rollback()
                    return None
                from smartdialer.domain import (
                    AGENT_TRANSITIONS,
                    CALL_TRANSITIONS,
                    AgentState,
                    CallState,
                    transition,
                )

                transition(CallState(call["state"]), CallState("RESERVED"), CALL_TRANSITIONS)
                transition(AgentState("AVAILABLE"), AgentState("RESERVED"), AGENT_TRANSITIONS)
                changed = db.execute(
                    "UPDATE agents SET state='RESERVED' WHERE id=? AND state='AVAILABLE'",
                    (agent["id"],),
                ).rowcount
                if changed != 1:
                    db.rollback()
                    return None
                db.execute(
                    "UPDATE calls SET agent_id=?,state='RESERVED',retry_at=NULL,updated_at=? "
                    "WHERE id=? AND state='RETRY_WAIT'",
                    (agent["id"], now, call_id),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    return None
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, "RETRY_CLAIMED", f"agent={agent['id']}", now),
                )
                db.commit()
                return {
                    "id": call_id,
                    "borrower_id": call["borrower_id"],
                    "agent_id": agent["id"],
                    "state": "RESERVED",
                    "retry_count": call["retry_count"],
                }
            except Exception:
                db.rollback()
                raise

    def due_retries(self, *, now: float) -> list[dict]:
        rows = self._connection.execute(
            """SELECT id,borrower_id,agent_id,provider,retry_count,retry_at,attempts
               FROM calls WHERE state='RETRY_WAIT' AND retry_at<=? ORDER BY retry_at,id""",
            (now,),
        ).fetchall()
        return [dict(row) for row in rows]

    def next_event_sequence(self, call_id: str, provider: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE call_id=? AND provider=?",
            (call_id, provider),
        ).fetchone()
        return int(row[0])

    def defer_retry(self, call_id: str, *, retry_at: float, now: float) -> bool:
        """Return a claimed retry to wait if the provider became unavailable before initiation."""
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT state,agent_id FROM calls WHERE id=?", (call_id,)
                ).fetchone()
                if row is None or row["state"] != "RESERVED":
                    db.rollback()
                    return False
                agent = db.execute(
                    "SELECT state FROM agents WHERE id=?", (row["agent_id"],)
                ).fetchone()
                if agent is None or agent["state"] != "RESERVED":
                    db.rollback()
                    return False
                from smartdialer.domain import (
                    AGENT_TRANSITIONS,
                    CALL_TRANSITIONS,
                    AgentState,
                    CallState,
                    transition,
                )

                transition(
                    AgentState(agent["state"]),
                    AgentState("AVAILABLE"),
                    AGENT_TRANSITIONS,
                )
                transition(CallState("RESERVED"), CallState("RETRY_WAIT"), CALL_TRANSITIONS)
                db.execute(
                    """UPDATE calls SET state='RETRY_WAIT',retry_at=?,updated_at=?
                       WHERE id=? AND state='RESERVED'""",
                    (retry_at, now, call_id),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    return False
                db.execute(
                    "UPDATE agents SET state='AVAILABLE' WHERE id=? AND state='RESERVED'",
                    (row["agent_id"],),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    return False
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, "RETRY_DEFERRED", f"at={retry_at}", now),
                )
                db.commit()
                return True
            except Exception:
                db.rollback()
                raise

    def claim_queued(self, agent_id: str, *, now: float | None = None) -> dict | None:
        """Resume one safely requeued call after a worker restart."""
        now = time.time() if now is None else now
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                agent = db.execute("SELECT state FROM agents WHERE id=?", (agent_id,)).fetchone()
                if agent is None or agent["state"] != "AVAILABLE":
                    db.rollback()
                    return None
                call = db.execute(
                    """SELECT id,borrower_id,state FROM calls WHERE state='QUEUED'
                       ORDER BY created_at,id LIMIT 1"""
                ).fetchone()
                if call is None:
                    db.rollback()
                    return None
                from smartdialer.domain import (
                    AGENT_TRANSITIONS,
                    CALL_TRANSITIONS,
                    AgentState,
                    CallState,
                    transition,
                )

                transition(AgentState(agent["state"]), AgentState("RESERVED"), AGENT_TRANSITIONS)
                transition(CallState(call["state"]), CallState("RESERVED"), CALL_TRANSITIONS)
                db.execute(
                    "UPDATE agents SET state='RESERVED' WHERE id=? AND state='AVAILABLE'",
                    (agent_id,),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    return None
                db.execute(
                    """UPDATE calls SET state='RESERVED',agent_id=?,updated_at=?
                       WHERE id=? AND state='QUEUED'""",
                    (agent_id, now, call["id"]),
                )
                if db.execute("SELECT changes()").fetchone()[0] != 1:
                    db.rollback()
                    return None
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call["id"], "RECOVERY_CLAIMED", f"agent={agent_id}", now),
                )
                db.commit()
                return {
                    "id": call["id"],
                    "borrower_id": call["borrower_id"],
                    "agent_id": agent_id,
                    "state": "RESERVED",
                }
            except Exception:
                db.rollback()
                raise

    def process_event(
        self,
        call_id: str,
        event_id: str,
        sequence: int,
        kind: str,
        payload: dict | None = None,
        now: float | None = None,
        *,
        provider: str = "default",
    ) -> str:
        """Apply one provider-scoped event atomically and reject stale/invalid events."""
        now = time.time() if now is None else now
        payload = payload or {}
        from smartdialer.domain import (
            AGENT_TRANSITIONS,
            CALL_TRANSITIONS,
            AgentState,
            CallState,
            InvalidTransition,
            transition,
        )

        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT state,agent_id FROM calls WHERE id=?", (call_id,)
                ).fetchone()
                if row is None:
                    db.rollback()
                    return "UNKNOWN_CALL"
                existing = db.execute(
                    "SELECT 1 FROM events WHERE provider=? AND event_id=?",
                    (provider, event_id),
                ).fetchone()
                if existing:
                    db.rollback()
                    return "DUPLICATE"
                latest = db.execute(
                    "SELECT MAX(seq) AS n FROM events WHERE call_id=? AND provider=?",
                    (call_id, provider),
                ).fetchone()["n"]
                if latest is not None and sequence <= latest:
                    db.rollback()
                    return "STALE"
                try:
                    transition(CallState(row["state"]), CallState(kind), CALL_TRANSITIONS)
                except (InvalidTransition, ValueError):
                    db.rollback()
                    return "INVALID_TRANSITION"
                agent = None
                if row["agent_id"] is not None:
                    agent = db.execute(
                        "SELECT state FROM agents WHERE id=?", (row["agent_id"],)
                    ).fetchone()
                    if agent is None:
                        db.rollback()
                        return "INVALID_TRANSITION"
                next_agent_state = (
                    self._next_agent_state(row["state"], kind, agent["state"])
                    if agent is not None
                    else None
                )
                if kind == "UNCERTAIN" and agent is not None:
                    next_agent_state = "PAUSED"
                requires_agent_update = (
                    agent is not None
                    and (
                        kind
                        in {
                            "INITIATED",
                            "UNCERTAIN",
                            "COMPLETED",
                        }
                        or (kind == "CONNECTED" and row["state"] != "UNCERTAIN")
                        or (
                            kind in {"FAILED", "CANCELLED", "ABANDONED"}
                            and row["state"]
                            in {
                                "RESERVED",
                                "INITIATED",
                                "RINGING",
                                "ANSWERED",
                                "CONNECTED",
                                "UNCERTAIN",
                            }
                        )
                    )
                )
                if requires_agent_update and next_agent_state is None:
                    db.rollback()
                    return "INVALID_TRANSITION"
                if next_agent_state is not None:
                    try:
                        transition(
                            AgentState(agent["state"]),
                            AgentState(next_agent_state),
                            AGENT_TRANSITIONS,
                        )
                    except (InvalidTransition, ValueError):
                        db.rollback()
                        return "INVALID_TRANSITION"
                changed = db.execute(
                    """UPDATE calls
                       SET state=?,provider=COALESCE(?,provider),
                       reason=CASE WHEN ? THEN NULL ELSE COALESCE(?,reason) END,
                       updated_at=?,attempts=attempts+?
                       WHERE id=? AND state=?""",
                    (
                        kind,
                        provider if kind == "INITIATED" else None,
                        kind in {"INITIATED", "RINGING", "ANSWERED", "CONNECTED", "COMPLETED"},
                        payload.get("reason"),
                        now,
                        int(kind == "INITIATED"),
                        call_id,
                        row["state"],
                    ),
                ).rowcount
                if changed != 1:
                    db.rollback()
                    return "INVALID_TRANSITION"
                if next_agent_state is not None:
                    changed = db.execute(
                        "UPDATE agents SET state=? WHERE id=? AND state=?",
                        (next_agent_state, row["agent_id"], agent["state"]),
                    ).rowcount
                    if changed != 1:
                        db.rollback()
                        return "INVALID_TRANSITION"
                db.execute(
                    """INSERT INTO events
                       (provider,event_id,call_id,seq,kind,payload,received_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        provider,
                        event_id,
                        call_id,
                        sequence,
                        kind,
                        json.dumps(payload, sort_keys=True),
                        now,
                    ),
                )
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (
                        call_id,
                        f"PROVIDER_EVENT:{provider}:{kind}",
                        json.dumps(payload, sort_keys=True),
                        now,
                    ),
                )
                db.commit()
                return "APPLIED"
            except Exception:
                db.rollback()
                raise

    def recover(self) -> int:
        """Requeue only pre-provider reservations; quarantine uncertain provider outcomes."""
        from smartdialer.domain import (
            AGENT_TRANSITIONS,
            CALL_TRANSITIONS,
            AgentState,
            CallState,
            transition,
        )

        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                active = db.execute(
                    """SELECT id,agent_id,state FROM calls
                       WHERE state IN ('RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED')
                       ORDER BY created_at,id"""
                ).fetchall()
                requeued = 0
                # Requeue pre-provider reservations and quarantine provider-started calls
                for call in active:
                    agent = None
                    if call["agent_id"] is not None:
                        agent = db.execute(
                            "SELECT state FROM agents WHERE id=?", (call["agent_id"],)
                        ).fetchone()
                        if agent is None:
                            raise RuntimeError(f"call {call['id']} references a missing agent")
                    if call["state"] == "RESERVED":
                        transition(
                            CallState(call["state"]),
                            CallState("QUEUED"),
                            CALL_TRANSITIONS,
                        )
                        changed = db.execute(
                            """UPDATE calls SET state='QUEUED',recovery_count=recovery_count+1,
                               updated_at=?,reason='recovered_before_provider_start'
                               WHERE id=? AND state='RESERVED'""",
                            (time.time(), call["id"]),
                        ).rowcount
                        if changed != 1:
                            continue
                        if agent is not None and agent["state"] != "AVAILABLE":
                            transition(
                                AgentState(agent["state"]),
                                AgentState("AVAILABLE"),
                                AGENT_TRANSITIONS,
                            )
                            updated = db.execute(
                                "UPDATE agents SET state='AVAILABLE' WHERE id=? AND state=?",
                                (call["agent_id"], agent["state"]),
                            ).rowcount
                            if updated != 1:
                                raise RuntimeError(
                                    "agent state changed while requeuing reservation"
                                )
                        detail = "pre-provider reservation safely requeued"
                        requeued += 1
                    else:
                        transition(
                            CallState(call["state"]),
                            CallState("UNCERTAIN"),
                            CALL_TRANSITIONS,
                        )
                        changed = db.execute(
                            """UPDATE calls SET state='UNCERTAIN',recovery_count=recovery_count+1,
                               updated_at=?,reason='provider_outcome_uncertain'
                               WHERE id=? AND state=?""",
                            (time.time(), call["id"], call["state"]),
                        ).rowcount
                        if changed != 1:
                            continue
                        if agent is not None and agent["state"] != "PAUSED":
                            transition(
                                AgentState(agent["state"]),
                                AgentState("PAUSED"),
                                AGENT_TRANSITIONS,
                            )
                            updated = db.execute(
                                "UPDATE agents SET state='PAUSED' WHERE id=? AND state=?",
                                (call["agent_id"], agent["state"]),
                            ).rowcount
                            if updated != 1:
                                raise RuntimeError("agent state changed while quarantining call")
                        detail = f"provider outcome uncertain after {call['state']}"
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(?,?,?,?)",
                        (call["id"], "WORKER_RECOVERY", detail, time.time()),
                    )

                # Point 1 recovery: clean up any orphan RESERVED agent
                # (crashed after agent reserved before call inserted)
                orphan_agents = db.execute(
                    """SELECT id, state FROM agents
                       WHERE state='RESERVED' AND id NOT IN (
                           SELECT agent_id FROM calls
                           WHERE state IN (
                               'RESERVED','INITIATED','RINGING',
                               'ANSWERED','CONNECTED','UNCERTAIN'
                           )
                       )"""
                ).fetchall()
                for orphan in orphan_agents:
                    transition(AgentState.RESERVED, AgentState.AVAILABLE, AGENT_TRANSITIONS)
                    db.execute(
                        "UPDATE agents SET state='AVAILABLE' WHERE id=? AND state='RESERVED'",
                        (orphan["id"],),
                    )
                    db.execute(
                        "INSERT INTO event_history(call_id,kind,detail,occurred_at) "
                        "VALUES(NULL,?,?,?)",
                        (
                            "WORKER_RECOVERY",
                            f"orphan reserved agent {orphan['id']} restored to AVAILABLE",
                            time.time(),
                        ),
                    )
                db.commit()
                return requeued
            except Exception:
                db.rollback()
                raise

    def counts(self) -> dict[str, int]:
        return {
            row["state"]: row["n"]
            for row in self._connection.execute(
                "SELECT state,COUNT(*) AS n FROM calls GROUP BY state"
            )
        }

    def event_count(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM event_history").fetchone()[0]
