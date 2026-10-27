from smartdialer.pacing import PacingInputs, PacingProposal, SafetyController, estimate_pacing


def inputs(**kwargs):
    values = dict(
        answer_rate=0.4,
        mean_call_seconds=90,
        mean_wrap_seconds=15,
        available_agents=5,
        busy_agents=2,
        pending_calls=10,
        provider_health=1,
        provider_failure_rate=0,
        observed_at_seconds=10,
        now_seconds=10,
        sample_count=100,
    )
    return PacingInputs(**(values | kwargs))


def test_estimator_proposes_rate_without_starting_calls():
    result = estimate_pacing(inputs())
    assert result.calls_per_minute > 0
    assert result.calls_per_minute <= 7 * 60


def test_empty_queue_yields_zero():
    assert estimate_pacing(inputs(pending_calls=0)).calls_per_minute == 0


def test_invalid_durations_fail_safe():
    assert estimate_pacing(inputs(mean_call_seconds=0)).calls_per_minute == 0


def test_safety_caps_rate_and_concurrency():
    controller = SafetyController(max_calls_per_minute=20, max_concurrency=3)
    result = controller.approve(PacingProposal(100, 0), inputs(busy_agents=1))
    assert result.approved_calls_per_minute == 20
    assert result.action == "REDUCE"


def test_safety_pauses_stale_or_unreliable_inputs():
    controller = SafetyController()
    result = controller.approve(PacingProposal(10, 0), inputs(now_seconds=50, sample_count=2))
    assert result.approved_calls_per_minute == 0
    assert result.action == "PAUSE"


def test_safety_reduces_abandonment_risk_and_provider_outage():
    controller = SafetyController()
    reduced = controller.approve(PacingProposal(20, 0.1), inputs())
    assert reduced.approved_calls_per_minute == 10
    paused = controller.approve(PacingProposal(20, 0), inputs(provider_health=0.1))
    assert paused.approved_calls_per_minute == 0


def test_no_agents_blocks_work():
    result = SafetyController().approve(
        PacingProposal(10, 0), inputs(available_agents=0, busy_agents=0, pending_calls=2)
    )
    assert result.approved_calls_per_minute == 0
