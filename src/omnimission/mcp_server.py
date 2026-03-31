from __future__ import annotations

import time

from fastmcp import FastMCP
from pydantic import ValidationError

from omnimission.api.schemas import PlanMissionInput
from omnimission.monitoring import record_plan_mission
from omnimission.planner.service import MissionPlanner


def build_mcp(planner: MissionPlanner) -> FastMCP:
    mcp = FastMCP(
        "OmniMission",
        instructions=(
            "Plans missions by ranking indexed skills and MCPs for a short natural-language goal. "
            "Returns deduplicated picks, quality/safety scores, policy summary, verification against "
            "the index, optional x402 USD preview, install hints, and optional mission_id checkpoints."
        ),
    )

    @mcp.tool
    def plan_mission(
        mission: str,
        mission_id: str | None = None,
        include_ranking_details: bool = True,
    ) -> dict:
        """Rank skills/MCPs for this mission (semantic match + metadata scores + policy + verify)."""
        t0 = time.perf_counter()
        try:
            payload = PlanMissionInput(
                mission=mission,
                mission_id=mission_id,
                include_ranking_details=include_ranking_details,
            )
        except ValidationError as e:
            record_plan_mission(
                duration_seconds=time.perf_counter() - t0,
                status="validation_error",
            )
            return {"error": "validation_error", "detail": e.errors()}
        try:
            out = planner.plan(
                payload.mission,
                mission_id=payload.mission_id,
                include_ranking_details=payload.include_ranking_details,
            )
            record_plan_mission(
                duration_seconds=time.perf_counter() - t0,
                status="success",
            )
            return out
        except Exception as e:
            record_plan_mission(
                duration_seconds=time.perf_counter() - t0,
                status="plan_failed",
            )
            return {"error": "plan_failed", "detail": str(e)[:500]}

    return mcp
