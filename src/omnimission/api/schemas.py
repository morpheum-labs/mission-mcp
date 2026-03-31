from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    service: str = Field(examples=["omnimission-api"])


class PlanMissionInput(BaseModel):
    """Validates the `mission` argument for the MCP tool `plan_mission`."""

    mission: str = Field(..., max_length=8000)

    @field_validator("mission")
    @classmethod
    def strip_nonempty(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("mission must not be empty")
        return s
