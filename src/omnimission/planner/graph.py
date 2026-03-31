from __future__ import annotations

from typing import TypedDict


class PlannerState(TypedDict, total=False):
    mission: str
    intent_summary: str
    subtasks: list[str]
    ranked_skills: list[dict]
    x402_preview: dict
    install_commands: list[str]
