import json
from pathlib import Path

from fastapi.testclient import TestClient

from sql_doctor.api import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_english_findings_keep_no_speedup_claim():
    client = TestClient(create_app(":memory:"))
    body = {"sql": "SELECT id FROM orders", "explain": "Seq Scan on orders  (cost=0.00..1.00 rows=1 width=4)"}
    chinese = client.post("/api/diagnose", json=body)
    assert chinese.json()["report"]["findings"][0]["name"] == "顺序扫描"
    assert chinese.json()["report"]["performance_claim"] is None
    english = client.post("/api/diagnose", json=body, headers={"Accept-Language": "en"})
    assert english.json()["report"]["findings"][0]["name"] == "Sequential scan"
    assert english.json()["report"]["performance_claim"] is None
    called = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "sql_diagnose", "arguments": {"sql": "SELECT id FROM orders; DELETE FROM orders", "locale": "en"}},
    })
    payload = json.loads(called.json()["result"]["content"][0]["text"])
    assert payload["findings"][0]["name"] == "Multiple statements"
    assert payload["performance_claim"] is None
    assert "speedup" in payload["message"]
    spring = (ROOT / "spring-ai" / "application-mcp.yml").read_text(encoding="utf-8")
    assert "streamable-http:" in spring and "endpoint: /mcp" in spring
