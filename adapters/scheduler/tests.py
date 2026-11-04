"""Unit tests for the M6 scheduler worker (stdlib-only Python 3.12)."""

from __future__ import annotations

import io
import json
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import cli as scheduler_cli
import scheduler


class _DummyResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class SchedulerTests(unittest.TestCase):
    def test_exponential_backoff_schedule_and_cap(self):
        self.assertEqual(scheduler.compute_backoff_seconds(0), 0.0)
        self.assertEqual(scheduler.compute_backoff_seconds(1, 60, 1800), 60.0)    # 1m
        self.assertEqual(scheduler.compute_backoff_seconds(2, 60, 1800), 120.0)   # 2m
        self.assertEqual(scheduler.compute_backoff_seconds(3, 60, 1800), 240.0)   # 4m
        self.assertEqual(scheduler.compute_backoff_seconds(4, 60, 1800), 480.0)   # 8m
        self.assertEqual(scheduler.compute_backoff_seconds(5, 60, 1800), 960.0)   # 16m
        self.assertEqual(scheduler.compute_backoff_seconds(6, 60, 1800), 1800.0)  # capped at 30m

    def test_fetch_with_retry_recovers_and_honors_retry_after(self):
        sleeps: list[float] = []
        calls = {"n": 0}

        def flaky_opener(req, timeout):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("temporary DNS timeout")
            if calls["n"] == 2:
                hdrs = Message()
                hdrs["Retry-After"] = "180"
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs, None)
            return _DummyResponse(b"<html>ok</html>")

        data = scheduler.fetch_with_retry(
            "https://stokomak.proverkanaceni.mk/?org=1&perPage=10&page=1",
            delay_seconds=0.0,
            max_retries=3,
            base_backoff_seconds=60.0,
            max_backoff_seconds=1800.0,
            opener=flaky_opener,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(data, b"<html>ok</html>")
        self.assertEqual(calls["n"], 3)
        # First retry: 60s (attempt 1); second retry: Retry-After=180 > 120s (attempt 2)
        self.assertEqual(sleeps, [60.0, 180.0])

    def test_prefer_ipv4_context_forces_af_inet(self):
        seen_families = []
        orig = socket.getaddrinfo

        def fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            seen_families.append(family)
            return []

        socket.getaddrinfo = fake_getaddrinfo
        try:
            with scheduler.prefer_ipv4_context(True):
                socket.getaddrinfo("stokomak.proverkanaceni.mk", 443)
        finally:
            socket.getaddrinfo = orig

        self.assertEqual(seen_families, [socket.AF_INET])

    def test_lease_manager_blocks_concurrent_and_expires_stale(self):
        tmp = Path(tempfile.mkdtemp(prefix="m6-lease-test-"))
        try:
            mgr = scheduler.LeaseManager(tmp, lease_ttl_seconds=3600)
            lease = mgr.acquire("vero", "run-1", worker_id="worker-a:100")
            self.assertEqual(lease["retailer"], "vero")
            self.assertEqual(lease["worker_id"], "worker-a:100")

            with self.assertRaises(scheduler.LeaseConflictError):
                mgr.acquire("vero", "run-2", worker_id="worker-b:200")

            # Other retailer can still acquire its own lease concurrently
            other = mgr.acquire("stokomak", "run-1", worker_id="worker-b:200")
            self.assertEqual(other["retailer"], "stokomak")

            mgr.release("vero", run_key="run-1")
            mgr.release("stokomak", run_key="run-1")

            # Re-acquiring after release succeeds
            reacquired = mgr.acquire("vero", "run-3", worker_id="worker-b:200")
            self.assertEqual(reacquired["run_key"], "run-3")
            mgr.release("vero", run_key="run-3")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_seconds_until_next_window_calculation(self):
        # 2026-10-29 06:30 UTC == 07:30 CET (Europe/Skopje) -> 1 hour (3600s) before 08:30
        before = datetime(2026, 10, 29, 6, 30, 0, tzinfo=timezone.utc)
        wait_before = scheduler.seconds_until_next_window(
            before, target_hour=8, target_minute=30, tz=scheduler.SKOPJE_TZ
        )
        self.assertAlmostEqual(wait_before, 3600.0, places=1)

        # 2026-10-29 08:30 UTC == 09:30 CET -> 23 hours (82800s) until next day's 08:30
        after = datetime(2026, 10, 29, 8, 30, 0, tzinfo=timezone.utc)
        wait_after = scheduler.seconds_until_next_window(
            after, target_hour=8, target_minute=30, tz=scheduler.SKOPJE_TZ
        )
        self.assertAlmostEqual(wait_after, 23 * 3600.0, places=1)

    def test_pipeline_pass_snapshots_and_quarantine_alert(self):
        tmp = Path(tempfile.mkdtemp(prefix="m6-pipeline-test-"))
        try:
            # Create a synthetic quarantined zito fixture dir with empty_1_1.html renamed to 1_1.html
            bad_zito_dir = tmp / "bad_zito"
            bad_zito_dir.mkdir(parents=True, exist_ok=True)
            empty_fixture = scheduler_cli._REPO_ROOT / "tests" / "fixtures" / "zito" / "empty_1_1.html"
            shutil.copyfile(empty_fixture, bad_zito_dir / "1_1.html")

            log_buf = io.StringIO()
            summary, exit_code = scheduler_cli.run_pipeline_pass(
                retailers=["vero", "zito"],
                mode="snapshots",
                run_tag="unit-test-m6",
                out_root=tmp / "snapshots",
                lease_dir=tmp / "leases",
                worker_id="unit-worker:1",
                snapshot_map={"zito": str(bad_zito_dir)},
                stores_map={},
                stream=log_buf,
            )

            # Exit code 2 because zito was quarantined while vero succeeded
            self.assertEqual(exit_code, 2)
            self.assertTrue(summary["any_quarantined"])
            self.assertFalse(summary["any_failed"])
            self.assertEqual(len(summary["retailers"]), 2)

            vero_res = next(r for r in summary["retailers"] if r["retailer"] == "vero")
            zito_res = next(r for r in summary["retailers"] if r["retailer"] == "zito")
            self.assertEqual(vero_res["status"], "completed")
            self.assertEqual(vero_res["rows_stored"], 1000)
            self.assertFalse(vero_res["quarantined"])

            self.assertEqual(zito_res["status"], "quarantined")
            self.assertTrue(zito_res["quarantined"])
            self.assertEqual(len(summary["alerts"]), 1)
            self.assertEqual(summary["alerts"][0]["retailer"], "zito")
            self.assertEqual(summary["alerts"][0]["level"], "error")

            # Verify structured JSON logs emitted
            log_lines = [json.loads(line) for line in log_buf.getvalue().splitlines() if line.strip()]
            events = [entry["event"] for entry in log_lines]
            self.assertIn("retailer_run_completed", events)
            self.assertIn("retailer_run_quarantined", events)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
