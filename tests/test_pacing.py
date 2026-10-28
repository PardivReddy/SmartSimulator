from smartdialer.pacing import (
    PacingInputs,
    PacingProposal,
    SafetyController,
    SlidingWindow,
    estimate_pacing,
)


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


def test_predictive_pacing_formula_and_reason_line():
    inp = inputs(
        available_agents=10,
        expected_finishing_agents=0,
        answer_rate=0.60,
        calls_in_flight=0,
        pending_calls=50,
        window_size=50,
    )
    proposal = estimate_pacing(inp)
    # ceil(10 / 0.60) = 17
    assert proposal.calls_to_start == 17
    assert (
        "proposed 17: free=10, answer_rate=0.60 (window=50), in_flight=0 -> ceil(10/0.60)=17"
        in proposal.reason
    )


def test_safety_controller_all_decision_types():
    controller = SafetyController(
        max_calls_per_minute=600, max_concurrency=20, min_sample_size=10, max_abandonment_risk=0.02
    )

    # 1. FALLBACK_PROGRESSIVE on small sample size
    small_sample_inp = inputs(sample_count=5, available_agents=4, pending_calls=10)
    prop = PacingProposal(calls_to_start=8, calls_per_minute=480, estimated_abandonment_risk=0)
    decision1 = controller.approve(prop, small_sample_inp)
    assert decision1.action == "FALLBACK_PROGRESSIVE"
    assert decision1.approved_calls_to_start == 4
    assert "fallback to progressive: sample size 5 < min 10" in decision1.reason

    # 2. REJECT on provider timeout / unhealthy
    timeout_inp = inputs(provider_timeout_rate=0.40)
    decision2 = controller.approve(prop, timeout_inp)
    assert decision2.action == "REJECT"
    assert decision2.approved_calls_to_start == 0
    assert "rejected: provider timeout rate" in decision2.reason

    # 3. REDUCE on sharp answer rate drop
    sharp_drop_inp = inputs(
        baseline_answer_rate=0.70,
        answer_rate=0.30,
        available_agents=10,
        pending_calls=20,
    )
    decision3 = controller.approve(prop, sharp_drop_inp)
    assert decision3.action == "REDUCE"
    assert "sharp answer-rate drop" in decision3.reason

    # 4. REDUCE on hard cap (expected connections exceed free agents)
    hard_cap_inp = inputs(
        available_agents=4,
        answer_rate=0.80,
        pending_calls=20,
        sample_count=50,
    )
    # Proposed 10 calls with answer_rate 0.80 -> expected 8 connections > 4 free agents
    large_prop = PacingProposal(
        calls_to_start=10, calls_per_minute=600, estimated_abandonment_risk=0
    )
    decision4 = controller.approve(large_prop, hard_cap_inp)
    assert decision4.action == "REDUCE"
    assert "hard cap prevents expected connections" in decision4.reason

    # 5. APPROVE when within safe bounds
    safe_inp = inputs(
        available_agents=10,
        answer_rate=0.50,
        pending_calls=20,
        sample_count=50,
    )
    safe_prop = PacingProposal(
        calls_to_start=10, calls_per_minute=600, estimated_abandonment_risk=0
    )
    decision5 = controller.approve(safe_prop, safe_inp)
    assert decision5.action == "APPROVE"
    assert "approved" in decision5.reason


def test_sliding_window_statistics():
    window = SlidingWindow(size=5)
    for _ in range(3):
        window.record_call(answered=True, talk_seconds=60.0, abandoned=False)
    for _ in range(2):
        window.record_call(answered=False, talk_seconds=0.0, abandoned=False)

    assert window.sample_count == 5
    assert window.answer_rate == 0.60
    assert window.average_talk_time == 60.0
    assert window.abandonment_rate == 0.0

    # Test rolling ejection
    window.record_call(answered=False, talk_seconds=0.0, abandoned=True)
    assert window.sample_count == 5
    assert window.answer_rate == 0.40
    assert window.abandonment_rate == 0.20
