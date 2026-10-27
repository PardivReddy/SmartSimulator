import pytest

from smartdialer.domain import (
    AGENT_TRANSITIONS,
    CALL_TRANSITIONS,
    AgentState,
    CallState,
    InvalidTransition,
    transition,
)


@pytest.mark.parametrize("source,targets", AGENT_TRANSITIONS.items())
def test_each_agent_transition_is_explicit(source, targets):
    for target in targets:
        assert transition(source, target, AGENT_TRANSITIONS) is target


@pytest.mark.parametrize("source,targets", CALL_TRANSITIONS.items())
def test_each_call_transition_is_explicit(source, targets):
    for target in targets:
        assert transition(source, target, CALL_TRANSITIONS) is target


@pytest.mark.parametrize("source,targets", AGENT_TRANSITIONS.items())
def test_illegal_agent_transitions_rejected(source, targets):
    for target in set(AgentState) - targets:
        with pytest.raises(InvalidTransition):
            transition(source, target, AGENT_TRANSITIONS)


@pytest.mark.parametrize("source,targets", CALL_TRANSITIONS.items())
def test_illegal_call_transitions_rejected(source, targets):
    for target in set(CallState) - targets:
        with pytest.raises(InvalidTransition):
            transition(source, target, CALL_TRANSITIONS)


def test_answered_does_not_imply_connected():
    assert CallState.ANSWERED in CALL_TRANSITIONS[CallState.RINGING]
    assert CallState.CONNECTED not in CALL_TRANSITIONS[CallState.RINGING]
    assert CallState.CONNECTED in CALL_TRANSITIONS[CallState.ANSWERED]
