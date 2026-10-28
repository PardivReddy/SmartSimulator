"""Progressive allocation and deterministic simulation orchestration."""

from __future__ import annotations

import random
from dataclasses import dataclass

from smartdialer.domain import (
    AGENT_TRANSITIONS,
    CALL_TRANSITIONS,
    AgentState,
    CallState,
    transition,
)
from smartdialer.metrics import SimulationMetrics
from smartdialer.pacing import PacingInputs, SafetyController, SlidingWindow, estimate_pacing
from smartdialer.providers import MockProvider, ProviderRetryPolicy, default_providers
from smartdialer.storage import Store

DEFAULT_RETRY_POLICY = ProviderRetryPolicy()


@dataclass
class Simulation:
    store: Store
    providers: tuple[MockProvider, ...]
    safety: SafetyController

    @classmethod
    def create(cls, path: str = ":memory:", seed: int = 42) -> Simulation:
        return cls(Store(path), default_providers(seed), SafetyController())

    def _apply_provider_event(
        self,
        call_id: str,
        provider: MockProvider,
        kind: str,
        *,
        now: float,
        payload: dict | None = None,
    ) -> None:
        sequence = self.store.next_event_sequence(call_id, provider.name)
        result = self.store.process_event(
            call_id,
            f"{call_id}:{provider.name}:{sequence}",
            sequence,
            kind,
            payload=payload,
            now=now,
            provider=provider.name,
        )
        if result != "APPLIED":
            raise RuntimeError(f"provider event was not applied: {result}")

    def _start_call(self, agent_id: str, provider: MockProvider, *, now: float) -> dict | None:
        if not provider.is_available:
            return None
        call = self.store.allocate(agent_id, now=now)
        if call is None:
            return None
        self._apply_provider_event(call["id"], provider, "INITIATED", now=now)
        return call

    def _ring_call(self, call_id: str, provider: MockProvider, *, now: float) -> None:
        self._apply_provider_event(call_id, provider, "RINGING", now=now)

    def _execute_ringing_call(
        self,
        call: dict,
        provider: MockProvider,
        *,
        now: float,
        retry_policy: ProviderRetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> dict[str, int | str | float]:
        event = provider.simulate()
        if event.kind == "ANSWERED":
            answered_at = now + event.delay_seconds
            self._apply_provider_event(call["id"], provider, "ANSWERED", now=answered_at)
            self._apply_provider_event(call["id"], provider, "CONNECTED", now=answered_at + 0.1)
            self._apply_provider_event(call["id"], provider, "COMPLETED", now=answered_at + 1)
            return {
                "attempted": 1,
                "failures": 0,
                "timeouts": 0,
                "retries_scheduled": 0,
                "elapsed_seconds": event.delay_seconds + 1,
            }

        reason = "NO_ANSWER"
        timeout = 0
        if event.kind == "FAILED":
            reason = "provider_unavailable" if not provider.is_available else "provider_timeout"
            timeout = 1
        failed_at = now + event.delay_seconds
        self._apply_provider_event(
            call["id"],
            provider,
            "FAILED",
            now=failed_at,
            payload={"reason": reason},
        )
        refreshed = self.store.call(call["id"])
        if refreshed is None:
            raise RuntimeError(f"failed call disappeared: {call['id']}")
        retry_number = refreshed["retry_count"] + 1
        retry_scheduled = (
            self.store.schedule_retry(
                call["id"],
                retry_at=failed_at + retry_policy.backoff_seconds(retry_number),
                max_retries=retry_policy.max_retries,
                now=failed_at,
            )
            if retry_number <= retry_policy.max_retries
            else False
        )
        return {
            "attempted": 1,
            "failures": int(event.kind == "FAILED"),
            "timeouts": timeout,
            "retries_scheduled": int(retry_scheduled),
            "elapsed_seconds": event.delay_seconds,
        }

    def run_due_retries(
        self,
        *,
        now: float,
        retry_policy: ProviderRetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> dict[str, object]:
        """Execute due retries only through their currently healthy mock provider."""
        result = {
            "due": 0,
            "not_due": 0,
            "deferred_provider_unavailable": 0,
            "deferred_no_agent": 0,
            "attempted": 0,
            "failures": 0,
            "timeouts": 0,
            "retries_scheduled": 0,
        }
        due_ids = {call["id"] for call in self.store.due_retries(now=now)}
        all_waiting = self.store._connection.execute(
            "SELECT id,provider FROM calls WHERE state='RETRY_WAIT'"
        ).fetchall()
        result["not_due"] = sum(row["id"] not in due_ids for row in all_waiting)
        result["due"] = len(due_ids)

        for retry in self.store.due_retries(now=now):
            provider = next(
                (item for item in self.providers if item.name == retry["provider"]),
                None,
            )
            if provider is None or not provider.is_available:
                result["deferred_provider_unavailable"] += 1
                continue
            reservation = self.store.claim_retry(retry["id"], now=now)
            if reservation is None:
                result["deferred_no_agent"] += 1
                continue
            if not provider.is_available:
                self.store.defer_retry(
                    retry["id"],
                    retry_at=now + retry_policy.initial_backoff_seconds,
                    now=now,
                )
                result["deferred_provider_unavailable"] += 1
                continue

            self._apply_provider_event(retry["id"], provider, "INITIATED", now=now)
            self._ring_call(retry["id"], provider, now=now + 0.1)
            attempt = self._execute_ringing_call(
                reservation,
                provider,
                now=now + 0.2,
                retry_policy=retry_policy,
            )
            for key in ("attempted", "failures", "timeouts", "retries_scheduled"):
                result[key] += int(attempt[key])
        return result

    def run(
        self,
        *,
        agents: int = 4,
        borrowers: int = 20,
        mode: str = "progressive",
        scenario: str = "normal",
    ) -> SimulationMetrics:
        if scenario == "provider_outage":
            raise ValueError("use run_provider_outage() for the provider-outage scenario")
        if scenario == "low_answer_rate":
            for provider in self.providers:
                provider.answer_probability = 0.0
        for index in range(agents):
            self.store.add_agent(f"agent-{index:04d}")
            if scenario == "no_available_agents":
                self.store.set_agent_state(f"agent-{index:04d}", "PAUSED")
        for index in range(borrowers):
            self.store.add_borrower(f"borrower-{index:04d}", priority=(borrowers - index))
        started = 0.0
        provider_health = sum(provider.is_available for provider in self.providers) / len(
            self.providers
        )
        inputs = PacingInputs(
            sum(provider.answer_probability for provider in self.providers) / len(self.providers),
            80.0,
            12.0,
            agents,
            0,
            borrowers,
            provider_health,
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
            if provider.is_available
        )
        remaining = min(
            borrowers,
            provider_capacity,
            agents if mode == "progressive" else max(0, round(allowed)),
        )
        elapsed = 1.0
        provider_errors = 0
        retries_scheduled = 0
        agent_busy_seconds = 0.0
        provider_attempts = [0 for _ in self.providers]
        retry_policy = DEFAULT_RETRY_POLICY
        for index in range(remaining):
            provider_index = next(
                (
                    offset
                    for offset in range(len(self.providers))
                    if provider_attempts[offset]
                    < min(
                        self.providers[offset].rate_limit_per_minute,
                        self.providers[offset].concurrency_limit,
                    )
                    and self.providers[offset].is_available
                ),
                None,
            )
            if provider_index is None:
                break
            provider = self.providers[provider_index]
            call = self._start_call(f"agent-{index:04d}", provider, now=started)
            if call is None:
                continue
            provider_attempts[provider_index] += 1
            self._ring_call(call["id"], provider, now=started + 0.1)
            outcome = self._execute_ringing_call(
                call,
                provider,
                now=started + 0.2,
                retry_policy=retry_policy,
            )
            elapsed = max(elapsed, float(outcome["elapsed_seconds"]))
            provider_errors += int(outcome["failures"])
            retries_scheduled += int(outcome["retries_scheduled"])
            if outcome["attempted"] and outcome["failures"] == 0:
                agent_busy_seconds += provider.duration_seconds + 12.0
        counts = self.store.counts()
        return SimulationMetrics.from_states(
            counts,
            elapsed_seconds=elapsed,
            retries=retries_scheduled,
            safety_interventions=self.safety.interventions,
            provider_errors=provider_errors,
            agent_count=agents,
            agent_busy_seconds=agent_busy_seconds,
        )

    def run_provider_outage(self, *, agents: int = 4, borrowers: int = 20) -> dict[str, object]:
        """Demonstrate an outage, bounded retry/backoff, pacing pause, and recovery."""
        if agents < 2 or borrowers < 3:
            raise ValueError("provider-outage scenario requires at least 2 agents and 3 borrowers")

        for index in range(agents):
            self.store.add_agent(f"agent-{index:04d}")
        for index in range(borrowers):
            self.store.add_borrower(f"borrower-{index:04d}", priority=borrowers - index)

        policy = ProviderRetryPolicy(max_retries=1, initial_backoff_seconds=5.0)
        initial_status = {
            provider.name: "AVAILABLE" if provider.is_available else "UNAVAILABLE"
            for provider in self.providers
        }
        existing_provider = self.providers[1]
        existing = self._start_call("agent-0000", existing_provider, now=0)
        if existing is None:
            raise RuntimeError("could not reserve the existing in-progress call")
        self._ring_call(existing["id"], existing_provider, now=1)

        failed_provider = self.providers[0]
        retry_call = self._start_call("agent-0001", failed_provider, now=2)
        if retry_call is None:
            raise RuntimeError("could not reserve the provider-timeout call")
        self._ring_call(retry_call["id"], failed_provider, now=3)

        for provider in self.providers:
            provider.set_available(False)
        outage_status = {
            provider.name: "AVAILABLE" if provider.is_available else "UNAVAILABLE"
            for provider in self.providers
        }

        timeout_result = self._execute_ringing_call(
            retry_call,
            failed_provider,
            now=4,
            retry_policy=policy,
        )
        timeout_at = 4 + failed_provider.timeout_seconds
        retry_at = timeout_at + policy.backoff_seconds(1)
        retry_scheduled = int(timeout_result["retries_scheduled"])

        calls_before_new_work = self.store._connection.execute(
            "SELECT COUNT(*) FROM calls"
        ).fetchone()[0]
        healthy_provider = next(
            (provider for provider in self.providers if provider.is_available), None
        )
        new_call = (
            self._start_call("agent-0002", healthy_provider, now=timeout_at)
            if healthy_provider is not None
            else None
        )
        calls_after_new_work = self.store._connection.execute(
            "SELECT COUNT(*) FROM calls"
        ).fetchone()[0]
        if new_call is not None or calls_after_new_work != calls_before_new_work:
            raise RuntimeError("new work was allocated while the provider outage was active")
        new_calls_blocked = 1

        pacing_inputs = PacingInputs(
            answer_rate=(
                sum(provider.answer_probability for provider in self.providers)
                / len(self.providers)
            ),
            mean_call_seconds=80.0,
            mean_wrap_seconds=12.0,
            available_agents=agents - 1,
            busy_agents=1,
            pending_calls=borrowers - 2,
            provider_health=sum(provider.is_available for provider in self.providers)
            / len(self.providers),
            provider_failure_rate=1.0,
            observed_at_seconds=timeout_at,
            now_seconds=timeout_at,
            sample_count=100,
        )
        proposal = estimate_pacing(pacing_inputs)
        decision = self.safety.approve(proposal, pacing_inputs)
        before_backoff = self.run_due_retries(now=retry_at - 1, retry_policy=policy)
        during_outage = self.run_due_retries(now=retry_at, retry_policy=policy)
        if self.store.call(retry_call["id"])["state"] != "RETRY_WAIT":
            raise RuntimeError("retry changed state before provider recovery")

        failed_provider.set_available(True)
        failed_provider.answer_probability = 1.0
        failed_provider.failure_rate = 0.0
        existing_provider.set_available(True)
        recovered_status = {
            provider.name: "AVAILABLE" if provider.is_available else "UNAVAILABLE"
            for provider in self.providers
        }
        after_recovery = self.run_due_retries(now=retry_at, retry_policy=policy)
        if after_recovery["attempted"] != 1:
            raise RuntimeError("eligible retry was not resumed after provider recovery")

        final_calls = {
            call_id: self.store.call(call_id) for call_id in (existing["id"], retry_call["id"])
        }
        return {
            "label": "SIMULATED_PROVIDER_OUTAGE",
            "provider_status": {
                "initial": initial_status,
                "during_outage": {name: status for name, status in outage_status.items()},
                "after_recovery": {
                    name: "AVAILABLE" if available else "UNAVAILABLE"
                    for name, available in recovered_status.items()
                },
            },
            "calls_attempted": 2 + after_recovery["attempted"],
            "failures": int(timeout_result["failures"]) + after_recovery["failures"],
            "timeouts": int(timeout_result["timeouts"]) + after_recovery["timeouts"],
            "retries_scheduled": retry_scheduled + after_recovery["retries_scheduled"],
            "retry_backoff_seconds": policy.backoff_seconds(1),
            "retry_before_backoff_elapsed": before_backoff["attempted"] > 0,
            "retry_deferred_during_outage": during_outage["deferred_provider_unavailable"],
            "retry_not_due_before_backoff": before_backoff["not_due"],
            "new_calls_blocked_during_outage": new_calls_blocked,
            "pacing": {
                "proposed_calls_per_minute": proposal.calls_per_minute,
                "approved_calls_per_minute": decision.approved_calls_per_minute,
                "safety_action": decision.action,
                "safety_reasons": list(decision.reasons),
            },
            "retry_call_id": retry_call["id"],
            "retry_borrower_id": retry_call["borrower_id"],
            "retry_agent_id": final_calls[retry_call["id"]]["agent_id"],
            "final_call_states": {
                call_id: call["state"] if call is not None else "MISSING"
                for call_id, call in final_calls.items()
            },
            "final_retry_count": (
                final_calls[retry_call["id"]]["retry_count"]
                if final_calls[retry_call["id"]] is not None
                else 0
            ),
            "retry_execution": {
                "before_backoff": before_backoff,
                "during_outage": during_outage,
                "after_recovery": after_recovery,
            },
        }


def validate_transition_examples() -> bool:
    return (
        transition(AgentState.AVAILABLE, AgentState.RESERVED, AGENT_TRANSITIONS)
        is AgentState.RESERVED
        and transition(CallState.ANSWERED, CallState.CONNECTED, CALL_TRANSITIONS)
        is CallState.CONNECTED
    )


@dataclass
class _SimActiveCall:
    call_id: str
    borrower_id: str
    agent_id: str
    provider_name: str
    initiated_at: float
    ring_until: float
    will_answer: bool
    state: str = "RINGING"
    connected_until: float = 0.0
    wrap_until: float = 0.0
    talk_duration: float = 0.0


def run_scenario(
    scenario: str,
    *,
    seed: int = 42,
    database: str = ":memory:",
    duration_ticks: int = 240,
) -> dict[str, object]:
    """Execute a discrete-time, deterministic simulation of required scenarios."""
    scenario = scenario.strip()
    rng = random.Random(seed)
    store = Store(database)
    sliding_window = SlidingWindow(size=50)

    # Fast & reliable ProviderA, Slow with failures & timeouts ProviderB
    provider_a = MockProvider("ProviderA", 0.5, 2.0, 90.0, 0.01, 120, 50, seed=seed)
    provider_b = MockProvider(
        "ProviderB", 0.5, 5.0, 90.0, 0.08, 60, 25, seed=seed + 1, timeout_seconds=12.0
    )
    providers = (provider_a, provider_b)

    # Setup scenario parameters
    if scenario == "A":
        initial_agents = 30
        initial_borrowers = 150
        answer_prob = 0.20
        talk_time = 120.0
    elif scenario == "B":
        initial_agents = 30
        initial_borrowers = 150
        answer_prob = 0.50
        talk_time = 90.0
    elif scenario == "C":
        initial_agents = 30
        initial_borrowers = 150
        answer_prob = 0.70
        talk_time = 180.0
    elif scenario == "D":
        initial_agents = 40
        initial_borrowers = 200
        answer_prob = 0.70
        talk_time = 180.0
    elif scenario == "agent-drop":
        initial_agents = 100
        initial_borrowers = 300
        answer_prob = 0.50
        talk_time = 90.0
    elif scenario == "outage":
        initial_agents = 30
        initial_borrowers = 150
        answer_prob = 0.50
        talk_time = 90.0
    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    for p in providers:
        p.answer_probability = answer_prob
        p.duration_seconds = talk_time

    for idx in range(initial_agents):
        store.add_agent(f"agent-{idx:04d}")
    for idx in range(initial_borrowers):
        store.add_borrower(f"borrower-{idx:04d}", priority=(initial_borrowers - idx))

    safety = SafetyController(
        max_calls_per_minute=600.0,
        max_concurrency=initial_agents,
        min_sample_size=10,
        max_abandonment_risk=0.03,
    )

    active_calls: dict[str, _SimActiveCall] = {}
    calls_initiated = 0
    calls_connected = 0
    abandoned_calls = 0
    total_busy_agent_seconds = 0.0
    sample_pacing_reasons: list[str] = []
    sample_safety_reasons: list[str] = []
    decision_counts = {
        "APPROVE": 0,
        "REDUCE": 0,
        "REJECT": 0,
        "FALLBACK_PROGRESSIVE": 0,
        "PAUSE": 0,
    }

    agent_drop_tick = 30 if scenario == "agent-drop" else -1
    agent_drop_occurred = False
    adjustment_latency = 0

    outage_start_tick = 40 if scenario == "outage" else -1
    outage_end_tick = 80 if scenario == "outage" else -1
    new_calls_during_outage = 0
    retries_scheduled_during_outage = 0

    wrap_duration = 5.0
    lookahead = 15.0
    retry_policy = ProviderRetryPolicy(max_retries=2, initial_backoff_seconds=10.0)

    for tick in range(duration_ticks):
        now = float(tick)

        if scenario == "D" and tick == 120:
            for p in providers:
                p.answer_probability = 0.10
                p.duration_seconds = 60.0
            answer_prob = 0.10
            talk_time = 60.0

        if scenario == "agent-drop" and tick == agent_drop_tick and not agent_drop_occurred:
            for idx in range(60, 100):
                aid = f"agent-{idx:04d}"
                row = store._connection.execute(
                    "SELECT state FROM agents WHERE id=?", (aid,)
                ).fetchone()
                if row and row["state"] == "AVAILABLE":
                    store._connection.execute(
                        "UPDATE agents SET state='OFFLINE' WHERE id=?", (aid,)
                    )
            agent_drop_occurred = True

        if scenario == "outage":
            if tick == outage_start_tick:
                provider_a.set_available(False)
                provider_b.set_available(False)
            elif tick == outage_end_tick:
                provider_a.set_available(True)
                provider_b.set_available(True)

        # 1. Update in-flight calls
        ended_call_ids = []
        for cid, ac in list(active_calls.items()):
            if ac.state == "RINGING" and now >= ac.ring_until:
                provider = provider_a if ac.provider_name == "ProviderA" else provider_b
                if not provider.is_available:
                    seq = store.next_event_sequence(cid, provider.name)
                    store.process_event(
                        cid,
                        f"{cid}:{provider.name}:{seq}",
                        seq,
                        "FAILED",
                        payload={"reason": "provider_unavailable"},
                        now=now,
                        provider=provider.name,
                    )
                    store.transition_agent(ac.agent_id, "AVAILABLE")
                    store.schedule_retry(
                        cid,
                        retry_at=now + retry_policy.backoff_seconds(1),
                        max_retries=retry_policy.max_retries,
                        now=now,
                    )
                    ended_call_ids.append(cid)
                    if scenario == "outage" and outage_start_tick <= tick < outage_end_tick:
                        retries_scheduled_during_outage += 1
                    sliding_window.record_call(answered=False, talk_seconds=0.0, abandoned=False)
                    continue

                if ac.will_answer:
                    seq = store.next_event_sequence(cid, provider.name)
                    store.process_event(
                        cid,
                        f"{cid}:{provider.name}:{seq}",
                        seq,
                        "ANSWERED",
                        now=now,
                        provider=provider.name,
                    )
                    seq2 = store.next_event_sequence(cid, provider.name)
                    store.process_event(
                        cid,
                        f"{cid}:{provider.name}:{seq2}",
                        seq2,
                        "CONNECTED",
                        now=now + 0.1,
                        provider=provider.name,
                    )
                    ac.state = "CONNECTED"
                    ac.connected_until = now + ac.talk_duration
                    calls_connected += 1

                    if provider.name == "ProviderB":
                        dup_res = store.process_event(
                            cid,
                            f"{cid}:{provider.name}:{seq2}",
                            seq2,
                            "CONNECTED",
                            now=now + 0.1,
                            provider=provider.name,
                        )
                        assert dup_res == "DUPLICATE"
                        stale_res = store.process_event(
                            cid,
                            f"{cid}:{provider.name}:stale",
                            1,
                            "RINGING",
                            now=now + 0.1,
                            provider=provider.name,
                        )
                        assert stale_res in ("DUPLICATE", "STALE")
                else:
                    seq = store.next_event_sequence(cid, provider.name)
                    store.process_event(
                        cid,
                        f"{cid}:{provider.name}:{seq}",
                        seq,
                        "FAILED",
                        payload={"reason": "NO_ANSWER"},
                        now=now,
                        provider=provider.name,
                    )
                    store.transition_agent(ac.agent_id, "AVAILABLE")
                    sliding_window.record_call(answered=False, talk_seconds=0.0, abandoned=False)
                    ended_call_ids.append(cid)

            elif ac.state == "CONNECTED" and now >= ac.connected_until:
                provider = provider_a if ac.provider_name == "ProviderA" else provider_b
                seq = store.next_event_sequence(cid, provider.name)
                store.process_event(
                    cid,
                    f"{cid}:{provider.name}:{seq}",
                    seq,
                    "COMPLETED",
                    now=now,
                    provider=provider.name,
                )
                ac.state = "WRAP_UP"
                ac.wrap_until = now + wrap_duration
                sliding_window.record_call(
                    answered=True, talk_seconds=ac.talk_duration, abandoned=False
                )

            elif ac.state == "WRAP_UP" and now >= ac.wrap_until:
                store.transition_agent(ac.agent_id, "AVAILABLE")
                ended_call_ids.append(cid)

        for cid in ended_call_ids:
            active_calls.pop(cid, None)

        # 2. Run due retries if healthy
        if any(p.is_available for p in providers):
            due = store.due_retries(now=now)
            for r in due:
                claim = store.claim_retry(r["id"], now=now)
                if claim:
                    p = provider_a if provider_a.is_available else provider_b
                    seq = store.next_event_sequence(r["id"], p.name)
                    store.process_event(
                        r["id"],
                        f"{r['id']}:{p.name}:{seq}",
                        seq,
                        "INITIATED",
                        now=now,
                        provider=p.name,
                    )
                    seq2 = store.next_event_sequence(r["id"], p.name)
                    store.process_event(
                        r["id"],
                        f"{r['id']}:{p.name}:{seq2}",
                        seq2,
                        "RINGING",
                        now=now + 0.5,
                        provider=p.name,
                    )
                    will_ans = rng.random() < p.answer_probability
                    active_calls[r["id"]] = _SimActiveCall(
                        call_id=r["id"],
                        borrower_id=r["borrower_id"],
                        agent_id=claim["agent_id"],
                        provider_name=p.name,
                        initiated_at=now,
                        ring_until=now + p.ringing_delay_seconds,
                        will_answer=will_ans,
                        talk_duration=p.duration_seconds,
                    )

        # 3. Gather real state from DB
        avail_agents = store._connection.execute(
            "SELECT COUNT(*) FROM agents WHERE state='AVAILABLE'"
        ).fetchone()[0]
        busy_agents = store._connection.execute(
            """SELECT COUNT(*) FROM agents WHERE state IN
               ('RESERVED','DIALING','CONNECTED','WRAP_UP')"""
        ).fetchone()[0]
        total_busy_agent_seconds += busy_agents * 1.0

        if (
            scenario == "agent-drop"
            and agent_drop_occurred
            and adjustment_latency == 0
            and tick > agent_drop_tick
        ):
            adjustment_latency = tick - agent_drop_tick

        finishing_soon = sum(
            1
            for c in active_calls.values()
            if c.state == "CONNECTED" and (c.connected_until - now) <= lookahead
        )
        in_flight = sum(1 for c in active_calls.values() if c.state == "RINGING")
        pending_borrowers = store._connection.execute(
            """SELECT COUNT(*) FROM borrowers b WHERE b.eligible=1 AND NOT EXISTS
               (SELECT 1 FROM calls c WHERE c.borrower_id=b.id AND c.state IN
                ('QUEUED','RESERVED','INITIATED','RINGING','ANSWERED','CONNECTED','RETRY_WAIT','UNCERTAIN'))"""
        ).fetchone()[0]

        est_answer_rate = (
            sliding_window.answer_rate if sliding_window.sample_count >= 10 else answer_prob
        )
        p_health = sum(p.is_available for p in providers) / len(providers)
        p_failure = sum(p.failure_rate for p in providers) / len(providers)

        pacing_inputs = PacingInputs(
            answer_rate=est_answer_rate,
            mean_call_seconds=(
                sliding_window.average_talk_time if sliding_window.sample_count >= 10 else talk_time
            ),
            mean_wrap_seconds=wrap_duration,
            available_agents=avail_agents,
            busy_agents=busy_agents,
            pending_calls=pending_borrowers,
            provider_health=p_health,
            provider_failure_rate=p_failure,
            expected_finishing_agents=finishing_soon,
            calls_in_flight=in_flight,
            baseline_answer_rate=answer_prob if scenario == "D" else None,
            recent_abandonment_rate=sliding_window.abandonment_rate,
            window_size=sliding_window.size,
            sample_count=sliding_window.sample_count,
            observed_at_seconds=now,
            now_seconds=now,
        )

        proposal = estimate_pacing(pacing_inputs)
        decision = safety.approve(proposal, pacing_inputs)

        d_action = decision.action
        if d_action in decision_counts:
            decision_counts[d_action] += 1
        elif d_action == "PAUSE":
            decision_counts["PAUSE"] += 1

        if len(sample_pacing_reasons) < 3 and proposal.reason and proposal.calls_to_start > 0:
            sample_pacing_reasons.append(f"[t={int(now)}s] {proposal.reason}")
        if len(sample_safety_reasons) < 3 and decision.reason:
            sample_safety_reasons.append(f"[t={int(now)}s] {decision.reason}")

        # 4. Dial approved calls
        approved_starts = decision.approved_calls_to_start
        calls_to_dial = min(approved_starts, avail_agents, pending_borrowers)

        if (
            scenario == "outage"
            and outage_start_tick <= tick < outage_end_tick
            and calls_to_dial > 0
        ):
            new_calls_during_outage += calls_to_dial

        for _ in range(calls_to_dial):
            agent_row = store._connection.execute(
                "SELECT id FROM agents WHERE state='AVAILABLE' ORDER BY id LIMIT 1"
            ).fetchone()
            if not agent_row:
                break
            chosen_provider = next((p for p in providers if p.is_available), None)
            if not chosen_provider:
                break
            call_res = store.allocate(agent_row["id"], now=now)
            if not call_res:
                continue

            cid = call_res["id"]
            calls_initiated += 1
            seq = store.next_event_sequence(cid, chosen_provider.name)
            store.process_event(
                cid,
                f"{cid}:{chosen_provider.name}:{seq}",
                seq,
                "INITIATED",
                now=now,
                provider=chosen_provider.name,
            )
            seq2 = store.next_event_sequence(cid, chosen_provider.name)
            store.process_event(
                cid,
                f"{cid}:{chosen_provider.name}:{seq2}",
                seq2,
                "RINGING",
                now=now + 0.2,
                provider=chosen_provider.name,
            )

            will_ans = rng.random() < chosen_provider.answer_probability
            active_calls[cid] = _SimActiveCall(
                call_id=cid,
                borrower_id=call_res["borrower_id"],
                agent_id=agent_row["id"],
                provider_name=chosen_provider.name,
                initiated_at=now,
                ring_until=now + chosen_provider.ringing_delay_seconds,
                will_answer=will_ans,
                talk_duration=chosen_provider.duration_seconds,
            )

    total_agent_seconds = float(initial_agents * duration_ticks)
    agent_utilization_pct = (
        min(100.0, round((total_busy_agent_seconds / total_agent_seconds) * 100, 2))
        if total_agent_seconds > 0
        else 0.0
    )

    stranded_calls = store._connection.execute(
        """SELECT COUNT(*) FROM calls c
           WHERE c.state IN ('INITIATED','RINGING','CONNECTED')
           AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.id=c.agent_id)"""
    ).fetchone()[0]

    final_available = store._connection.execute(
        "SELECT COUNT(*) FROM agents WHERE state='AVAILABLE'"
    ).fetchone()[0]

    store.close()

    return {
        "scenario": scenario,
        "seed": seed,
        "duration_seconds": duration_ticks,
        "total_agents": initial_agents,
        "final_available_agents": final_available,
        "agent_utilization_pct": agent_utilization_pct,
        "calls_initiated": calls_initiated,
        "calls_connected": calls_connected,
        "abandoned_calls": abandoned_calls,
        "pacing_proposals_count": duration_ticks,
        "safety_decisions": decision_counts,
        "stranded_calls": stranded_calls,
        "adjustment_latency_ticks": adjustment_latency if scenario == "agent-drop" else 0,
        "sample_pacing_reasons": sample_pacing_reasons,
        "sample_safety_reasons": sample_safety_reasons,
        "new_calls_during_outage": new_calls_during_outage,
        "retries_scheduled_during_outage": retries_scheduled_during_outage,
    }


def format_scenario_table(res: dict) -> str:
    """Format scenario simulation result as a compact ASCII table."""
    dec = res["safety_decisions"]
    approve = dec.get("APPROVE", 0)
    reduce_cnt = dec.get("REDUCE", 0)
    reject = dec.get("REJECT", 0) + dec.get("PAUSE", 0)
    fallback = dec.get("FALLBACK_PROGRESSIVE", 0)

    lines = [
        "=" * 74,
        f"SCENARIO: {res['scenario']} | Seed: {res['seed']} | Duration: {res['duration_seconds']}s",
        "=" * 74,
        f"{'Metric':<38} | {'Value':<30}",
        "-" * 38 + "-+-" + "-" * 30,
        f"{'Agent Utilization':<38} | {res['agent_utilization_pct']:.2f}%",
        f"{'Calls Initiated':<38} | {res['calls_initiated']}",
        f"{'Calls Connected':<38} | {res['calls_connected']}",
        f"{'Abandoned Connected Calls':<38} | {res['abandoned_calls']}",
        f"{'Pacing Proposals Evaluated':<38} | {res['pacing_proposals_count']}",
        f"{'Safety (Approve/Red/Rej/FB)':<38} | {approve}/{reduce_cnt}/{reject}/{fallback}",
        f"{'Stranded Calls (Target: 0)':<38} | {res['stranded_calls']}",
    ]
    if res["scenario"] == "agent-drop":
        lines.append(
            f"{'Adjustment Latency (ticks)':<38} | {res['adjustment_latency_ticks']} tick(s)"
        )
    if res["scenario"] == "outage":
        blocked_str = (
            "YES (0 placed)"
            if res["new_calls_during_outage"] == 0
            else str(res["new_calls_during_outage"])
        )
        lines.append(f"{'New Calls Blocked During Outage':<38} | {blocked_str}")
        lines.append(
            f"{'Retries Scheduled During Outage':<38} | {res['retries_scheduled_during_outage']}"
        )

    lines.append("-" * 74)
    lines.append("Sample Reason Lines:")
    for r in res.get("sample_pacing_reasons", [])[:2]:
        lines.append(f"  [Pacing] {r}")
    for r in res.get("sample_safety_reasons", [])[:2]:
        lines.append(f"  [Safety] {r}")
    lines.append("=" * 74)
    return "\n".join(lines)
