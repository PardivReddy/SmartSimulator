"""Predictive proposal and independent conservative safety approval."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PacingInputs:
    answer_rate: float
    mean_call_seconds: float
    mean_wrap_seconds: float
    available_agents: int
    busy_agents: int
    pending_calls: int
    provider_health: float
    provider_failure_rate: float
    abandonment_limit: float = 0.02
    observed_at_seconds: float = 0.0
    now_seconds: float = 0.0
    sample_count: int = 100


@dataclass(frozen=True)
class PacingProposal:
    calls_per_minute: float
    estimated_abandonment_risk: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SafetyDecision:
    approved_calls_per_minute: float
    action: str
    reasons: tuple[str, ...] = ()


@dataclass
class SafetyController:
    max_calls_per_minute: float = 30.0
    max_concurrency: int = 10
    max_abandonment_risk: float = 0.02
    min_provider_health: float = 0.5
    max_input_age_seconds: float = 30.0
    interventions: int = 0
    history: list[SafetyDecision] = field(default_factory=list)

    def approve(self, proposal: PacingProposal, inputs: PacingInputs) -> SafetyDecision:
        reasons: list[str] = []
        rate = max(0.0, min(proposal.calls_per_minute, self.max_calls_per_minute))
        if proposal.calls_per_minute > self.max_calls_per_minute:
            reasons.append("configured_rate_cap")
        stale = inputs.now_seconds - inputs.observed_at_seconds > self.max_input_age_seconds
        unreliable = inputs.sample_count < 10 or stale
        unhealthy = (
            inputs.provider_health < self.min_provider_health or inputs.provider_failure_rate > 0.5
        )
        if unreliable or unhealthy:
            rate = 0.0
            reasons.append("stale_or_unreliable_inputs" if unreliable else "provider_health_limit")
        elif proposal.estimated_abandonment_risk > min(
            inputs.abandonment_limit, self.max_abandonment_risk
        ):
            rate *= 0.5
            reasons.append("abandonment_risk_reduction")
        free = max(0, self.max_concurrency - inputs.busy_agents)
        rate = min(rate, float(free * 60))
        if inputs.pending_calls and inputs.available_agents == 0:
            rate = 0.0
            reasons.append("no_available_agents")
        action = "APPROVE" if not reasons else ("PAUSE" if rate == 0 else "REDUCE")
        decision = SafetyDecision(rate, action, tuple(reasons))
        if action != "APPROVE":
            self.interventions += 1
        self.history.append(decision)
        return decision


def estimate_pacing(inputs: PacingInputs) -> PacingProposal:
    """Estimate an offered load; never starts calls or reserves agents."""
    if inputs.mean_call_seconds <= 0 or inputs.mean_wrap_seconds < 0:
        return PacingProposal(0.0, 1.0, ("invalid_duration_estimate",))
    occupancy = inputs.mean_call_seconds + inputs.mean_wrap_seconds
    capacity = max(0, inputs.available_agents + inputs.busy_agents) * 60 / occupancy
    answer_rate = min(1.0, max(0.0, inputs.answer_rate))
    provider_factor = min(1.0, max(0.0, inputs.provider_health))
    offered = capacity / max(answer_rate, 0.05)
    offered *= provider_factor * (1 - min(1.0, max(0.0, inputs.provider_failure_rate)))
    offered = min(offered, float(max(0, inputs.available_agents + inputs.busy_agents) * 60))
    risk = max(
        0.0, (offered * answer_rate - max(0, inputs.available_agents) * 60 / occupancy)
    ) / max(offered, 1.0)
    if inputs.pending_calls == 0:
        offered = 0.0
    return PacingProposal(offered, risk)
