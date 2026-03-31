from omnimission import ingest
from omnimission.api.schemas import PlanMissionInput
from pydantic import ValidationError


def test_chunk_id_dedupes_same_title_body() -> None:
    a = ingest._chunk_id("My Skill", "body text")
    b = ingest._chunk_id("My Skill", "body text")
    assert a == b
    assert len(a) == 64


def test_chunk_id_differs_when_body_differs() -> None:
    assert ingest._chunk_id("T", "a") != ingest._chunk_id("T", "b")


def test_plan_mission_input_rejects_empty() -> None:
    try:
        PlanMissionInput(mission="   ")
    except ValidationError as e:
        assert e.errors()
    else:
        raise AssertionError("expected ValidationError")


def test_plan_mission_input_accepts_trimmed() -> None:
    m = PlanMissionInput(mission="  find skills for PDFs  ")
    assert m.mission == "find skills for PDFs"
