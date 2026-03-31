from __future__ import annotations

from typing import Any

from omnimission.config import Settings


def parse_block_keywords(raw: str) -> list[str]:
    return [k.strip().lower() for k in (raw or "").split(",") if k.strip()]


def policy_violations(meta: dict[str, Any], row_preview: dict[str, Any], settings: Settings) -> list[str]:
    """Return human-readable violation codes; empty list means the skill passes policy."""
    violations: list[str] = []
    try:
        s = float(meta.get("safety_score") or 0.0)
    except (TypeError, ValueError):
        s = 0.0
    min_s = float(settings.policy_min_safety_score or 0.0)
    if min_s > 0.0 and s < min_s:
        violations.append("below_min_safety")

    hay = " ".join(
        [
            str(row_preview.get("title", "")),
            str(row_preview.get("snippet", "")),
            str(meta.get("source_url", "")),
            str(meta.get("publisher", "")),
            str(meta.get("title", "")),
        ]
    ).lower()
    for kw in parse_block_keywords(settings.policy_block_keywords):
        if kw and kw in hay:
            violations.append(f"blocked_keyword:{kw}")
    return violations
