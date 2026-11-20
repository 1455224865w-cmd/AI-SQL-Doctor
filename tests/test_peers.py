import pytest

from sql_doctor.analyze import cost_shares, diagnose, parse_explain

SQL = "SELECT id FROM orders WHERE customer_id = 1"
EXPLAIN = """
Limit  (cost=0.00..10.00 rows=20 width=4) (actual time=0.100..0.200 rows=20 loops=1)
  ->  Seq Scan on orders  (cost=0.00..1000.00 rows=50 width=4) (actual time=0.050..80.000 rows=5000 loops=1)
"""


def test_cost_share_stays_an_estimate():
    shares = cost_shares(parse_explain(EXPLAIN))
    seq = next(node for node in shares if node["kind"] == "Seq Scan")
    assert seq["cost_share"] >= 0.5
    report = diagnose(SQL, EXPLAIN)
    assert report["performance_claim"] is None
    assert any(item["name"] == "计划成本集中" for item in report["findings"])
    tiny = diagnose(SQL, "Seq Scan on orders  (cost=0.00..1.00 rows=1 width=4)")
    assert tiny["performance_claim"] is None
    assert all(item["name"] != "计划成本集中" for item in tiny["findings"])


def test_json_plan_filter_and_multiple_statements():
    import json
    from sql_doctor.analyze import explain_readonly

    text = """
Seq Scan on orders  (cost=0.00..1000.00 rows=1000 width=4) (actual time=0.100..2.000 rows=10 loops=1)
  Filter: (status = 'open')
  Rows Removed by Filter: 5000
"""
    report = diagnose("SELECT id FROM orders WHERE status = 'open'", text)
    assert any(item["name"] == "过滤丢弃了大量行" for item in report["findings"])
    assert report["performance_claim"] is None
    payload = json.dumps([{
        "Plan": {
            "Node Type": "Index Scan",
            "Relation Name": "orders",
            "Startup Cost": 0.29,
            "Total Cost": 8.31,
            "Plan Rows": 1,
            "Plan Width": 4,
            "Actual Rows": 1,
            "Plans": [],
        }
    }])
    nodes = parse_explain(payload)
    assert nodes[0]["kind"] == "Index Scan"
    assert nodes[0]["relation"] == "orders"
    multi = diagnose("SELECT id FROM orders; DELETE FROM orders")
    assert multi["parsed"] is False
    assert multi["findings"][0]["name"] == "包含多条语句"
    assert multi["performance_claim"] is None

    class Conn:
        def __init__(self):
            self.statements = []
        def execute(self, statement):
            self.statements.append(statement)
            return "ok"

    conn = Conn()
    with pytest.raises(PermissionError):
        explain_readonly("SELECT id FROM orders; DELETE FROM orders", conn)
    assert conn.statements == []


def test_join_without_condition_is_not_a_speedup():
    report = diagnose("SELECT orders.id FROM orders JOIN customers")
    item = next(finding for finding in report["findings"] if finding["name"] == "连接没有条件")
    assert item["severity"] == "info"
    assert report["performance_claim"] is None
    matched = diagnose("SELECT orders.id FROM orders JOIN customers ON orders.id = customers.order_id")
    assert all(finding["name"] != "连接没有条件" for finding in matched["findings"])


def test_buffer_reads_do_not_become_a_speedup():
    text = """
Seq Scan on orders  (cost=0.00..10.00 rows=10 width=4) (actual time=0.1..1.0 rows=10 loops=1)
  Buffers: shared hit=1 read=500
"""
    report = diagnose("SELECT id FROM orders", text)
    assert any(item["name"] == "缓存读入偏多" for item in report["findings"])
    assert report["performance_claim"] is None
