from __future__ import annotations

from typing import Any


def grand_total_preview(skills: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate x402-style USD hints from skill metadata (preview only, no chain calls)."""
    total = 0.0
    priced = 0
    for s in skills:
        p = s.get("x402_price_usd")
        if p is None:
            continue
        try:
            total += float(p)
            priced += 1
        except (TypeError, ValueError):
            continue
    return {
        "currency": "USD",
        "grand_total_usd": round(total, 6),
        "priced_skills": priced,
        "note": "Preview from indexed metadata; verify with live x402 requirements before paying.",
    }
