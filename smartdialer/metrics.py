"""Aggregate simulation metrics. All values describe the local simulation only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationMetrics:
    attempted: int
    answered: int
    connected: int
    completed: int
    failed: int
    cancelled: int
    connection_rate: float
    abandonment_rate: float
    provider_error_rate: float
    provider_errors: int
    retries: int
    queue_wait_seconds_mean: float
    elapsed_seconds: float
    throughput_calls_per_minute: float
    agent_utilization: float
    agent_idle_seconds: float
    safety_interventions: int

    @classmethod
    def from_states(
        cls,
        states: dict[str, int],
        *,
        elapsed_seconds: float,
        retries: int = 0,
        mean_queue_wait_seconds: float = 0.0,
        safety_interventions: int = 0,
        provider_errors: int = 0,
        agent_count: int = 0,
        agent_busy_seconds: float = 0.0,
        provider_attempts: int | None = None,
        answered_no_agent: int = 0,
    ) -> SimulationMetrics:
        logical_attempted = sum(
            states.get(s, 0)
            for s in (
                "INITIATED",
                "RINGING",
                "ANSWERED",
                "CONNECTED",
                "COMPLETED",
                "FAILED",
                "RETRY_WAIT",
                "UNCERTAIN",
                "ABANDONED_NO_AGENT",
            )
        )
        attempted = logical_attempted if provider_attempts is None else provider_attempts
        answered = sum(states.get(s, 0) for s in ("ANSWERED", "CONNECTED", "COMPLETED"))
        answered += answered_no_agent
        connected = sum(states.get(s, 0) for s in ("CONNECTED", "COMPLETED"))
        completed = states.get("COMPLETED", 0)
        failed = states.get("FAILED", 0)
        cancelled = states.get("CANCELLED", 0)
        abandoned_no_agent = states.get("ABANDONED_NO_AGENT", 0)
        denominator = attempted or 1
        active_plus_done = attempted + cancelled
        total_agent_seconds = max(0, agent_count) * max(0.0, elapsed_seconds)
        busy = min(total_agent_seconds, max(0.0, agent_busy_seconds))
        return cls(
            attempted,
            answered,
            connected,
            completed,
            failed,
            cancelled,
            connected / denominator,
            (cancelled + abandoned_no_agent) / (active_plus_done or 1),
            provider_errors / denominator,
            provider_errors,
            retries,
            mean_queue_wait_seconds,
            elapsed_seconds,
            attempted * 60 / elapsed_seconds if elapsed_seconds > 0 else 0.0,
            busy / total_agent_seconds if total_agent_seconds > 0 else 0.0,
            max(0.0, total_agent_seconds - busy),
            safety_interventions,
        )

    def as_dict(self) -> dict[str, int | float | str]:
        return {"label": "SIMULATED", **self.__dict__}
