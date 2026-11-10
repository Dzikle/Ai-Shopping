"""FastAPI application factory - replaces AiShoppingApplication.java.

Default response class renders Decimals/d datetimes the same way Jackson did for
the Java service; Spring-shaped error bodies keep container parity for 404/500.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.jsonx import RestJSONResponse, spring_error_body
from app.routes.baskets import make_baskets_router
from app.routes.catalog import make_catalog_router
from app.mcp.routes import make_mcp_router
from app.mcp.tool_registry import McpToolRegistry


def create_app(settings=None, catalog_service=None, basket_service=None, assistant_provider=None) -> FastAPI:
    if catalog_service is None and basket_service is None:
        catalog_service, basket_service = _build_default_stack(settings)
    elif catalog_service is None or basket_service is None:
        from app.services.catalog_search_service import CatalogSearchService
        from app.services.basket_optimizer_service import BasketOptimizerService

        catalog_service = catalog_service or CatalogSearchService.__new__(CatalogSearchService)
        basket_service = basket_service or BasketOptimizerService.__new__(BasketOptimizerService)

    registry = McpToolRegistry(catalog_service, basket_service)

    app = FastAPI(default_response_class=RestJSONResponse)
    app.include_router(make_catalog_router(catalog_service))
    app.include_router(make_baskets_router(basket_service))
    app.include_router(make_mcp_router(registry))
    app.include_router(make_assistant_router(registry, settings, assistant_provider))

    _install_error_handlers(app)
    return app


def make_assistant_router(registry, settings, assistant_provider=None):
    """Builds the M13 assistant route. Uses the injected provider when given
    (tests), otherwise resolves the provider from server-side config only."""
    from app.assistant.coordinator import AssistantCoordinator
    from app.assistant.providers import build_provider
    from app.routes.assistant import make_assistant_router as make_route

    s = settings
    if s is None:
        from app.config import load_settings

        s = load_settings()
    provider = assistant_provider if assistant_provider is not None else build_provider(s)
    return make_route(AssistantCoordinator(registry, provider), s)


def _build_default_stack(settings):
    from app.config import load_settings

    s = settings or load_settings()
    from app.db import Database
    from app.repositories.catalog_repository import PostgresCatalogRepository
    from app.repositories.basket_repository import BasketRepository
    from app.services.opensearch_client import OpenSearchClient
    from app.services.catalog_search_service import CatalogSearchService
    from app.services.basket_optimizer_service import BasketOptimizerService

    database = Database(
        host=s.postgres_host,
        port=s.postgres_port,
        dbname=s.postgres_db,
        user=s.postgres_user,
        password=s.postgres_password,
    )
    os_client = OpenSearchClient(s.opensearch_url)
    pg_repository = PostgresCatalogRepository(database)
    basket_repository = BasketRepository(database)
    catalog_service = CatalogSearchService(os_client, pg_repository)
    basket_service = BasketOptimizerService(basket_repository)
    return catalog_service, basket_service


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content=_spring_error_body(400, "Bad Request", request.url.path),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        texts = {404: "Not Found", 405: "Method Not Allowed", 500: "Internal Server Error"}
        text = texts.get(exc.status_code, str(exc.detail) if exc.detail else "Error")
        return JSONResponse(
            status_code=exc.status_code,
            content=_spring_error_body(exc.status_code, text, request.url.path),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        import traceback

        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content=_spring_error_body(500, "Internal Server Error", request.url.path),
        )


def _spring_error_body(status: int, error: str, path: str) -> dict[str, Any]:
    return spring_error_body(status, error, path)
