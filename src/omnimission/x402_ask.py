"""Optional x402 pay-per-use (HTTP 402 \"ask\") on MCP routes via FastAPI middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import Response

from omnimission.config import Settings


def build_x402_mcp_middleware(settings: Settings):
    """Return an ASGI middleware function for x402-gated `/mcp`, or ``None`` if disabled."""
    if not settings.x402_ask_enabled:
        return None

    from x402 import x402ResourceServer
    from x402.http import FacilitatorConfig, HTTPFacilitatorClient
    from x402.http.middleware.fastapi import payment_middleware
    from x402.mechanisms.evm.exact.register import register_exact_evm_server

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(url=settings.x402_facilitator_url),
    )
    server = x402ResourceServer(facilitator)
    register_exact_evm_server(server, networks=[settings.x402_network])

    route: dict = {
        "accepts": {
            "scheme": "exact",
            "payTo": settings.x402_pay_to,
            "price": settings.x402_price,
            "network": settings.x402_network,
        },
        "description": settings.x402_resource_description,
    }

    routes = {
        "* /mcp": route,
        "* /mcp/*": route,
    }

    inner = payment_middleware(
        routes,
        server,
        paywall_config=None,
        paywall_provider=None,
    )

    async def x402_layer(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)
        return await inner(request, call_next)

    return x402_layer
