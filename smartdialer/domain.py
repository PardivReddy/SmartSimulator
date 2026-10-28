"""Validated domain states and transitions for the simulator."""

from __future__ import annotations

from enum import StrEnum


class AgentState(StrEnum):
    OFFLINE = "OFFLINE"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    DIALING = "DIALING"
    CONNECTED = "CONNECTED"
    WRAP_UP = "WRAP_UP"
    PAUSED = "PAUSED"


class CallState(StrEnum):
    QUEUED = "QUEUED"
    RESERVED = "RESERVED"
    INITIATED = "INITIATED"
    RINGING = "RINGING"
    ANSWERED = "ANSWERED"
    CONNECTED = "CONNECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_WAIT = "RETRY_WAIT"
    UNCERTAIN = "UNCERTAIN"
    CANCELLED = "CANCELLED"
    ABANDONED = "ABANDONED"


AGENT_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.OFFLINE: {AgentState.AVAILABLE},
    AgentState.AVAILABLE: {AgentState.OFFLINE, AgentState.RESERVED, AgentState.PAUSED},
    AgentState.RESERVED: {AgentState.AVAILABLE, AgentState.DIALING, AgentState.PAUSED},
    AgentState.DIALING: {AgentState.AVAILABLE, AgentState.CONNECTED, AgentState.PAUSED},
    AgentState.CONNECTED: {AgentState.WRAP_UP, AgentState.PAUSED},
    AgentState.WRAP_UP: {AgentState.AVAILABLE, AgentState.PAUSED},
    AgentState.PAUSED: {AgentState.AVAILABLE, AgentState.OFFLINE, AgentState.WRAP_UP},
}

CALL_TRANSITIONS: dict[CallState, set[CallState]] = {
    CallState.QUEUED: {CallState.RESERVED, CallState.CANCELLED},
    CallState.RESERVED: {
        CallState.QUEUED,
        CallState.INITIATED,
        CallState.CANCELLED,
        CallState.FAILED,
        CallState.RETRY_WAIT,
    },
    CallState.INITIATED: {
        CallState.RINGING,
        CallState.FAILED,
        CallState.UNCERTAIN,
        CallState.CANCELLED,
    },
    CallState.RINGING: {
        CallState.ANSWERED,
        CallState.FAILED,
        CallState.UNCERTAIN,
        CallState.CANCELLED,
    },
    CallState.ANSWERED: {
        CallState.CONNECTED,
        CallState.COMPLETED,
        CallState.FAILED,
        CallState.UNCERTAIN,
        CallState.ABANDONED,
    },
    CallState.CONNECTED: {
        CallState.COMPLETED,
        CallState.FAILED,
        CallState.UNCERTAIN,
    },
    CallState.COMPLETED: set(),
    CallState.FAILED: {CallState.RETRY_WAIT},
    CallState.RETRY_WAIT: {CallState.RESERVED, CallState.FAILED, CallState.CANCELLED},
    CallState.UNCERTAIN: {
        CallState.RINGING,
        CallState.ANSWERED,
        CallState.CONNECTED,
        CallState.COMPLETED,
        CallState.FAILED,
    },
    CallState.CANCELLED: set(),
    CallState.ABANDONED: set(),
}


class InvalidTransition(ValueError):
    """Raised when a state change is not part of the declared transition graph."""


def transition(current: StrEnum, target: StrEnum, graph: dict) -> StrEnum:
    """Return target if the transition is legal; otherwise reject it."""
    if target not in graph.get(current, set()):
        raise InvalidTransition(f"Illegal transition: {current.value} -> {target.value}")
    return target
