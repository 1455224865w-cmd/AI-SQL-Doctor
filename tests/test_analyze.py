from sql_doctor.analyze import diagnose, parse_explain

SQL = """
SELECT * FROM orders
WHERE lower(status) = 'open' AND customer_id = 1 AND note LIKE '%rush%'
ORDER BY created_at
LIMIT 20 OFFSET 5000
"""

EXPLAIN = """
Limit  (cost=0.00..10.00 rows=20 width=4) (actual time=0.100..0.200 rows=20 loops=1)
  ->  Seq Scan on orders  (cost=0.00..1000.00 rows=50 width=4) (actual time=0.050..80.000 rows=5000 loops=1)
        Filter: (status = 'open')
"""


def test_sql_and_explain_findings_do_not_claim_speedup():
    report = diagnose(SQL, EXPLAIN)
    assert report["parsed"] is True
    assert report["performance_claim"] is None
    assert "orders" in report["structure"]["tables"]
    names = {item["name"] for item in report["findings"]}
    assert "查询返回全部列" in names
    assert "前导模糊匹配" in names
    assert "深分页" in names
    assert "条件里的列套了函数" in names
    assert "顺序扫描" in names
    assert "行数估算误差" in names
    assert report["index_candidates"][0]["columns"] == ["customer_id", "created_at"]
    seq = next(item for item in report["findings"] if item["name"] == "顺序扫描")
    assert seq["severity"] == "info"


def test_write_statement_is_not_executed():
    report = diagnose("DELETE FROM orders WHERE id = 1")
    assert report["findings"][0]["severity"] == "high"
    assert report["index_candidates"] == []


def test_broken_sql_has_no_fake_structure():
    report = diagnose("SELECT FROM")
    assert report["parsed"] is False
    assert report["structure"] is None


def test_explain_tree_rows():
    nodes = parse_explain(EXPLAIN)
    assert [node["kind"] for node in nodes] == ["Limit", "Seq Scan"]
    assert nodes[1]["actual_rows"] == 5000
    assert nodes[1]["relation"] == "orders"
