"""Seeded, local-only mock providers."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderEvent:
    kind: str
    delay_seconds: float


@dataclass
class MockProvider:
    name: str
    answer_probability: float
    ringing_delay_seconds: float
    duration_seconds: float
    failure_rate: float
    rate_limit_per_minute: int
    concurrency_limit: int
    available: bool = True
    seed: int = 42
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        self._random = random.Random(self.seed)

    def simulate(self) -> ProviderEvent:
        if not self.available:
            return ProviderEvent("FAILED", self.timeout_seconds)
        if self._random.random() < self.failure_rate:
            return ProviderEvent("FAILED", self.timeout_seconds)
        if self._random.random() < self.answer_probability:
            return ProviderEvent("ANSWERED", self.ringing_delay_seconds + self.duration_seconds)
        return ProviderEvent("NO_ANSWER", self.ringing_delay_seconds)


def default_providers(seed: int = 42) -> tuple[MockProvider, MockProvider]:
    return (
        MockProvider("MockNorth", 0.35, 4.0, 75.0, 0.03, 60, 12, seed=seed),
        MockProvider("MockSouth", 0.52, 6.0, 95.0, 0.08, 40, 8, seed=seed + 1),
    )
