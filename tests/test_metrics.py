from fastapi.testclient import TestClient

from omnimission.api.main import app


def test_metrics_endpoint_exposes_omnimission_series() -> None:
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "omnimission_http_requests_total" in body
    assert "omnimission_plan_mission_total" in body
    assert "omnimission_chroma_queries_total" in body
