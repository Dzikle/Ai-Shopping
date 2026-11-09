"""JSON value conversion and response serialization shared by all controllers.

Mirrors the Java baseline (Jackson + JavaTimeModule, WRITE_DATES_AS_TIMESTAMPS
disabled): timestamps serialize as ISO-8601 instants with a Z suffix, decimals
as JSON numbers, DTO record components stay camelCase and keep explicit nulls.
"""

import datetime as dt
import json
from decimal import Decimal

from fastapi.responses import JSONResponse


def iso_instant(value):
    """Serialize a datetime to the Java `Instant` JSON shape (e.g. 2026-04-17T10:00:00Z)."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        iso = value.isoformat()
        return iso[:-6] + "Z" if iso.endswith("+00:00") else iso
    raise TypeError(f"not a datetime: {value!r}")


def iso_date(value):
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value.isoformat()
    raise TypeError(f"not a date: {value!r}")


def dec(value):
    """Decimal -> float (JSON number, matching Jackson's numeric BigDecimal output)."""
    if value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"not a decimal: {value!r}")


class RestJSONResponse(JSONResponse):
    """JSONResponse accepting Decimal/datetime inside the payload tree."""

    def render(self, content) -> bytes:
        if content is None:
            return b""
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            default=self._default,
        ).encode("utf-8")

    @staticmethod
    def _default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dt.datetime):
            return iso_instant(obj)
        if isinstance(obj, dt.date):
            return iso_date(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def spring_error_body(status: int, error: str, path: str) -> dict:
    """Spring Boot 3 DefaultErrorAttributes JSON body shape (timestamp, status, error, path)."""
    return {
        "timestamp": iso_instant(dt.datetime.now(dt.UTC)),
        "status": status,
        "error": error,
        "path": path,
    }
