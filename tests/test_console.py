from fastapi.testclient import TestClient

from sql_doctor.api import create_app


def test_console_lists_reports_without_sql():
    client = TestClient(create_app(":memory:"))
    page = client.get("/")
    assert page.status_code == 200
    assert 'data-shell="studio"' in page.text
    created = client.post("/api/diagnose", json={"sql": "SELECT id FROM orders WHERE name LIKE '%x%'"})
    assert created.status_code == 200
    listed = client.get("/api/reports")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created.json()["id"]
    assert "SELECT" not in listed.text
    assert listed.json()[0]["performance_claim"] if False else "performance_claim" not in listed.json()[0]
