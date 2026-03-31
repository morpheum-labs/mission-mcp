from __future__ import annotations

from fastmcp import FastMCP

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
        return planner.plan(mission)

    return mcp
