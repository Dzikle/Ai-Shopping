"""In-process bounded unauthenticated request controls for the assistant (M13).

Bounded controls requested by the task doc: per-client rate limiting, a global
concurrency cap and hard payload bounds (payload bounds live in the Pydantic
schemas). The limiter is per-process memory only - acceptable for the current
single-process FastAPI deployment; a production multi-worker deployment would
need a shared store, which is explicitly out of this milestone's scope.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi.responses import JSONResponse

from app.jsonx import spring_error_body


class RateLimiter:
    """Per-client sliding window limiter, thread-safe."""

    def __init__(self, max_requests: int, window_seconds: int):
        self._max_requests = max(1, max_requests)
        self._window = max(1, window_seconds)
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_key: str, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        with self._lock:
            history = self._hits[client_key]
            cutoff = current - self._window
            while history and history[0] < cutoff:
                history.popleft()
            if len(history) >= self._max_requests:
                return False
            history.append(current)
            # opportunistically keep memory bounded
            if len(self._hits) > 10000:
                for key in list(self._hits.keys()):
                    if not self._hits[key]:
                        self._hits.pop(key, None)
            return True


class ConcurrencyGate:
    """Global cap of concurrently executing assistant turns."""

    def __init__(self, limit: int):
        self._semaphore = threading.Semaphore(max(1, limit))

    def acquire(self) -> bool:
        return self._semaphore.acquire(blocking=False)

    def release(self) -> None:
        self._semaphore.release()


def rate_limit_response(limit_requests: int, path: str) -> JSONResponse:
    body = spring_error_body(429, "Too Many Requests", path)
    return JSONResponse(
        status_code=429,
        content=body,
        headers={"Retry-After": "60"},
    )
