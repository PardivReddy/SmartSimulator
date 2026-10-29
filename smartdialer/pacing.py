"""Predictive proposal and independent conservative safety approval."""

from __future__ import annotations

import collections
import math
from dataclasses import dataclass, field


@dataclass
class SlidingWindow:
    """Bounded window tracking recent call outcomes and durations."""

    size: int = 50
    outcomes: collections.deque[bool] = field(default_factory=collections.deque)
    talk_durations: collections.deque[float] = field(default_factory=collections.deque)
    abandonments: collections.deque[bool] = field(default_factory=collections.deque)

    def record_call(
        self,
        *,
        answered: bool,
        talk_seconds: float = 0.0,
        abandoned: bool = False,
    ) -> None:
        self.outcomes.append(answered)
        if len(self.outcomes) > self.size:
            self.outcomes.popleft()
        if answered and talk_seconds > 0:
            self.talk_durations.append(talk_seconds)
            if len(self.talk_durations) > self.size:
                self.talk_durations.popleft()
        self.abandonments.append(abandoned)
        if len(self.abandonments) > self.size:
            self.abandonments.popleft()

    @property
    def sample_count(self) -> int:
        return len(self.outcomes)

    @property
    def answer_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(self.outcomes) / len(self.outcomes)

    @property
    def average_talk_time(self) -> float:
        if not self.talk_durations:
            return 90.0
        return sum(self.talk_durations) / len(self.talk_durations)

    @property
    def abandonment_rate(self) -> float:
        if not self.abandonments:
            return 0.0
        return sum(self.abandonments) / len(self.abandonments)


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
    expected_finishing_agents: int = 0
    calls_in_flight: int = 0
    provider_timeout_rate: float = 0.0
    baseline_answer_rate: float | None = None
    recent_abandonment_rate: float = 0.0
    abandonment_limit: float = 0.03
    window_size: int = 50
    observed_at_seconds: float = 0.0
    now_seconds: float = 0.0
    sample_count: int = 100


@dataclass(frozen=True)
class PacingProposal:
    calls_to_start: int
    calls_per_minute: float
    estimated_abandonment_risk: float
    reason: str = ""
    reasons: tuple[str, ...] = ()

    def __init__(
        self,
        calls_per_minute: float,
        estimated_abandonment_risk: float,
        reasons: tuple[str, ...] = (),
        calls_to_start: int | None = None,
        reason: str = "",
    ) -> None:
        computed_start = (
            calls_to_start if calls_to_start is not None else max(0, round(calls_per_minute / 60))
        )
        object.__setattr__(self, "calls_to_start", computed_start)
        object.__setattr__(self, "calls_per_minute", float(calls_per_minute))
        object.__setattr__(self, "estimated_abandonment_risk", float(estimated_abandonment_risk))
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "reasons", reasons)


@dataclass(frozen=True)
class SafetyDecision:
    approved_calls_to_start: int
    approved_calls_per_minute: float
    action: str  # APPROVE, REDUCE, REJECT, PAUSE, FALLBACK_PROGRESSIVE, IDLE
    reason: str = ""
    reasons: tuple[str, ...] = ()

    def __init__(
        self,
        approved_calls_per_minute: float,
        action: str,
        reasons: tuple[str, ...] = (),
        approved_calls_to_start: int | None = None,
        reason: str = "",
    ) -> None:
        computed_start = (
            approved_calls_to_start
            if approved_calls_to_start is not None
            else max(0, round(approved_calls_per_minute / 60))
        )
        object.__setattr__(self, "approved_calls_to_start", computed_start)
        object.__setattr__(self, "approved_calls_per_minute", float(approved_calls_per_minute))
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "reasons", reasons)


