import time
from enum import StrEnum

from app.monitoring.metrics import set_circuit_breaker_state


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# Numeric value exported in the llm_circuit_breaker_state gauge.
STATE_GAUGE_VALUES = {CircuitState.CLOSED: 0, CircuitState.HALF_OPEN: 1, CircuitState.OPEN: 2}


class CircuitBreakerOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """Circuit breaker for external LLM provider calls."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
        name: str = "llm",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()
        self._export_state()

    def _export_state(self) -> None:
        set_circuit_breaker_state(self.name, STATE_GAUGE_VALUES[self.state])

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            now = time.time()
            if now - self.last_state_change >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                self._export_state()
                return True
            return False

        # HALF_OPEN: allow a trial request
        return True

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_state_change = time.time()
        self._export_state()

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()
            self._export_state()


# Global default circuit breaker instance
default_circuit_breaker = CircuitBreaker()
