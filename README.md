# OmniMission MCP

## Introduction

**OmniMission** is a mission-planning service for agents: you describe a goal in natural language, and it searches a **vector index** of skills and MCP-related content, then returns **ranked matches** with relevance scores, optional **x402** pricing preview, and install hints. It combines **Chroma** for retrieval, **LangGraph** for a small planning graph, and **FastMCP** so clients can talk to the planner over **MCP over HTTP** from a FastAPI app.

Typical flow: a crawler ingests documents into Chroma; the API exposes health and OpenAPI; the MCP surface (e.g. `plan_mission`) runs on `/mcp` and uses embeddings to query that index.

### Calling `plan_mission` (MCP)

The MCP app is mounted at **`/mcp`** (streamable HTTP / SSE, per the [Model Context Protocol](https://modelcontextprotocol.io/)). Use any MCP client that supports HTTP transport and point it at:

`http://localhost:8080/mcp` (or your deployed host).

Register the tool **`plan_mission`** with a single string argument **`mission`** (natural-language goal). The response is JSON with ranked skills, scores, and optional x402 preview.

**Smoke checks (REST):**

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/ | jq .
```

MCP sessions are negotiated by the client (not a single static `curl` one-liner). For local debugging, use an MCP-aware IDE or the official MCP Inspector once configured for your base URL.

## Requirements

- Python **3.12+**
- **Chroma** (included in Docker Compose as `chroma-db`)

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run Chroma (or point config at an existing instance), then:

```bash
uvicorn omnimission.api.main:app --reload --host 0.0.0.0 --port 8080
```

- API docs: `http://localhost:8080/docs`
- MCP (HTTP): `http://localhost:8080/mcp`

Crawler (scheduled ingest) in another terminal:

```bash
python -m omnimission.crawler.worker
```

## Docker Compose

From the repo root:

```bash
docker compose up --build
```

Services:

- **chroma-db** — Chroma on port `8000`
- **api-service** — FastAPI + MCP on port `8080`
- **crawler-service** — periodic crawl/ingest into Chroma

## Configuration

Settings live in `src/omnimission/config.py`. **Precedence** (highest first): arguments passed to `Settings(...)`, then **environment variables** (`OMNIMISSION_*`), then **`.env`**, then optional **`conf.toml`**, then **field defaults** in code.

Copy `conf.toml.example` to `conf.toml` to override defaults without exporting env vars. In TOML, keys use **Python field names** (e.g. `chroma_host`), not the `OMNIMISSION_` prefix.

Useful variables include `OMNIMISSION_CHROMA_HOST`, `OMNIMISSION_CHROMA_PORT`, `OMNIMISSION_EMBED_MODEL`, `OMNIMISSION_CRAWLER_SEED_URLS`, and optional **x402** settings (`OMNIMISSION_X402_ASK_ENABLED`, `OMNIMISSION_X402_PAY_TO`, …) for pay-per-use gating on `/mcp`.

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Includes ingest validation, **`MissionPlanner`** with mocked `embed_query` and **`ChromaStore.query`**, and pure **`_rank_and_dedupe`** behavior.

## CLI entry points

| Command | Purpose |
|--------|---------|
| `omnimission-api` | Run the API (same as uvicorn target in `omnimission.api.main`) |
| `omnimission-crawler` | Run the crawler worker |
| `omnimission-export-openapi` | Export OpenAPI JSON |

## Repository layout

- `src/omnimission/` — application package (API, MCP, planner, crawler, Chroma store, config)
- `docker/` — container build
- `openapi/` — exported OpenAPI snapshot (if present)

