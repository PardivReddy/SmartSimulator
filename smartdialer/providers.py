"""Seeded, local-only mock providers."""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderEvent:
    kind: str
    delay_seconds: float


@dataclass(frozen=True)
class ProviderRetryPolicy:
    max_retries: int = 2
    initial_backoff_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries must be zero or greater")
        if self.initial_backoff_seconds <= 0:
            raise ValueError("initial_backoff_seconds must be positive")

    def backoff_seconds(self, retry_number: int) -> float:
        if not 1 <= retry_number <= self.max_retries:
            raise ValueError("retry_number must be within the configured retry limit")
        return self.initial_backoff_seconds * (2 ** (retry_number - 1))


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
        self._lock = threading.RLock()

    def simulate(self) -> ProviderEvent:
        with self._lock:
            if not self.available:
                return ProviderEvent("FAILED", self.timeout_seconds)
            if self._random.random() < self.failure_rate:
                return ProviderEvent("FAILED", self.timeout_seconds)
            if self._random.random() < self.answer_probability:
                return ProviderEvent("ANSWERED", self.ringing_delay_seconds + self.duration_seconds)
            return ProviderEvent("NO_ANSWER", self.ringing_delay_seconds)

    @property
    def is_available(self) -> bool:
        with self._lock:
            return self.available

    def set_available(self, available: bool) -> None:
        with self._lock:
            self.available = available


def default_providers(seed: int = 42) -> tuple[MockProvider, MockProvider]:
    return (
        MockProvider("MockNorth", 0.35, 4.0, 75.0, 0.03, 60, 12, seed=seed),
        MockProvider("MockSouth", 0.52, 6.0, 95.0, 0.08, 40, 8, seed=seed + 1),
    )
