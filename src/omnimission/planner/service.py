from __future__ import annotations

import json
import re
from typing import Any

from langgraph.graph import END, StateGraph

from omnimission.chroma_store import ChromaStore
from omnimission.config import Settings
from omnimission.embeddings import embed_query
from omnimission.mission_state import MissionStateStore
from omnimission.monitoring import observe_chroma_query
from omnimission.planner.graph import PlannerState
from omnimission.policy import policy_violations
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
    settings: Settings,
    include_ranking_details: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    policy_dropped: list[dict[str, Any]] = []
    for sid, meta, dist, doc in zip(ids, metas, distances, documents, strict=True):
        q = _coerce_float(meta.get("quality_score"), 70.0)
        s = _coerce_float(meta.get("safety_score"), 75.0)
        x402 = _coerce_float(meta.get("x402_price_usd"), 0.0)
        d = float(dist)
        relevance = max(0.0, min(1.0, 1.0 - d))
        quality_factor = q / 100.0
        safety_multiplier = 0.55 + min(s, 100.0) / 200.0
        score = relevance * quality_factor * safety_multiplier
        install_raw = meta.get("install_commands_json") or "[]"
        try:
            installs = json.loads(install_raw) if isinstance(install_raw, str) else install_raw
        except json.JSONDecodeError:
            installs = [str(install_raw)]
        if isinstance(installs, str):
            installs = [installs]
        row_preview = {
            "title": meta.get("title", ""),
            "publisher": meta.get("publisher", ""),
            "snippet": (doc or "")[:400],
        }
        viol = policy_violations(meta, row_preview, settings)
        if viol:
            policy_dropped.append({"id": sid, "violations": viol})
            continue

        ranking: dict[str, Any] = {}
        if include_ranking_details:
            ranking = {
                "formula": "relevance * (quality_score/100) * (0.55 + min(safety_score,100)/200)",
                "components": {
                    "distance": round(d, 6),
                    "relevance": round(relevance, 6),
                    "quality_score": round(q, 4),
                    "quality_factor": round(quality_factor, 6),
                    "safety_score": round(s, 4),
                    "safety_multiplier": round(safety_multiplier, 6),
                },
                "dedupe_scope": "one_best_per_publisher_key",
                "sort_after_graph": "combined_score desc, then x402_price_usd asc",
            }

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
                "ranking": ranking,
            }
        )

    best_by_pub: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _publisher_key(row)
        prev = best_by_pub.get(key)
        if prev is None or row["combined_score"] > prev["combined_score"]:
            if prev is not None and include_ranking_details:
                pr = prev.get("ranking") or {}
                pr["dedupe_outcome"] = "dropped_lower_combined_score_same_publisher"
                prev["ranking"] = pr
            best_by_pub[key] = row

    for row in best_by_pub.values():
        if include_ranking_details:
            rnk = row.get("ranking") or {}
            rnk["dedupe_outcome"] = "kept_highest_combined_score_for_publisher"
            row["ranking"] = rnk

    ranked = sorted(best_by_pub.values(), key=lambda r: r["combined_score"], reverse=True)
    trimmed = ranked[:top_k]
    audit = {
        "policy_dropped_count": len(policy_dropped),
        "policy_dropped_sample": policy_dropped[:8],
        "candidates_after_policy": len(rows),
        "publishers_after_dedupe": len(trimmed),
    }
    return trimmed, audit


