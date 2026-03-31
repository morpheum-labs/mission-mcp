"""Prometheus metrics (omnimission_*)."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# plan_mission MCP tool
PLAN_MISSION_DURATION_SECONDS = Histogram(
    "omnimission_plan_mission_duration_seconds",
    "Wall time spent inside the plan_mission tool handler",
    ["status"],
)
PLAN_MISSION_TOTAL = Counter(
    "omnimission_plan_mission_total",
    "plan_mission invocations by outcome",
    ["status"],
)

# Planner → Chroma
CHROMA_QUERIES_TOTAL = Counter(
    "omnimission_chroma_queries_total",
    "Chroma collection.query calls from the mission planner",
)

# Crawler worker
CRAWLER_RUNS_TOTAL = Counter(
    "omnimission_crawler_runs_total",
    "Completed crawler scheduler job cycles",
)

# FastAPI (excluding /metrics scrape to avoid self-noise)
HTTP_REQUESTS_TOTAL = Counter(
    "omnimission_http_requests_total",
    "HTTP requests",
    ["method", "route_group"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "omnimission_http_request_duration_seconds",
    "HTTP request latency",
    ["route_group"],
)


def route_group(path: str) -> str:
    """Low-cardinality bucket for HTTP metrics."""
    p = path.split("?", 1)[0].rstrip("/") or "/"
    if p == "/":
        return "root"
    if p.startswith("/health"):
        return "health"
    if p.startswith("/mcp"):
        return "mcp"
    if p.startswith("/metrics"):
        return "metrics"
    if p.startswith("/docs") or p.startswith("/redoc") or p.startswith("/openapi"):
        return "docs"
    return "other"


def record_plan_mission(*, duration_seconds: float, status: str) -> None:
    """status: success | validation_error | plan_failed"""
    PLAN_MISSION_DURATION_SECONDS.labels(status=status).observe(duration_seconds)
    PLAN_MISSION_TOTAL.labels(status=status).inc()


def observe_chroma_query() -> None:
    CHROMA_QUERIES_TOTAL.inc()


def record_crawler_run() -> None:
    CRAWLER_RUNS_TOTAL.inc()
