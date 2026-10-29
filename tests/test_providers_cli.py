import json

import pytest

from smartdialer.cli import main
from smartdialer.engine import Simulation
from smartdialer.providers import MockProvider, ProviderRetryPolicy


def test_mock_provider_replays_with_same_seed():
    a = MockProvider("a", 0.5, 2, 10, 0.1, 20, 5, seed=4)
    b = MockProvider("b", 0.5, 2, 10, 0.1, 20, 5, seed=4)
    assert [a.simulate() for _ in range(10)] == [b.simulate() for _ in range(10)]


def test_unavailable_provider_generates_a_simulated_timeout():
    provider = MockProvider("offline", 0.5, 2, 10, 0, 10, 2, available=False)
    assert provider.simulate().kind == "FAILED"
    assert provider.simulate().delay_seconds == provider.timeout_seconds


def test_mock_provider_recovers_after_an_outage():
    provider = MockProvider("recovering", 0.5, 2, 10, 0, 10, 2, available=False)
    assert provider.simulate().kind == "FAILED"
    provider.available = True
    assert provider.simulate().kind in {"ANSWERED", "NO_ANSWER"}


def test_simulation_respects_provider_concurrency_and_rate_caps():
    simulation = Simulation.create(seed=3)
    simulation.providers[0].concurrency_limit = 2
    simulation.providers[0].rate_limit_per_minute = 2
    simulation.providers[1].concurrency_limit = 1
    simulation.providers[1].rate_limit_per_minute = 1
    result = simulation.run(agents=8, borrowers=12)
    assert result.attempted == 3
    simulation.store.close()


def test_predictive_execution_obeys_safety_pause_during_provider_outage():
    simulation = Simulation.create(seed=3)
    for provider in simulation.providers:
        provider.set_available(False)

    metrics = simulation.run(agents=2, borrowers=4, mode="predictive")

    assert metrics.attempted == 0
    assert metrics.safety_interventions == 1
    assert simulation.safety.history[-1].action == "PAUSE"
    simulation.store.close()


def test_legacy_predictive_run_respects_zero_safety_approved_starts():
    simulation = Simulation.create(seed=42)

    metrics = simulation.run(agents=2, borrowers=10, mode="predictive")

    assert simulation.safety.history[-1].approved_calls_per_minute > 0
    assert simulation.safety.history[-1].approved_calls_to_start == 0
    assert metrics.attempted == 0
    assert simulation.store._connection.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    simulation.store.close()


def test_predictive_runner_uses_actual_zero_available_agent_count():
    simulation = Simulation.create(seed=42)

    metrics = simulation.run(
        agents=2, borrowers=10, mode="predictive", scenario="no_available_agents"
    )

    assert simulation.safety.history[-1].action == "IDLE"
    assert simulation.safety.history[-1].approved_calls_to_start == 0
    assert metrics.attempted == 0
    assert simulation.store._connection.execute("SELECT COUNT(*) FROM calls").fetchone()[0] == 0
    simulation.store.close()


def test_new_call_uses_healthy_provider_when_another_is_unavailable():
    simulation = Simulation.create(seed=3)
    unavailable, healthy = simulation.providers
    unavailable.available = False
    healthy.failure_rate = 0.0
    healthy.answer_probability = 0.0

    simulation.run(agents=1, borrowers=1)

    call = simulation.store._connection.execute("SELECT provider FROM calls").fetchone()
    assert call["provider"] == healthy.name
    simulation.store.close()


