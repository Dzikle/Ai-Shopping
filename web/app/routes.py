"""HTTP routes for the M14 web prototype (all pages server-rendered)."""

import math
from contextlib import contextmanager
from typing import Any

from fastapi import Body, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from .api import ApiClient, ApiError, ApiNotFound
from .cache import TtlCache
from .formatting import format_date, format_datetime
from .transliteration import transliterate_to_cyrillic

PAGE_SIZE = 20
MAX_OPTIMIZE_ITEMS = 50
KNOWN_UNITS = ("pack", "pcs", "g", "kg", "ml", "l")

_FRESHNESS_STATUS_MK = {
    "FRESH": "Свежи податоци",
    "DEGRADED": "Делумно застарени податоци",
    "EMPTY": "Нема податоци",
}

_MISSING_REASONS_MK = {
    "no_offer_at_store": "Нема понуда во оваа продавница",
    "no_offer_in_selected_stores": "Нема понуда во избраните продавници",
    "product_not_found_in_catalog": "Производот не е пронајден во каталогот",
}

_RECOMMENDATION_MK = {
    "split_saves_vs_best_single": "Поделеното пазарење штеди најмалку толку колку што е прагот.",
    "split_not_worth_vs_best_single": "Поделеното пазарење не штеди доволно во однос на најдобрата единствена продавница.",
    "no_stores_cover_requested_items": "Ниедна продавница не покрива ништо од побараните ставки.",
}


