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
              agent_id TEXT NOT NULL REFERENCES agents(id), state TEXT NOT NULL,
              created_at REAL NOT NULL, updated_at REAL NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              provider TEXT, reason TEXT
            );
            CREATE INDEX IF NOT EXISTS calls_state ON calls(state);
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY, call_id TEXT NOT NULL, seq INTEGER NOT NULL,
              kind TEXT NOT NULL, payload TEXT NOT NULL, received_at REAL NOT NULL,
              UNIQUE(call_id, seq)
            );
            CREATE TABLE IF NOT EXISTS event_history(
              id INTEGER PRIMARY KEY AUTOINCREMENT, call_id TEXT, kind TEXT NOT NULL,
              detail TEXT NOT NULL, occurred_at REAL NOT NULL
            );
            """
        )

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

        with self._connection:
            row = self._connection.execute(
                "SELECT state FROM agents WHERE id=?", (agent_id,)
            ).fetchone()
            if row is None:
                return False
            try:
                transition(AgentState(row["state"]), AgentState(state), AGENT_TRANSITIONS)
            except (InvalidTransition, ValueError):
                return False
            self._connection.execute("UPDATE agents SET state=? WHERE id=?", (state, agent_id))
            return True

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
                        ('RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED'))
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
                    "('RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED')",
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
    ) -> bool:
        now = time.time() if now is None else now
        with self._connection:
            row = self._connection.execute(
                "SELECT state,agent_id FROM calls WHERE id=?", (call_id,)
            ).fetchone()
            if row is None:
                return False
            from smartdialer.domain import (
                CALL_TRANSITIONS,
                CallState,
                InvalidTransition,
                transition,
            )

            try:
                transition(CallState(row["state"]), CallState(state), CALL_TRANSITIONS)
            except (InvalidTransition, ValueError):
                return False
            self._connection.execute(
                "UPDATE calls SET state=?,provider=COALESCE(?,provider),reason=COALESCE(?,reason),"
                "updated_at=? WHERE id=?",
                (state, provider, reason, now, call_id),
            )
            if state in {"COMPLETED", "FAILED", "CANCELLED"}:
                agent_state = "WRAP_UP" if state == "COMPLETED" else "AVAILABLE"
                self._connection.execute(
                    "UPDATE agents SET state=? WHERE id=?", (agent_state, row["agent_id"])
                )
            elif state == "INITIATED":
                self._connection.execute(
                    "UPDATE agents SET state='DIALING' WHERE id=?", (row["agent_id"],)
                )
            elif state == "CONNECTED":
                self._connection.execute(
                    "UPDATE agents SET state='CONNECTED' WHERE id=?", (row["agent_id"],)
                )
            return True

    def process_event(
        self,
        call_id: str,
        event_id: str,
        sequence: int,
        kind: str,
        payload: dict | None = None,
        now: float | None = None,
    ) -> str:
        """Deduplicate provider events and reject stale sequence numbers."""
        now = time.time() if now is None else now
        with self._lock:
            db = self._connection
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT 1 FROM events WHERE event_id=?", (event_id,)
                ).fetchone()
                if existing:
                    db.rollback()
                    return "DUPLICATE"
                latest = db.execute(
                    "SELECT MAX(seq) AS n FROM events WHERE call_id=?", (call_id,)
                ).fetchone()["n"]
                if latest is not None and sequence <= latest:
                    db.rollback()
                    return "STALE"
                db.execute(
                    "INSERT INTO events VALUES(?,?,?,?,?,?)",
                    (
                        event_id,
                        call_id,
                        sequence,
                        kind,
                        json.dumps(payload or {}, sort_keys=True),
                        now,
                    ),
                )
                row = db.execute("SELECT state FROM calls WHERE id=?", (call_id,)).fetchone()
                if row is None:
                    db.rollback()
                    return "UNKNOWN_CALL"
                from smartdialer.domain import (
                    CALL_TRANSITIONS,
                    CallState,
                    InvalidTransition,
                    transition,
                )

                try:
                    transition(CallState(row["state"]), CallState(kind), CALL_TRANSITIONS)
                except (InvalidTransition, ValueError):
                    db.rollback()
                    return "INVALID_TRANSITION"
                db.execute("UPDATE calls SET state=?,updated_at=? WHERE id=?", (kind, now, call_id))
                call = db.execute("SELECT agent_id FROM calls WHERE id=?", (call_id,)).fetchone()
                if kind == "INITIATED":
                    db.execute("UPDATE agents SET state='DIALING' WHERE id=?", (call["agent_id"],))
                elif kind == "CONNECTED":
                    db.execute(
                        "UPDATE agents SET state='CONNECTED' WHERE id=?", (call["agent_id"],)
                    )
                elif kind in {"COMPLETED", "FAILED", "CANCELLED"}:
                    db.execute(
                        "UPDATE agents SET state=? WHERE id=?",
                        ("WRAP_UP" if kind == "COMPLETED" else "AVAILABLE", call["agent_id"]),
                    )
                db.execute(
                    "INSERT INTO event_history(call_id,kind,detail,occurred_at) VALUES(?,?,?,?)",
                    (call_id, kind, json.dumps(payload or {}, sort_keys=True), now),
                )
                db.commit()
                return "APPLIED"
            except Exception:
                db.rollback()
                raise

    def recover(self) -> int:
        """Reset orphaned active work after a worker restart; retry count stays bounded."""
        with self._connection:
            active = self._connection.execute(
                "SELECT id,agent_id,attempts FROM calls "
                "WHERE state IN ('RESERVED','INITIATED','RINGING') "
                "OR (state='QUEUED' AND attempts>0)"
            ).fetchall()
            recovered = 0
            for call in active:
                if call["attempts"] < 1:
                    self._connection.execute(
                        "UPDATE calls SET state='QUEUED',attempts=attempts+1,updated_at=? "
                        "WHERE id=?",
                        (time.time(), call["id"]),
                    )
                    self._connection.execute(
                        "UPDATE agents SET state='AVAILABLE' WHERE id=?", (call["agent_id"],)
                    )
                    recovered += 1
                else:
                    self._connection.execute(
                        "UPDATE calls SET state='FAILED' WHERE id=?", (call["id"],)
                    )
                    self._connection.execute(
                        "UPDATE agents SET state='AVAILABLE' WHERE id=?", (call["agent_id"],)
                    )
        return recovered

    def counts(self) -> dict[str, int]:
        return {
            row["state"]: row["n"]
            for row in self._connection.execute(
                "SELECT state,COUNT(*) AS n FROM calls GROUP BY state"
            )
        }

    def event_count(self) -> int:
        return self._connection.execute("SELECT COUNT(*) FROM event_history").fetchone()[0]