def test_cli_emits_simulated_metrics(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["smartdialer", "simulate", "--agents", "2", "--borrowers", "4"]
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["label"] == "SIMULATED"
    assert result["attempted"] == 2


def test_cli_models_provider_outage(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "smartdialer",
            "simulate",
            "--scenario",
            "provider_outage",
            "--agents",
            "2",
            "--borrowers",
            "4",
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["label"] == "SIMULATED_PROVIDER_OUTAGE"
    assert result["calls_attempted"] == 3
    assert result["failures"] == 1
    assert result["timeouts"] == 1
    assert result["retries_scheduled"] == 1
    assert result["retry_backoff_seconds"] == 5
    assert result["retry_before_backoff_elapsed"] is False
    assert result["retry_deferred_during_outage"] == 1
    assert result["new_calls_blocked_during_outage"] == 1
    assert set(result["provider_status"]["during_outage"].values()) == {"UNAVAILABLE"}
    assert set(result["provider_status"]["after_recovery"].values()) == {"AVAILABLE"}
    assert result["pacing"]["approved_calls_per_minute"] == 0
    assert result["pacing"]["safety_action"] == "PAUSE"
    assert set(result["final_call_states"].values()) == {"RINGING", "COMPLETED"}
    assert result["final_retry_count"] == 1


def test_provider_outage_retry_reuses_one_borrower_and_preserves_existing_call():
    simulation = Simulation.create(seed=5)
    result = simulation.run_provider_outage(agents=3, borrowers=4)
    rows = simulation.store._connection.execute(
        "SELECT borrower_id,agent_id,state FROM calls ORDER BY id"
    ).fetchall()
    retry_rows = [row for row in rows if row["borrower_id"] == result["retry_borrower_id"]]
    assert len(rows) == 2
    assert len(retry_rows) == 1
    assert retry_rows[0]["state"] == "COMPLETED"
    assert retry_rows[0]["agent_id"] == result["retry_agent_id"]
    assert "RINGING" in [row["state"] for row in rows]
    simulation.store.close()


def test_provider_retry_policy_uses_bounded_exponential_backoff():
    policy = ProviderRetryPolicy(max_retries=2, initial_backoff_seconds=5)
    assert policy.backoff_seconds(1) == 5
    assert policy.backoff_seconds(2) == 10
    with pytest.raises(ValueError, match="retry_number"):
        policy.backoff_seconds(3)


def test_cli_with_no_available_agents_does_not_dial(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "smartdialer",
            "simulate",
            "--scenario",
            "no_available_agents",
            "--agents",
            "2",
            "--borrowers",
            "4",
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["attempted"] == 0


def test_cli_runs_load_test(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "smartdialer",
            "load-test",
            "--agents",
            "8",
            "--borrowers",
            "8",
            "--workers",
            "4",
            "--seed",
            "7",
        ],
    )
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "PASS"
    assert result["reservations"] == 8


def test_cli_returns_failure_status_when_load_invariants_fail(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["smartdialer", "load-test"])
    monkeypatch.setattr("smartdialer.cli.run_load_test", lambda **kwargs: {"result": "FAIL"})
    with pytest.raises(SystemExit) as exit_result:
        main()
    assert exit_result.value.code == 1


@pytest.mark.parametrize("scenario", ["A", "B", "C", "D", "agent-drop", "outage"])
def test_simulation_scenarios_abandonment_and_safety_bounds(scenario):
    from smartdialer.engine import run_scenario

    res = run_scenario(scenario, seed=42, duration_ticks=60)
    assert res["abandoned_calls"] <= 0.02 * max(1, res["calls_connected"])
    assert res["stranded_calls"] == 0
    if scenario == "agent-drop":
        assert res["adjustment_latency_ticks"] <= 2
        assert res["available_agents_at_drop"] == 60
        assert res["offline_agents_at_drop"] == 40
    if scenario == "outage":
        assert res["new_calls_during_outage"] == 0


def test_cli_runs_scenario_table(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["smartdialer", "simulate", "--scenario", "A", "--seed", "42"])
    main()
    output = capsys.readouterr().out
    assert "SCENARIO: A | Seed: 42" in output
    assert "Agent Utilization" in output
    assert "Abandoned Calls" in output
    assert "Stranded Calls (Target: 0)" in output