def register(app: FastAPI) -> None:
    api: ApiClient = app.state.api
    cache: TtlCache = app.state.cache
    templates: Jinja2Templates = app.state.templates
    web_base_url: str = app.state.web_base_url

    def _freshness() -> dict[str, Any] | None:
        try:
            return cache.get_or_load("freshness", api.get_freshness)
        except ApiError:
            return None

    def _freshness_summary() -> dict[str, Any] | None:
        fresh = _freshness()
        if not fresh:
            return None
        latest = None
        for r in fresh.get("retailers", []):
            ts = r.get("latestPublishedTs")
            if ts and (latest is None or str(ts) > str(latest)):
                latest = ts
        return {
            "status_label": _FRESHNESS_STATUS_MK.get(fresh.get("status") or "", fresh.get("status")),
            "total_offers": fresh.get("totalOffers") or 0,
            "retailer_count": len(fresh.get("retailers", [])),
            "populated_stores": fresh.get("totalPopulatedStores") or 0,
            "latest_published": format_date(latest),
            "checked_at": format_datetime(fresh.get("checkedAt")),
            "retailers": fresh.get("retailers", []),
        }

    def _retailer_slugs() -> list[dict[str, Any]]:
        fresh = _freshness()
        if not fresh:
            return []
        return [
            {"slug": r.get("retailerSlug") or "", "name": r.get("retailerName") or r.get("retailerSlug") or ""}
            for r in fresh.get("retailers", [])
            if r.get("retailerSlug")
        ]

    def _render(request: Request, name: str, context: dict[str, Any], status_code: int = 200) -> Response:
        context.setdefault("web_base_url", web_base_url)
        context.setdefault("nav_path", request.url.path)
        context.setdefault("freshness_summary", None)
        return templates.TemplateResponse(
            request=request, name=name, context=context, status_code=status_code
        )

    # ---- error pages -----------------------------------------------------

    @app.exception_handler(ApiError)
    def api_error_handler(request: Request, exc: ApiError):
        return _render(
            request,
            "error.html",
            {"title": "Услугата е привремено недостапна", "code": 503, "detail": None},
            status_code=503,
        )

    @app.exception_handler(ApiNotFound)
    def api_not_found_handler(request: Request, exc: ApiNotFound):
        return _render(
            request,
            "error.html",
            {"title": "Страницата не е пронајдена", "code": 404, "detail": None},
            status_code=404,
        )

    @app.exception_handler(RequestValidationError)
    def validation_handler(request: Request, exc: RequestValidationError):
        # Bad GET paths (e.g. /compare/abc) get the HTML error page; the JSON
        # optimize relay keeps machine-readable 422 semantics for its client.
        if request.method == "POST":
            return JSONResponse(status_code=422, content={"error": "invalid_payload"})
        return _render(
            request,
            "error.html",
            {"title": "Страницата не е пронајдена", "code": 404, "detail": None},
            status_code=404,
        )

    # ---- home ------------------------------------------------------------

    @app.get("/")
    def home(request: Request):
        return _render(
            request,
            "home.html",
            {
                "title": "AI Пазарење — најдобри цени во Македонија",
                "freshness_summary": _freshness_summary(),
            },
        )

    # ---- search ----------------------------------------------------------

    @app.get("/search")
    def search(
        request: Request,
        q: str = Query(default=""),
        retailer: str = Query(default=""),
        instock: bool = Query(default=False),
        promo: bool = Query(default=False),
        sort: str = Query(default="price_asc"),
        page: int = Query(default=0, ge=0),
    ):
        clean_q = q.strip()
        effective_q = transliterate_to_cyrillic(clean_q) if clean_q else None
        transliterated = bool(clean_q) and effective_q != clean_q
        sort_value = sort if sort in ("price_asc", "price_desc") else "price_asc"

        params: dict[str, Any] = {
            "page": page,
            "size": PAGE_SIZE,
            "sort": sort_value,
            "inStockOnly": instock,
            "promoOnly": promo,
        }
        if effective_q:
            params["q"] = effective_q
        if retailer:
            params["retailer"] = retailer

        result = api.search_offers(params)
        total = int(result.get("total") or 0)
        items = result.get("items") or []
        pages = math.ceil(total / PAGE_SIZE) if total else 0

        return _render(
            request,
            "search.html",
            {
                "title": f"Пребарување: {clean_q} — AI Пазарење" if clean_q else "Пребарување — AI Пазарење",
                "noindex": True,
                "q": clean_q,
                "effective_q": effective_q or "",
                "transliterated": transliterated,
                "retailer": retailer,
                "instock": instock,
                "promo": promo,
                "sort": sort_value,
                "retailer_options": _retailer_slugs(),
                "offers": items,
                "total": total,
                "page": page,
                "pages": pages,
                "freshness_summary": _freshness_summary(),
            },
        )

    # ---- comparisons -----------------------------------------------------

    @app.get("/compare")
    def compare(request: Request, q: str = Query(default=""), page: int = Query(default=0, ge=0)):
        clean_q = q.strip()
        params: dict[str, Any] = {"page": page, "size": PAGE_SIZE, "minRetailers": 2}
        if clean_q:
            params["q"] = transliterate_to_cyrillic(clean_q)

        result = api.compare_products(params)
        total = int(result.get("total") or 0)
        items = result.get("items") or []
        pages = math.ceil(total / PAGE_SIZE) if total else 0

        return _render(
            request,
            "compare.html",
            {
                "title": f"Споредба на цени: {clean_q} — AI Пазарење" if clean_q else "Проверени споредби — AI Пазарење",
                "noindex": page > 0,
                "q": clean_q,
                "groups": items,
                "total": total,
                "page": page,
                "pages": pages,
            },
        )

    @app.get("/compare/{canonical_id}")
    def compare_detail(request: Request, canonical_id: int):
        result = api.compare_products(
            {"canonicalId": canonical_id, "minRetailers": 1, "page": 0, "size": 1}
        )
        items = result.get("items") or []
        if not items:
            raise ApiNotFound("/compare")
        group = items[0]
        group_id = group.get("canonicalProductId")
        if group_id != canonical_id:
            raise ApiNotFound("/compare")
        return _render(
            request,
            "compare_detail.html",
            {
                "title": f"{group.get('canonicalName')} — споредба на цени — AI Пазарење",
                "group": group,
                "missing_reasons": _MISSING_REASONS_MK,
            },
        )

    # ---- basket ----------------------------------------------------------

    @app.get("/basket")
    def basket(request: Request):
        return _render(
            request,
            "basket.html",
            {
                "title": "Кошничка — AI Пазарење",
                "noindex": True,
                "units": KNOWN_UNITS,
                "missing_reasons": _MISSING_REASONS_MK,
                "recommendations": _RECOMMENDATION_MK,
            },
        )

    @app.post("/basket/optimize")
    def basket_optimize(payload: dict[str, Any] = Body(...)):
        items = payload.get("items")
        if not isinstance(items, list):
            return JSONResponse(status_code=400, content={"error": "items_must_be_list"})
        if len(items) > MAX_OPTIMIZE_ITEMS:
            return JSONResponse(status_code=400, content={"error": "too_many_items"})
        status, data = api.optimize_basket(payload)
        if data is None:
            return JSONResponse(status_code=503, content={"error": "api_unreachable"})
        return JSONResponse(status_code=status, content=data)

    # ---- SEO + ops -------------------------------------------------------

    @app.get("/robots.txt", response_class=PlainTextResponse)
    def robots():
        lines = [
            "User-agent: *",
            "Disallow: /basket",
            "Disallow: /api/",
            f"Sitemap: {web_base_url}/sitemap.xml",
            "",
        ]
        return PlainTextResponse("\n".join(lines), media_type="text/plain")

    @app.get("/sitemap.xml", response_class=Response)
    def sitemap():
        urls = [f"{web_base_url}/", f"{web_base_url}/compare"]
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(
                f"  <url><loc>{url}</loc></url>\n" for url in urls
            )
            + "</urlset>\n"
        )
        return Response(content=body, media_type="application/xml")

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    @app.get("/healthz", response_class=JSONResponse)
    def healthz():
        return {"status": "ok"}
