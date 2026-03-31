from __future__ import annotations

import json
import re
from typing import Any

from langgraph.graph import END, StateGraph

from omnimission.chroma_store import ChromaStore
from omnimission.config import Settings
from omnimission.embeddings import embed_query
from omnimission.monitoring import observe_chroma_query
from omnimission.planner.graph import PlannerState
from omnimission.x402_preview import grand_total_preview


def _coerce_float(v: Any, default: float) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_subtasks(mission: str) -> list[str]:
    parts = re.split(r"[.;]\s+", mission.strip())
    return [p.strip() for p in parts if len(p.strip()) > 8][:6]


def _publisher_key(meta: dict[str, Any]) -> str:
    pub = meta.get("publisher") or "unknown"
    return str(pub).strip().lower()[:128]


def _rank_and_dedupe(
    ids: list[str],
    metas: list[dict[str, Any]],
    distances: list[float],
    documents: list[str],
    top_k: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sid, meta, dist, doc in zip(ids, metas, distances, documents, strict=True):
        q = _coerce_float(meta.get("quality_score"), 70.0)
        s = _coerce_float(meta.get("safety_score"), 75.0)
        x402 = _coerce_float(meta.get("x402_price_usd"), 0.0)
        d = float(dist)
        relevance = max(0.0, min(1.0, 1.0 - d))
        score = relevance * (q / 100.0) * (0.55 + min(s, 100.0) / 200.0)
        install_raw = meta.get("install_commands_json") or "[]"
        try:
            installs = json.loads(install_raw) if isinstance(install_raw, str) else install_raw
        except json.JSONDecodeError:
            installs = [str(install_raw)]
        if isinstance(installs, str):
            installs = [installs]
        rows.append(
            {
                "id": sid,
                "title": meta.get("title", ""),
                "publisher": meta.get("publisher", ""),
                "source_url": meta.get("source_url", ""),
                "quality_score": round(q, 2),
                "safety_score": round(s, 2),
                "x402_price_usd": x402,
                "relevance": round(relevance, 4),
                "distance": round(d, 6),
                "combined_score": round(score, 6),
                "install_commands": installs,
                "snippet": (doc or "")[:400],
            }
        )

    best_by_pub: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _publisher_key(row)
        prev = best_by_pub.get(key)
        if prev is None or row["combined_score"] > prev["combined_score"]:
            best_by_pub[key] = row

    ranked = sorted(best_by_pub.values(), key=lambda r: r["combined_score"], reverse=True)
    return ranked[:top_k]


class MissionPlanner:
    def __init__(self, settings: Settings, store: ChromaStore) -> None:
        self._settings = settings
        self._store = store
        self._graph = self._compile()

    def _compile(self):
        graph = StateGraph(PlannerState)

        def intent_node(state: PlannerState) -> PlannerState:
            mission = state.get("mission") or ""
            return {
                "intent_summary": mission[:800],
                "subtasks": _parse_subtasks(mission),
            }

        def rank_node(state: PlannerState) -> PlannerState:
            mission = state.get("mission") or ""
            emb = embed_query(self._settings.embed_model, mission)
            ids, metas, dists, docs = self._store.query(
                query_embedding=emb,
                n_results=self._settings.fetch_n,
            )
            observe_chroma_query()
            ranked = _rank_and_dedupe(
                ids,
                metas,
                dists,
                docs,
                top_k=self._settings.top_k,
            )
            preview = grand_total_preview(ranked)
            flat_installs: list[str] = []
            for r in ranked:
                for c in r.get("install_commands") or []:
                    if c and c not in flat_installs:
                        flat_installs.append(c)
            return {
                "ranked_skills": ranked,
                "x402_preview": preview,
                "install_commands": flat_installs[:20],
            }

        graph.add_node("intent", intent_node)
        graph.add_node("rank", rank_node)
        graph.set_entry_point("intent")
        graph.add_edge("intent", "rank")
        graph.add_edge("rank", END)
        return graph.compile()

    def plan(self, mission: str) -> dict[str, Any]:
        out: PlannerState = self._graph.invoke({"mission": mission})
        return {
            "mission": mission,
            "intent_summary": out.get("intent_summary", ""),
            "subtasks": out.get("subtasks") or [],
            "skills": out.get("ranked_skills") or [],
            "x402_preview": out.get("x402_preview") or {},
            "install_commands": out.get("install_commands") or [],
            "x402_ask": {
                "enabled": self._settings.x402_ask_enabled,
                "note": (
                    "When enabled, MCP HTTP access to this server requires x402 payment "
                    "before tools run; see PAYMENT-REQUIRED / 402 on /mcp."
                ),
            },
        }
