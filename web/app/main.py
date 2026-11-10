"""AI Shopping public web prototype (M14) — server-rendered FastAPI + Jinja2.

Standalone HTML-first frontend over the existing FastAPI REST API
(ADR-0007). The browser only ever talks to this app; the API stays on its
private address. No trackers, no third-party scripts, no client-side money
math: all totals come from `POST /api/v1/baskets/optimize`.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import ApiClient
from .cache import TtlCache
from .formatting import (
    format_date,
    format_datetime,
    format_mkd,
    format_number,
    format_price_range,
    format_quantity,
    mk_noun,
    unit_price_for_offer,
)
from . import routes

_APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = _APP_DIR / "templates"
STATIC_DIR = _APP_DIR / "static"

DEFAULT_API_BASE_URL = "http://127.0.0.1:18089"
DEFAULT_WEB_BASE_URL = "http://localhost:8090"
MAX_OPTIMIZE_BODY_BYTES = 65536


def create_app(
    api_base_url: str | None = None,
    web_base_url: str | None = None,
    api_timeout: float | None = None,
    transport=None,
) -> FastAPI:
    api_base_url = api_base_url or os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL)
    web_base_url = (
        web_base_url or os.environ.get("WEB_BASE_URL", DEFAULT_WEB_BASE_URL)
    ).rstrip("/")
    if api_timeout is None:
        api_timeout = float(os.environ.get("API_TIMEOUT_SECONDS", "8"))

    api = ApiClient(api_base_url, timeout=api_timeout, transport=transport)
    freshness_cache = TtlCache(ttl_seconds=60.0)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        api.close()

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["mkd"] = format_mkd
    templates.env.filters["mknum"] = format_number
    templates.env.filters["mkqty"] = format_quantity
    templates.env.filters["mkdate"] = format_date
    templates.env.filters["mkdatetime"] = format_datetime
    templates.env.filters["mkrange"] = format_price_range
    templates.env.filters["mknoun"] = mk_noun
    templates.env.filters["unit_price"] = unit_price_for_offer

    app.state.api = api
    app.state.cache = freshness_cache
    app.state.templates = templates
    app.state.web_base_url = web_base_url

    routes.register(app)

    @app.middleware("http")
    async def harden_response(request: Request, call_next):
        if request.method == "POST" and request.url.path == "/basket/optimize":
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_OPTIMIZE_BODY_BYTES:
                return JSONResponse(status_code=413, content={"error": "payload_too_large"})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app
