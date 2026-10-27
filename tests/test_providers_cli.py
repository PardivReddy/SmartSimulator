import json

from smartdialer.cli import main
from smartdialer.engine import Simulation
from smartdialer.providers import MockProvider


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
    assert result["attempted"] == 0
    assert result["provider_errors"] == 0
    assert result["agent_utilization"] == 0


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