def _sort_skills_relevance_then_cost(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Primary: highest combined_score first; secondary: lower x402_price_usd first (free before paid)."""
    return sorted(
        skills,
        key=lambda s: (
            -_coerce_float(s.get("combined_score"), 0.0),
            _coerce_float(s.get("x402_price_usd"), 0.0),
        ),
    )


class MissionPlanner:
    def __init__(
        self,
        settings: Settings,
        store: ChromaStore,
        mission_state: MissionStateStore | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._mission_state = mission_state
        self._graph = self._compile()

    def _compile(self):
        graph = StateGraph(PlannerState)

        def intent_node(state: PlannerState) -> PlannerState:
            mission = state.get("mission") or ""
            return {
                "intent_summary": mission[:800],
                "subtasks": _parse_subtasks(mission),
                "include_ranking_details": state.get("include_ranking_details", True),
            }

        def rank_node(state: PlannerState) -> PlannerState:
            mission = state.get("mission") or ""
            include_ranking = bool(state.get("include_ranking_details", True))
            emb = embed_query(self._settings.embed_model, mission)
            ids, metas, dists, docs = self._store.query(
                query_embedding=emb,
                n_results=self._settings.fetch_n,
            )
            observe_chroma_query()
            ranked, audit = _rank_and_dedupe(
                ids,
                metas,
                dists,
                docs,
                top_k=self._settings.top_k,
                settings=self._settings,
                include_ranking_details=include_ranking,
            )
            preview = grand_total_preview(ranked)
            flat_installs: list[str] = []
            for r in ranked:
                for c in r.get("install_commands") or []:
                    if c and c not in flat_installs:
                        flat_installs.append(c)
            policy_summary = {
                "block_keywords_active": bool(
                    (self._settings.policy_block_keywords or "").strip()
                ),
                "min_safety_score": self._settings.policy_min_safety_score,
                **audit,
            }
            return {
                "ranked_skills": ranked,
                "x402_preview": preview,
                "install_commands": flat_installs[:20],
                "policy": policy_summary,
            }

        def verify_node(state: PlannerState) -> PlannerState:
            ranked = state.get("ranked_skills") or []
            skill_ids = [str(r.get("id")) for r in ranked if r.get("id")]
            present = self._store.get_by_ids(skill_ids)
            missing = [sid for sid in skill_ids if sid not in present]
            for r in ranked:
                sid = str(r.get("id") or "")
                ok = sid in present
                r["verified"] = ok
                if r.get("ranking") is not None:
                    r["ranking"]["verification"] = "present_in_index" if ok else "missing_from_index"
            return {
                "verification": {
                    "checked": len(skill_ids),
                    "present": len(present),
                    "missing_ids": missing,
                    "all_verified": len(missing) == 0,
                },
            }

        graph.add_node("intent", intent_node)
        graph.add_node("rank", rank_node)
        graph.add_node("verify", verify_node)
        graph.set_entry_point("intent")
        graph.add_edge("intent", "rank")
        graph.add_edge("rank", "verify")
        graph.add_edge("verify", END)
        return graph.compile()

    def plan(
        self,
        mission: str,
        *,
        mission_id: str | None = None,
        include_ranking_details: bool = True,
    ) -> dict[str, Any]:
        out: PlannerState = self._graph.invoke(
            {
                "mission": mission,
                "include_ranking_details": include_ranking_details,
            }
        )
        skills = _sort_skills_relevance_then_cost(out.get("ranked_skills") or [])
        if not include_ranking_details:
            for s in skills:
                s.pop("ranking", None)

        payload: dict[str, Any] = {
            "mission": mission,
            "intent_summary": out.get("intent_summary", ""),
            "subtasks": out.get("subtasks") or [],
            "skills": skills,
            "x402_preview": out.get("x402_preview") or {},
            "install_commands": out.get("install_commands") or [],
            "policy": out.get("policy") or {},
            "verification": out.get("verification") or {},
            "x402_ask": {
                "enabled": self._settings.x402_ask_enabled,
                "note": (
                    "When enabled, MCP HTTP access to this server requires x402 payment "
                    "before tools run; see PAYMENT-REQUIRED / 402 on /mcp."
                ),
            },
        }
        if mission_id:
            payload["mission_id"] = mission_id
            if self._mission_state is not None and self._settings.mission_state_enabled:
                st = self._mission_state.save_checkpoint(mission_id, mission, payload)
                payload["mission_state"] = {
                    "mission_id": mission_id,
                    "checkpoint_count": len(st.get("history") or []),
                    "recent_history": (st.get("history") or [])[-5:],
                    "updated_at": st.get("updated_at"),
                }

        return payload
