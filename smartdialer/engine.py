"""Progressive allocation and deterministic simulation orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from smartdialer.domain import (
    AGENT_TRANSITIONS,
    CALL_TRANSITIONS,
    AgentState,
    CallState,
    transition,
)
from smartdialer.metrics import SimulationMetrics
from smartdialer.pacing import PacingInputs, SafetyController, estimate_pacing
from smartdialer.providers import MockProvider, default_providers
from smartdialer.storage import Store


@dataclass
class Simulation:
    store: Store
    providers: tuple[MockProvider, ...]
    safety: SafetyController

    @classmethod
    def create(cls, path: str = ":memory:", seed: int = 42) -> Simulation:
        return cls(Store(path), default_providers(seed), SafetyController())

    def run(
        self,
        *,
        agents: int = 4,
        borrowers: int = 20,
        mode: str = "progressive",
        scenario: str = "normal",
    ) -> SimulationMetrics:
        if scenario == "low_answer_rate":
            for provider in self.providers:
                provider.answer_probability = 0.0
        elif scenario == "provider_outage":
            for provider in self.providers:
                provider.available = False
        for index in range(agents):
            self.store.add_agent(f"agent-{index:04d}")
            if scenario == "no_available_agents":
                self.store.set_agent_state(f"agent-{index:04d}", "PAUSED")
        for index in range(borrowers):
            self.store.add_borrower(f"borrower-{index:04d}", priority=(borrowers - index))
        started = 0.0
        inputs = PacingInputs(
            sum(provider.answer_probability for provider in self.providers) / len(self.providers),
            80.0,
            12.0,
            agents,
            0,
            borrowers,
            sum(provider.available for provider in self.providers) / len(self.providers),
            sum(provider.failure_rate for provider in self.providers) / len(self.providers),
            observed_at_seconds=started,
            now_seconds=started,
            sample_count=100,
        )
        allowed = float(agents)
        if mode == "predictive":
            proposed = estimate_pacing(inputs)
            allowed = self.safety.approve(proposed, inputs).approved_calls_per_minute / 60
        provider_capacity = sum(
            min(provider.rate_limit_per_minute, provider.concurrency_limit)
            for provider in self.providers
            if provider.available
        )
        remaining = min(
            borrowers,
            provider_capacity,
            agents if mode == "progressive" else max(1, round(allowed)),
        )
        elapsed = 1.0
        provider_errors = 0
        agent_busy_seconds = 0.0
        provider_attempts = [0 for _ in self.providers]
        for index in range(remaining):
            call = self.store.allocate(f"agent-{index:04d}", now=started)
            if call is None:
                continue
            provider_index = next(
                (
                    offset
                    for offset in range(len(self.providers))
                    if provider_attempts[offset]
                    < min(
                        self.providers[offset].rate_limit_per_minute,
                        self.providers[offset].concurrency_limit,
                    )
                    and self.providers[offset].available
                ),
                None,
            )
            if provider_index is None:
                self.store.transition_call(call["id"], "CANCELLED", reason="provider_capacity")
                continue
            provider = self.providers[provider_index]
            provider_attempts[provider_index] += 1
            self.store.transition_call(
                call["id"], "INITIATED", provider=provider.name, now=started + 1
            )
            self.store.transition_call(call["id"], "RINGING", now=started + 2)
            event = provider.simulate()
            elapsed = max(elapsed, event.delay_seconds + 1)
            if event.kind == "ANSWERED":
                agent_busy_seconds += provider.duration_seconds + 12.0
                self.store.transition_call(
                    call["id"], "ANSWERED", now=started + event.delay_seconds
                )
                self.store.transition_call(
                    call["id"], "CONNECTED", now=started + event.delay_seconds + 0.1
                )
                self.store.transition_call(
                    call["id"], "COMPLETED", now=started + event.delay_seconds + 1
                )
            else:
                provider_errors += int(event.kind == "FAILED")
                self.store.transition_call(
                    call["id"], "FAILED", reason=event.kind, now=started + event.delay_seconds
                )
        counts = self.store.counts()
        return SimulationMetrics.from_states(
            counts,
            elapsed_seconds=elapsed,
            safety_interventions=self.safety.interventions,
            provider_errors=provider_errors,
            agent_count=agents,
            agent_busy_seconds=agent_busy_seconds,
        )


def validate_transition_examples() -> bool:
    return (
        transition(AgentState.AVAILABLE, AgentState.RESERVED, AGENT_TRANSITIONS)
        is AgentState.RESERVED
        and transition(CallState.ANSWERED, CallState.CONNECTED, CALL_TRANSITIONS)
        is CallState.CONNECTED
    )
