# OmniMission MCP

## Introduction

**OmniMission** is a mission-planning service for agents: you describe a goal in natural language, and it searches a **vector index** of skills and MCP-related content, then returns **ranked matches** with relevance scores, optional **x402** pricing preview, and install hints. It combines **Chroma** for retrieval, **LangGraph** for a small planning graph, and **FastMCP** so clients can talk to the planner over **MCP over HTTP** from a FastAPI app.

Typical flow: a crawler ingests documents into Chroma; the API exposes health and OpenAPI; the MCP surface (e.g. `plan_mission`) runs on `/mcp` and uses embeddings to query that index.

### How this advances harness engineering

Agent harnesses work best when **tooling, retrieval, policy, and observability** are first-class—not afterthoughts around a raw model. OmniMission applies that idea in a **portable, MCP-native** layer:

- **Retrieval-first planning**: goals are embedded and matched against a living Chroma index; results are **scored, deduplicated per publisher**, then **sorted** by combined score and cost—not a static tool manifest.
- **Standard surface**: the planner is a real **`plan_mission` MCP tool** (and `POST /v1/plan`), so any compatible client can depend on a stable contract.
- **Policy and verification**: configurable **keyword / safety guardrails** filter candidates before ranking; a **verify** step checks that returned ids still exist in the index, with counts exposed in the response.
- **Optional mission memory**: pass a **`mission_id`** to append **checkpoints** (history + last plan snapshot) in a dedicated Chroma collection—planning stays decoupled from execution, but long runs can be traced.
- **Economics and ops**: optional **x402** pricing preview on skills, **Prometheus** metrics, Docker Compose, and a **crawler** keep the harness observable and the index fresh.

This complements “internal harness” projects (rich runtime inside one codebase) by **externalizing planning + discovery** as a small service any agent can call—while borrowing the same principle: **the surrounding system is the product**.

| Dimension | **Claw Code** ([instructkr/claw-code](https://github.com/instructkr/claw-code)) | **OmniMission MCP** (this repo) |
|---|----------------|----------------------------------|
| **Primary aim** | Faithful, educational harness architecture (tools, orchestration, manifests, verification patterns) in a single application. | Production-oriented **mission planning + semantic skill discovery** as a **pluggable MCP/HTTP service**. |
| **Interface** | In-process / project-bound. | **MCP over HTTP/SSE** + **OpenAPI** (`POST /v1/plan`). |
| **Discovery** | Depends on how you wire tools in code. | **Chroma + embeddings** with ranking, dedupe, optional policy filters. |
| **Guardrails** | Your app’s policy layer. | Built-in **policy** knobs (`policy_block_keywords`, `policy_min_safety_score`) + **verification** against the index. |
| **State** | Rich runtime context inside the harness. | **Stateless** by default; optional **`mission_id`** checkpoints in Chroma. |
| **Ops story** | Varies by deployment. | **Metrics**, health, Docker Compose, crawler worker. |

### Calling `plan_mission` (MCP)

The MCP app is mounted at **`/mcp`** (streamable HTTP / SSE, per the [Model Context Protocol](https://modelcontextprotocol.io/)). Use any MCP client that supports HTTP transport and point it at:

`http://localhost:8080/mcp` (or your deployed host).

Register the tool **`plan_mission`**. Arguments:

- **`mission`** (string, required): natural-language goal.
- **`mission_id`** (string, optional): stable id to persist checkpoints when `mission_state_enabled` is true.
- **`include_ranking_details`** (boolean, default `true`): per-skill ranking components and verification hints.

The response includes **`skills`**, **`policy`** (including policy-drop counts), **`verification`** (index presence), optional **`mission_state`**, **`x402_preview`**, and **`install_commands`**.

**REST (same planner):**

```bash
curl -s -X POST http://localhost:8080/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"mission":"Ship a secure payments MCP","include_ranking_details":true}'
```

**Smoke checks (REST):**

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/ | jq .
curl -s http://localhost:8080/metrics | head
```

Prometheus scrape target: **`GET /metrics`** (`omnimission_*` series: HTTP latency/counts, `plan_mission` outcomes/durations, Chroma query count; the crawler process exposes `omnimission_crawler_runs_total` when the worker runs).

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

Useful variables include `OMNIMISSION_CHROMA_HOST`, `OMNIMISSION_CHROMA_PORT`, `OMNIMISSION_EMBED_MODEL`, `OMNIMISSION_CRAWLER_SEED_URLS`, **policy** (`OMNIMISSION_POLICY_BLOCK_KEYWORDS`, `OMNIMISSION_POLICY_MIN_SAFETY_SCORE`), **mission checkpoints** (`OMNIMISSION_MISSION_STATE_COLLECTION`, `OMNIMISSION_MISSION_STATE_ENABLED`), and optional **x402** settings (`OMNIMISSION_X402_ASK_ENABLED`, `OMNIMISSION_X402_PAY_TO`, …) for pay-per-use gating on `/mcp`.

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
| `omnimission-audit` | Print a full JSON plan (ranking, policy, verification); requires Chroma + index (pass mission as arg or stdin) |

## Repository layout

- `src/omnimission/` — application package (API, MCP, planner, crawler, Chroma store, config)
- `docker/` — container build
- `openapi/` — exported OpenAPI snapshot (if present)

