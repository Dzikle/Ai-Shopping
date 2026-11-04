"""Core M6 scheduler worker primitives (stdlib-only Python 3.12).

Responsibilities:
- Worker lease management (prevents concurrent runs for the same retailer).
- Exponential backoff (1m, 2m, 4m, 8m, capped at 30m) + Retry-After support.
- IPv4 preference context for hosts with unreliable IPv6 (*.proverkanaceni.mk).
- Daily schedule calculation aligned to 08:30 Europe/Skopje publication window.
- Structured JSON logging and alert payload construction.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        SKOPJE_TZ: tzinfo = ZoneInfo("Europe/Skopje")
        TZ_SOURCE = "zoneinfo:Europe/Skopje"
    except ZoneInfoNotFoundError:
        SKOPJE_TZ = timezone(timedelta(hours=1), name="CET")
        TZ_SOURCE = "fixed:+01:00"
except ImportError:
    SKOPJE_TZ = timezone(timedelta(hours=1), name="CET")
    TZ_SOURCE = "fixed:+01:00"

DEFAULT_RETAILERS = ("vero", "stokomak", "zito")

DEFAULT_FIXTURE_DIRS = {
    "vero": "tests/fixtures/vero",
    "stokomak": "tests/fixtures/stokomak",
    "zito": "tests/fixtures/zito",
}

DEFAULT_LIVE_URLS = {
    "vero": "https://pricelist.vero.com.mk",
    "stokomak": "https://stokomak.proverkanaceni.mk",
    "zito": "https://zito.proverkanaceni.mk",
}

DEFAULT_LIVE_SMOKE_STORES = {
    "vero": ["89"],
    "stokomak": ["1"],
    "zito": ["2"],
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dt_utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def default_worker_id() -> str:
    host = socket.gethostname() or "localhost"
    return f"{host}:{os.getpid()}"


def emit_json_log(
    level: str,
    event: str,
    *,
    retailer: str | None = None,
    store: str | None = None,
    page: int | None = None,
    run_key: str | None = None,
    worker_id: str | None = None,
    duration_ms: int | None = None,
    status: str | None = None,
    stream=None,
    **extra: Any,
) -> dict[str, Any]:
    """Emit a single-line structured JSON log event to stdout (or custom stream)."""
    record: dict[str, Any] = {
        "timestamp": dt_utc_iso(now_utc()),
        "level": level,
        "event": event,
    }
    if retailer is not None:
        record["retailer"] = retailer
    if store is not None:
        record["store"] = str(store)
    if page is not None:
        record["page"] = page
    if run_key is not None:
        record["run_key"] = run_key
    if worker_id is not None:
        record["worker_id"] = worker_id
    if duration_ms is not None:
        record["duration_ms"] = duration_ms
    if status is not None:
        record["status"] = status
    for k, v in extra.items():
        if v is not None:
            record[k] = v

    target = stream if stream is not None else sys.stdout
    target.write(json.dumps(record, ensure_ascii=False) + "\n")
    target.flush()
    return record


def build_alert_payload(
    *,
    level: str,
    retailer: str,
    store: str,
    message: str,
    run_key: str,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    """Construct the canonical M6 alert payload."""
    ts = timestamp or now_utc()
    return {
        "timestamp": dt_utc_iso(ts),
        "level": level,
        "retailer": retailer,
        "store": str(store),
        "message": message,
        "runKey": run_key,
    }


def compute_backoff_seconds(
    attempt: int,
    base_seconds: float = 60.0,
    max_seconds: float = 1800.0,
) -> float:
    """Exponential backoff: 1m, 2m, 4m, 8m, ..., capped at 30m (1800s).

    attempt is 1-based (1 -> 1*base, 2 -> 2*base, 3 -> 4*base, 4 -> 8*base).
    """
    if attempt <= 0:
        return 0.0
    delay = float(base_seconds) * (2 ** (attempt - 1))
    return min(delay, float(max_seconds))


@contextlib.contextmanager
def prefer_ipv4_context(enabled: bool = True):
    """Force socket.getaddrinfo to resolve AF_INET (IPv4) when enabled.

    Mitigates slow/unreachable IPv6 on *.proverkanaceni.mk.
    """
    if not enabled:
        yield
        return
    orig_getaddrinfo = socket.getaddrinfo

    def ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        res = orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        return res

    socket.getaddrinfo = ipv4_only_getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = orig_getaddrinfo


def fetch_with_retry(
    url: str,
    *,
    delay_seconds: float = 1.0,
    state: dict[str, Any] | None = None,
    max_retries: int = 3,
    base_backoff_seconds: float = 60.0,
    max_backoff_seconds: float = 1800.0,
    timeout_seconds: float = 60.0,
    force_ipv4: bool = False,
    user_agent: str = "AiShopping-M6-scheduler/0.1 (+contact: owner)",
    opener: Callable[[urllib.request.Request, float], Any] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bytes:
    """Polite HTTP fetch with inter-request rate limit, Retry-After, and exponential backoff."""
    if state is None:
        state = {}
    min_interval = float(state.get("min_interval", delay_seconds))
    last_ts = state.get("last_request_ts")
    if last_ts is not None and min_interval > 0:
        elapsed = time.monotonic() - last_ts
        if elapsed < min_interval:
            sleep_fn(min_interval - elapsed)

    open_fn = opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
    attempt = 0

    while True:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with prefer_ipv4_context(force_ipv4):
                resp = open_fn(req, timeout_seconds)
                with resp:
                    data = resp.read()
            state["last_request_ts"] = time.monotonic()
            return data
        except urllib.error.HTTPError as exc:
            state["last_request_ts"] = time.monotonic()
            if attempt >= max_retries or exc.code not in (408, 429, 500, 502, 503, 504):
                raise
            attempt += 1
            retry_after_hdr = exc.headers.get("Retry-After") if exc.headers else None
            wait_sec = compute_backoff_seconds(
                attempt, base_seconds=base_backoff_seconds, max_seconds=max_backoff_seconds
            )
            if retry_after_hdr:
                try:
                    wait_sec = min(max(float(retry_after_hdr), wait_sec), max_backoff_seconds)
                except ValueError:
                    pass
            sleep_fn(wait_sec)
        except (urllib.error.URLError, TimeoutError, OSError):
            state["last_request_ts"] = time.monotonic()
            if attempt >= max_retries:
                raise
            attempt += 1
            wait_sec = compute_backoff_seconds(
                attempt, base_seconds=base_backoff_seconds, max_seconds=max_backoff_seconds
            )
            sleep_fn(wait_sec)


class LeaseConflictError(RuntimeError):
    """Raised when another worker already holds an active lease for the retailer."""


class LeaseManager:
    """Atomic file-based and SQL-compatible lease manager per retailer source_slug."""

    def __init__(self, lease_dir: str | Path, lease_ttl_seconds: int = 7200):
        self.lease_dir = Path(lease_dir)
        self.lease_ttl_seconds = lease_ttl_seconds
        self.lease_dir.mkdir(parents=True, exist_ok=True)

    def _lease_path(self, retailer: str) -> Path:
        safe = "".join(ch for ch in retailer.lower() if ch.isalnum() or ch in ("_", "-"))
        return self.lease_dir / f"{safe}.lease.json"

    def acquire(self, retailer: str, run_key: str, worker_id: str | None = None) -> dict[str, Any]:
        worker = worker_id or default_worker_id()
        path = self._lease_path(retailer)
        now = now_utc()

        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                started = datetime.fromisoformat(existing["started_at"])
                age = (now - started).total_seconds()
                if age < self.lease_ttl_seconds:
                    raise LeaseConflictError(
                        f"active lease held for retailer={retailer} by worker={existing.get('worker_id')} "
                        f"run_key={existing.get('run_key')} (age={int(age)}s)"
                    )
                # Expired lease: remove stale lockfile before re-acquiring
                path.unlink(missing_ok=True)
            except LeaseConflictError:
                raise
            except Exception:
                path.unlink(missing_ok=True)

        payload = {
            "retailer": retailer,
            "run_key": run_key,
            "worker_id": worker,
            "status": "running",
            "started_at": dt_utc_iso(now),
        }
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            raise LeaseConflictError(f"concurrent lease acquisition for retailer={retailer}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return payload

    def release(self, retailer: str, run_key: str | None = None) -> None:
        path = self._lease_path(retailer)
        if not path.exists():
            return
        if run_key is not None:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if existing.get("run_key") != run_key:
                    return
            except Exception:
                pass
        path.unlink(missing_ok=True)

    @contextlib.contextmanager
    def lease(self, retailer: str, run_key: str, worker_id: str | None = None):
        info = self.acquire(retailer, run_key, worker_id=worker_id)
        try:
            yield info
        finally:
            self.release(retailer, run_key=run_key)


def seconds_until_next_window(
    now: datetime | None = None,
    *,
    target_hour: int = 8,
    target_minute: int = 30,
    tz: tzinfo = SKOPJE_TZ,
) -> float:
    """Return seconds from `now` until the next daily HH:MM target window in `tz`."""
    current = (now or now_utc()).astimezone(tz)
    candidate = current.replace(
        hour=target_hour, minute=target_minute, second=0, microsecond=0
    )
    if candidate <= current:
        candidate = candidate + timedelta(days=1)
    return max(0.0, (candidate - current).total_seconds())
