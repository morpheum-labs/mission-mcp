from __future__ import annotations

from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastmcp.utilities.lifespan import combine_lifespans
from prometheus_client import make_asgi_app

from omnimission.api.schemas import HealthResponse
from omnimission.chroma_store import ChromaStore
from omnimission.config import get_settings
from omnimission.embeddings import embed_query
from omnimission.mcp_server import build_mcp
from omnimission.monitoring import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    route_group,
)
from omnimission.planner.service import MissionPlanner
from omnimission.x402_ask import build_x402_mcp_middleware

API_DESCRIPTION = """
**OmniMission** exposes a REST surface for health checks and mounts a **FastMCP** server for agents.

- **OpenAPI** (this spec): `/openapi.json`, interactive docs: `/docs`, ReDoc: `/redoc`
- **MCP (HTTP)**: mounted at `/mcp` — use an MCP client with streamable HTTP/SSE against that path. Primary tool: `plan_mission` (natural-language mission → ranked skills, scores, x402 preview, install hints).
- **Prometheus**: `GET /metrics` — scrape for HTTP, `plan_mission`, and Chroma query counters (and crawler when that process runs).
- **x402 ask (optional)**: set `OMNIMISSION_X402_ASK_ENABLED=true` to require [x402](https://www.x402.org/) payment (HTTP 402) on `/mcp` before MCP access; configure facilitator URL, network, `pay_to`, and price via env.

The MCP protocol is defined by the [Model Context Protocol](https://modelcontextprotocol.io/); this document describes the FastAPI routes only (the MCP sub-app is documented below as an extension path).
"""

OPENAPI_TAGS = [
    {
        "name": "meta",
        "description": "Service metadata and discovery.",
    },
    {
        "name": "health",
        "description": "Liveness and readiness probes.",
    },
    {
        "name": "mcp",
        "description": "Model Context Protocol over HTTP (mounted ASGI app). Not every sub-route is listed here; use an MCP client to negotiate the session.",
    },
]


def create_app() -> FastAPI:
    settings = get_settings()
    store = ChromaStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.collection_name,
    )
    planner = MissionPlanner(settings, store)
    mcp = build_mcp(planner)
    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def warmup_lifespan(app: FastAPI):
        embed_query(settings.embed_model, "warmup: omnimission")
        yield

    app = FastAPI(
        title="OmniMission API",
        version="0.1.0",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=combine_lifespans(warmup_lifespan, mcp_app.lifespan),
    )

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version="3.1.0",
            description=app.description,
            routes=app.routes,
            tags=OPENAPI_TAGS,
        )
        openapi_schema.setdefault("paths", {})
        openapi_schema["paths"]["/mcp"] = {
            "get": {
                "tags": ["mcp"],
                "summary": "MCP HTTP transport (session)",
                "description": (
                    "Entry for the FastMCP ASGI app (`http_app`). "
                    "Clients use MCP streamable HTTP / SSE semantics on this path and its sub-routes. "
                    "Tool: **plan_mission** — pass a mission string; response includes ranked skills and x402 preview."
                ),
                "operationId": "mcp_session",
                "responses": {
                    "200": {
                        "description": "MCP protocol response (SSE or JSON-RPC per client negotiation).",
                    },
                    "405": {
                        "description": "Some methods may return 405 depending on client and sub-path.",
                    },
                },
            }
        }
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    x402_mw = build_x402_mcp_middleware(settings)
    if x402_mw is not None:
        app.middleware("http")(x402_mw)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

    @app.middleware("http")
    async def prometheus_http_metrics(request: Request, call_next):
        path = request.url.path
        if path.startswith("/metrics"):
            return await call_next(request)
        method = request.method
        rg = route_group(path)
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        HTTP_REQUESTS_TOTAL.labels(method=method, route_group=rg).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(route_group=rg).observe(elapsed)
        return response

    @app.get(
        "/",
        tags=["meta"],
        summary="API root",
        operation_id="root",
    )
    def root() -> dict:
        return {
            "service": "omnimission-api",
            "version": "0.1.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "mcp": "/mcp",
            "metrics": "/metrics",
            "x402_ask_enabled": settings.x402_ask_enabled,
        }

    @app.get(
        "/health",
        tags=["health"],
        summary="Health check",
        operation_id="health",
        response_model=HealthResponse,
    )
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="omnimission-api")

    app.mount("/mcp", mcp_app)
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "omnimission.api.main:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    run()
