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
