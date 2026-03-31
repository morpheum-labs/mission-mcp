"""Mission planner + Chroma query path (mocked embeddings and store)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from omnimission.config import Settings
from omnimission.planner.service import (
    MissionPlanner,
    _rank_and_dedupe,
    _sort_skills_relevance_then_cost,
)


@pytest.fixture
def planner_settings() -> Settings:
    return Settings(
        embed_model="test-model",
        top_k=4,
        fetch_n=4,
    )


def _sample_query_result() -> tuple[list[str], list[dict], list[float], list[str]]:
    ids = ["id1", "id2"]
    metas = [
        {
            "title": "Skill A",
            "publisher": "pub-a.example",
            "source_url": "https://a",
            "quality_score": 90.0,
            "safety_score": 80.0,
            "x402_price_usd": 0.02,
            "install_commands_json": "[]",
        },
        {
            "title": "Skill B",
            "publisher": "pub-b.example",
            "source_url": "https://b",
            "quality_score": 85.0,
            "safety_score": 75.0,
            "x402_price_usd": 0.0,
            "install_commands_json": "[]",
        },
    ]
    dists = [0.1, 0.2]
    docs = ["doc a text", "doc b text"]
    return ids, metas, dists, docs


@patch("omnimission.planner.service.embed_query", return_value=[0.0] * 8)
def test_mission_planner_success(mock_embed: MagicMock, planner_settings: Settings) -> None:
    store = MagicMock()
    store.query.return_value = _sample_query_result()
    planner = MissionPlanner(planner_settings, store)

    result = planner.plan("Build a trader; deploy safely")

    assert result["mission"] == "Build a trader; deploy safely"
    assert result["intent_summary"].startswith("Build a trader")
    assert isinstance(result["subtasks"], list)
    assert len(result["skills"]) == 2
    assert {s["title"] for s in result["skills"]} == {"Skill A", "Skill B"}
    assert result["x402_preview"]["grand_total_usd"] == pytest.approx(0.02)
    assert result["x402_preview"]["priced_skills"] == 2
    assert result["x402_ask"]["enabled"] is False

    mock_embed.assert_called_once_with("test-model", "Build a trader; deploy safely")
    store.query.assert_called_once()
    call_kw = store.query.call_args.kwargs
    assert call_kw["n_results"] == 4
    assert len(call_kw["query_embedding"]) == 8


@patch("omnimission.planner.service.embed_query", return_value=[0.0] * 8)
def test_mission_planner_chroma_error(mock_embed: MagicMock, planner_settings: Settings) -> None:
    store = MagicMock()
    store.query.side_effect = RuntimeError("Chroma down")
    planner = MissionPlanner(planner_settings, store)

    with pytest.raises(RuntimeError, match="Chroma down"):
        planner.plan("test mission")


def test_sort_skills_free_before_paid_when_combined_score_tied() -> None:
    skills = [
        {"title": "paid", "combined_score": 0.5, "x402_price_usd": 0.10},
        {"title": "free", "combined_score": 0.5, "x402_price_usd": 0.0},
    ]
    out = _sort_skills_relevance_then_cost(skills)
    assert [s["title"] for s in out] == ["free", "paid"]


def test_rank_and_dedupe_one_skill_per_publisher() -> None:
    ids = ["a1", "a2", "b1"]
    metas = [
        {
            "title": "low",
            "publisher": "samepub",
            "quality_score": 80.0,
            "safety_score": 80.0,
            "install_commands_json": "[]",
        },
        {
            "title": "high",
            "publisher": "samepub",
            "quality_score": 95.0,
            "safety_score": 80.0,
            "install_commands_json": "[]",
        },
        {
            "title": "other",
            "publisher": "otherpub",
            "quality_score": 70.0,
            "safety_score": 80.0,
            "install_commands_json": "[]",
        },
    ]
    dists = [0.5, 0.05, 0.3]
    docs = ["d1", "d2", "d3"]
    ranked = _rank_and_dedupe(ids, metas, dists, docs, top_k=10)
    assert len(ranked) == 2
    pubs = {r["publisher"] for r in ranked}
    assert pubs == {"samepub", "otherpub"}
    same_pub_rows = [r for r in ranked if r["publisher"] == "samepub"]
    assert len(same_pub_rows) == 1
    assert same_pub_rows[0]["title"] == "high"
