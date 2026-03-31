from __future__ import annotations

from fastmcp import FastMCP
from pydantic import ValidationError

from omnimission.api.schemas import PlanMissionInput
from omnimission.planner.service import MissionPlanner


def build_mcp(planner: MissionPlanner) -> FastMCP:
    mcp = FastMCP(
        "OmniMission",
        instructions=(
            "Plans missions by ranking indexed skills and MCPs for a short natural-language goal. "
            "Returns deduplicated picks, quality/safety scores, x402 USD preview, and install hints."
        ),
    )

    @mcp.tool
    def plan_mission(mission: str) -> dict:
        """Rank the best 8–12 skills/MCPs for this mission (semantic match + metadata scores)."""
        try:
            payload = PlanMissionInput(mission=mission)
        except ValidationError as e:
            return {"error": "validation_error", "detail": e.errors()}
        try:
            return planner.plan(payload.mission)
        except Exception as e:
            return {"error": "plan_failed", "detail": str(e)[:500]}

    return mcp
