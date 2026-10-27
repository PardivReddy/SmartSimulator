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