@dataclass
class SafetyController:
    max_calls_per_minute: float = 600.0
    max_concurrency: int = 100
    max_abandonment_risk: float = 0.03
    critical_abandonment_risk: float = 0.05
    min_provider_health: float = 0.5
    max_input_age_seconds: float = 30.0
    min_sample_size: int = 10
    sharp_drop_threshold: float = 0.20
    interventions: int = 0
    history: list[SafetyDecision] = field(default_factory=list)

    def approve(self, proposal: PacingProposal, inputs: PacingInputs) -> SafetyDecision:
        reasons: list[str] = []
        action = "APPROVE"
        free_agents = max(0, inputs.available_agents)
        expected_free = free_agents + inputs.expected_finishing_agents
        proposed_calls = proposal.calls_to_start

        def risk_adjusted_answers(total_attempts: int, answer_probability: float) -> float:
            # A 2.33-sigma one-sided margin guards batch approvals against answer variance.
            answer_margin = 2.33 * math.sqrt(
                total_attempts * answer_probability * (1.0 - answer_probability)
            )
            return total_attempts * answer_probability + answer_margin

        def capacity_limited_calls(max_calls: int, answer_probability: float) -> tuple[int, float]:
            low = 0
            high = max_calls
            while low < high:
                candidate = (low + high + 1) // 2
                total_attempts = inputs.calls_in_flight + candidate
                if risk_adjusted_answers(total_attempts, answer_probability) <= expected_free:
                    low = candidate
                else:
                    high = candidate - 1
            total_attempts = inputs.calls_in_flight + low
            return low, risk_adjusted_answers(total_attempts, answer_probability)

        # Start from proposal rate and caps
        rate = max(0.0, min(proposal.calls_per_minute, self.max_calls_per_minute))
        if proposal.calls_per_minute > self.max_calls_per_minute:
            reasons.append("configured_rate_cap")

        stale = (inputs.now_seconds - inputs.observed_at_seconds) > self.max_input_age_seconds
        unreliable = stale or (inputs.sample_count < self.min_sample_size and stale)
        unhealthy = (
            inputs.provider_health < self.min_provider_health or inputs.provider_failure_rate > 0.5
        )

        # Trigger 1: Stale inputs or provider outage -> PAUSE / REJECT
        if unreliable or unhealthy:
            rate = 0.0
            reasons.append("stale_or_unreliable_inputs" if unreliable else "provider_health_limit")
            action = (
                "PAUSE"
                if (unreliable or inputs.provider_health < self.min_provider_health)
                else "REJECT"
            )
            age_sec = inputs.now_seconds - inputs.observed_at_seconds
            reason_line = (
                f"paused: inputs stale ({age_sec:.1f}s > {self.max_input_age_seconds}s)"
                if unreliable
                else (
                    f"rejected: provider unhealthy (health={inputs.provider_health:.2f}, "
                    f"failure_rate={inputs.provider_failure_rate:.2f})"
                )
            )

        # Trigger 2: Provider timing out -> REJECT
        elif inputs.provider_timeout_rate > 0.3:
            rate = 0.0
            reasons.append("provider_timeout_limit")
            action = "REJECT"
            reason_line = (
                f"rejected: provider timeout rate {inputs.provider_timeout_rate:.2%} > 30%"
            )

        # Trigger 3: No available agents -> IDLE (do NOT count as reject)
        elif free_agents == 0 and inputs.pending_calls > 0:
            rate = 0.0
            reasons.append("no_available_agents")
            action = "IDLE"
            reason_line = "idle: no available agents"

        # Trigger 4: Small sample size (not stale) -> FALLBACK_PROGRESSIVE
        elif inputs.sample_count < self.min_sample_size:
            approved_calls = min(free_agents, inputs.pending_calls)
            rate = float(approved_calls * 60)
            reasons.append("small_sample_size")
            action = "FALLBACK_PROGRESSIVE"
            reason_line = (
                f"fallback to progressive: sample size {inputs.sample_count} < min "
                f"{self.min_sample_size}"
            )

        # Trigger 5: Critical rolling abandonment rate or proposal risk -> FALLBACK_PROGRESSIVE
        elif (
            inputs.recent_abandonment_rate > self.critical_abandonment_risk
            or proposal.estimated_abandonment_risk > self.critical_abandonment_risk
        ):
            approved_calls = min(free_agents, inputs.pending_calls)
            rate = float(approved_calls * 60)
            reasons.append("critical_abandonment_fallback")
            action = "FALLBACK_PROGRESSIVE"
            critical_risks = []
            if inputs.recent_abandonment_rate > self.critical_abandonment_risk:
                critical_risks.append(f"rolling abandon rate {inputs.recent_abandonment_rate:.1%}")
            if proposal.estimated_abandonment_risk > self.critical_abandonment_risk:
                critical_risks.append(
                    f"proposal abandonment risk {proposal.estimated_abandonment_risk:.1%}"
                )
            reason_line = (
                f"fallback to progressive: critical abandonment limit "
                f"{self.critical_abandonment_risk:.1%} exceeded by "
                f"{' and '.join(critical_risks)}"
            )

        # Trigger 6: Rolling abandonment rate or proposal risk above warning threshold -> REDUCE
        elif (
            inputs.recent_abandonment_rate > self.max_abandonment_risk
            or proposal.estimated_abandonment_risk > self.max_abandonment_risk
        ):
            rate = max(0.0, rate * 0.5)
            approved_calls = max(0, math.ceil(rate / 60)) if rate > 0 else 0
            reasons.append("abandonment_risk_reduction")
            action = "REDUCE"
            reason_line = (
                f"reduced to {rate / 60:.1f} cpm: abandon risk "
                f"exceeds limit {self.max_abandonment_risk:.1%}"
            )

        # Trigger 7: Sharp answer-rate drop -> REDUCE
        elif (
            inputs.baseline_answer_rate is not None
            and inputs.baseline_answer_rate > 0
            and (inputs.baseline_answer_rate - inputs.answer_rate) >= self.sharp_drop_threshold
        ):
            reduced_proposal = max(0, math.ceil(proposed_calls * 0.5))
            answer_p = max(
                0.01,
                min(
                    1.0,
                    max(inputs.answer_rate, inputs.baseline_answer_rate),
                ),
            )
            approved_calls, upper_answers = capacity_limited_calls(reduced_proposal, answer_p)
            rate = float(approved_calls * 60)
            reasons.append("sharp_answer_rate_drop")
            action = "REDUCE"
            reason_line = (
                f"reduced to {approved_calls}: sharp answer-rate drop from "
                f"{inputs.baseline_answer_rate:.2f} to {inputs.answer_rate:.2f}; "
                f"risk-adjusted answer cap {upper_answers:.1f} "
                f"<= free agents ({expected_free})"
            )

        # Trigger 8: Risk-adjusted cap on expected answers from new and in-flight calls
        else:
            answer_p = max(
                0.50, min(1.0, inputs.answer_rate if inputs.sample_count >= 10 else 0.50)
            )
            flight_answers = inputs.calls_in_flight * answer_p
            new_answers = proposed_calls * answer_p
            total_answers = flight_answers + new_answers

            approved_calls, upper_answers = capacity_limited_calls(proposed_calls, answer_p)
            proposed_upper_answers = risk_adjusted_answers(
                inputs.calls_in_flight + proposed_calls, answer_p
            )

            if approved_calls < proposed_calls:
                rate = float(approved_calls * 60)
                reasons.append("hard_cap_free_agents")
                action = "REDUCE"
                reason_line = (
                    f"reduced to {approved_calls}: hard cap expected answers "
                    f"({new_answers:.1f} new + {flight_answers:.1f} flight = {total_answers:.1f}); "
                    f"proposed risk-adjusted answers {proposed_upper_answers:.1f} "
                    f"> free agents ({expected_free}); approved bound {upper_answers:.1f}"
                )
            else:
                approved_calls = proposed_calls
                action = "APPROVE"
                reason_line = (
                    f"approved {approved_calls}: risk-adjusted answers "
                    f"({upper_answers:.1f}) <= free agents ({expected_free})"
                )

        # Concurrency limit
        free_conc = max(0, self.max_concurrency - inputs.busy_agents)
        if rate > float(free_conc * 60):
            rate = float(free_conc * 60)
            if action == "APPROVE":
                action = "REDUCE"
                reason_line = (
                    f"reduced to {rate / 60:.0f} calls: concurrency cap {self.max_concurrency}"
                )
                reasons.append("concurrency_cap")

        calls_to_start = max(0, round(rate / 60)) if rate > 0 else 0
        if action == "APPROVE" and calls_to_start < proposed_calls:
            action = "REDUCE"

        decision = SafetyDecision(
            approved_calls_per_minute=rate,
            action=action,
            reasons=tuple(reasons),
            approved_calls_to_start=calls_to_start,
            reason=reason_line,
        )
        if action not in ("APPROVE", "IDLE"):
            self.interventions += 1
        self.history.append(decision)
        return decision


