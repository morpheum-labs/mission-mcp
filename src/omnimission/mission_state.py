from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from omnimission.chroma_store import ChromaStore
from omnimission.config import Settings
from omnimission.embeddings import embed_query


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


class MissionStateStore:
    """Persists optional long-running mission checkpoints in a dedicated Chroma collection."""

    def __init__(self, settings: Settings, store: ChromaStore) -> None:
        self._settings = settings
        self._store = store

    def load(self, mission_id: str) -> dict[str, Any] | None:
        m = self._store.get_document_map([mission_id])
        raw = m.get(mission_id)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def save_checkpoint(
        self,
        mission_id: str,
        mission: str,
        plan_payload: dict[str, Any],
    ) -> dict[str, Any]:
        prev = self.load(mission_id) or {}
        history: list[dict[str, Any]] = list(prev.get("history") or [])
        entry = {
            "at": _utc_now_iso(),
            "mission": mission[:2000],
            "skill_ids": [s.get("id") for s in (plan_payload.get("skills") or []) if s.get("id")],
            "verified_all": (plan_payload.get("verification") or {}).get("all_verified"),
        }
        history.append(entry)
        state = {
            "mission_id": mission_id,
            "updated_at": entry["at"],
            "history": history[-200:],
            "last_plan": {
                "intent_summary": plan_payload.get("intent_summary"),
                "skills": plan_payload.get("skills"),
            },
        }
        doc = json.dumps(state, ensure_ascii=False)
        emb = embed_query(
            self._settings.embed_model,
            f"mission_state:{mission_id}\n{mission[:1500]}",
        )
        self._store.upsert(
            ids=[mission_id],
            embeddings=[emb],
            documents=[doc],
            metadatas=[{"mission_id": mission_id, "updated_at": state["updated_at"]}],
        )
        return state
