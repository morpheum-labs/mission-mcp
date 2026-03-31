"""Print a JSON plan with ranking/policy/verification for local auditing (requires a running Chroma index)."""

from __future__ import annotations

import argparse
import json
import sys

from omnimission.chroma_store import ChromaStore
from omnimission.config import get_settings
from omnimission.mission_state import MissionStateStore
from omnimission.planner.service import MissionPlanner


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run plan_mission-equivalent logic and print JSON (ranking audit, policy, verification).",
    )
    parser.add_argument(
        "mission",
        nargs="?",
        default="",
        help="Natural-language mission (or pass via stdin if empty).",
    )
    parser.add_argument(
        "--mission-id",
        default=None,
        help="Optional mission id for checkpoint persistence.",
    )
    parser.add_argument(
        "--no-ranking-details",
        action="store_true",
        help="Omit per-skill ranking dicts.",
    )
    args = parser.parse_args()
    mission = (args.mission or "").strip()
    if not mission:
        mission = sys.stdin.read().strip()
    if not mission:
        parser.error("mission text required (argument or stdin)")

    settings = get_settings()
    store = ChromaStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        collection_name=settings.collection_name,
    )
    mission_state: MissionStateStore | None = None
    if settings.mission_state_enabled:
        mission_state = MissionStateStore(
            settings,
            ChromaStore(
                host=settings.chroma_host,
                port=settings.chroma_port,
                collection_name=settings.mission_state_collection,
            ),
        )
    planner = MissionPlanner(settings, store, mission_state=mission_state)
    out = planner.plan(
        mission,
        mission_id=args.mission_id,
        include_ranking_details=not args.no_ranking_details,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
