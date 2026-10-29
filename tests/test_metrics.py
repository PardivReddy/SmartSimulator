from smartdialer.metrics import SimulationMetrics


def test_aggregate_metric_counts_and_denominators():
    metrics = SimulationMetrics.from_states(
        {"COMPLETED": 2, "FAILED": 1, "CANCELLED": 1},
        elapsed_seconds=120,
        provider_errors=1,
        agent_count=2,
        agent_busy_seconds=60,
    )
    assert metrics.attempted == 3
    assert metrics.answered == 2
    assert metrics.connected == 2
    assert metrics.connection_rate == 2 / 3
    assert metrics.abandonment_rate == 0.25
    assert metrics.provider_error_rate == 1 / 3
    assert metrics.throughput_calls_per_minute == 1.5
    assert metrics.agent_utilization == 0.25
    assert metrics.agent_idle_seconds == 180


def test_zero_denominators_are_safe():
    metrics = SimulationMetrics.from_states({}, elapsed_seconds=0)
    assert metrics.connection_rate == 0
    assert metrics.abandonment_rate == 0
    assert metrics.provider_error_rate == 0
    assert metrics.throughput_calls_per_minute == 0


def test_no_agent_abandonments_count_as_attempts_and_abandonments():
    metrics = SimulationMetrics.from_states(
        {"COMPLETED": 2, "FAILED": 1, "CANCELLED": 1, "ABANDONED_NO_AGENT": 2},
        elapsed_seconds=60,
    )

    assert metrics.attempted == 5
    assert metrics.answered == 2
    assert metrics.cancelled == 1
    assert metrics.abandonment_rate == 0.5


def test_metrics_use_persisted_provider_attempts_and_answer_event_evidence():
    metrics = SimulationMetrics.from_states(
        {"ABANDONED_NO_AGENT": 1, "FAILED": 1},
        elapsed_seconds=60,
        provider_attempts=3,
        answered_no_agent=1,
    )

    assert metrics.attempted == 3
    assert metrics.answered == 1
    assert metrics.connected == 0
    assert metrics.abandonment_rate == 1 / 3
