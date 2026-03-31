from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str = Field(examples=["omnimission-api"])


class PlanMissionInput(BaseModel):
    """Validates the `plan_mission` tool and REST body."""

    mission: str = Field(..., max_length=8000)
    mission_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional stable id to append checkpoints in the mission_state collection.",
    )
    include_ranking_details: bool = Field(
        default=True,
        description="Include per-skill ranking breakdown and verification hints.",
    )

    @field_validator("mission")
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("mission must not be empty")
        return s

    @field_validator("mission_id")
    @classmethod
    def mission_id_ok(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        if not re.match(r"^[A-Za-z0-9._:-]{1,128}$", s):
            raise ValueError("mission_id must be alphanumeric with ._:- only")
        return s