def estimate_pacing(inputs: PacingInputs) -> PacingProposal:
    """Rule-based predictive proposal showing raw formula result, any cap applied,

    and the final number.
    """
    if inputs.mean_call_seconds <= 0 or inputs.mean_wrap_seconds < 0:
        return PacingProposal(
            0.0,
            1.0,
            ("invalid_duration_estimate",),
            calls_to_start=0,
            reason="raw=0, invalid duration estimate -> proposed 0",
        )

    expected_free = max(0, inputs.available_agents + inputs.expected_finishing_agents)

    # Determine answer rate
    if inputs.sample_count < 10:
        prior = 0.50
        effective_rate = prior
        window_note = (
            f"window={inputs.sample_count}/{inputs.window_size} < 10 -> using prior {prior:.2f}"
        )
    else:
        effective_rate = max(0.01, min(1.0, inputs.answer_rate))
        window_note = f"window={inputs.sample_count}/{inputs.window_size}"

    raw_val = (
        math.ceil(expected_free / effective_rate) if effective_rate > 0 and expected_free > 0 else 0
    )
    raw_formula = f"raw=ceil({expected_free}/{effective_rate:.2f})={raw_val}"

    # Step 1: subtract in_flight calls
    after_flight = max(0, raw_val - inputs.calls_in_flight)

    # Step 2: cap by pending calls
    final_calls = after_flight
    cap_reasons: list[str] = []
    if inputs.calls_in_flight > 0:
        cap_reasons.append(f"in_flight={inputs.calls_in_flight}")
    if final_calls > inputs.pending_calls:
        final_calls = inputs.pending_calls
        cap_reasons.append(f"pending_calls={inputs.pending_calls}")

    if inputs.pending_calls == 0:
        calls_to_start = 0
        reason = f"{window_note}, {raw_formula}, capped to 0 by pending_calls=0 -> proposed 0"
    elif expected_free == 0:
        calls_to_start = 0
        reason = f"{window_note}, {raw_formula}, capped to 0 by no_free_agents -> proposed 0"
    elif cap_reasons:
        calls_to_start = final_calls
        reasons_str = ", ".join(cap_reasons)
        reason = (
            f"{window_note}, {raw_formula}, capped to {calls_to_start} by {reasons_str} "
            f"-> proposed {calls_to_start}"
        )
    else:
        calls_to_start = final_calls
        reason = f"{window_note}, {raw_formula} -> proposed {calls_to_start}"

    total_agents = max(0, inputs.available_agents + inputs.busy_agents)
    occupancy = inputs.mean_call_seconds + inputs.mean_wrap_seconds
    capacity = total_agents * 60 / occupancy
    provider_factor = min(1.0, max(0.0, inputs.provider_health))
    offered = (
        (capacity / effective_rate)
        * provider_factor
        * (1.0 - min(1.0, max(0.0, inputs.provider_failure_rate)))
    )
    offered = min(offered, float(total_agents * 60))
    cpm = min(float(calls_to_start * 60), offered) if calls_to_start > 0 else 0.0

    # Risk metric for reporting
    risk = max(
        0.0,
        ((calls_to_start * effective_rate) - inputs.available_agents) / max(calls_to_start, 1),
    )

    return PacingProposal(
        calls_per_minute=cpm,
        estimated_abandonment_risk=risk,
        reasons=(),
        calls_to_start=calls_to_start,
        reason=reason,
    )
