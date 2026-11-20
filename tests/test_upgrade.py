import pytest

from sql_doctor.analyze import compare_plans, diagnose, explain_readonly, parse_explain

SQL = "SELECT id FROM orders WHERE customer_id = 1 ORDER BY created_at"


class Conn:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return "Seq Scan on orders  (cost=0.00..1.00 rows=1 width=4)"


def test_existing_index_is_not_suggested_again():
    unchecked = diagnose(SQL)
    assert unchecked["index_candidates"][0]["checked_existing"] is False
    checked = diagnose(SQL, existing_indexes=[["customer_id", "created_at"]])
    assert checked["index_candidates"] == []
    fresh = diagnose(SQL, existing_indexes=[["id"]])
    assert fresh["index_candidates"][0]["columns"] == ["customer_id", "created_at"]
    assert fresh["index_candidates"][0]["checked_existing"] is True


def test_plan_compare_has_no_speedup_claim():
    before = parse_explain("Seq Scan on orders  (cost=0.00..10.00 rows=10 width=4)")
    after = parse_explain("Index Scan on orders  (cost=0.00..1.00 rows=1 width=4)")
    compared = compare_plans(before, after)
    assert compared["before_count"] == 1
    assert compared["after_count"] == 1
    assert compared["performance_claim"] is None


def test_readonly_explain_never_sends_writes():
    conn = Conn()
    with pytest.raises(PermissionError):
        explain_readonly("DELETE FROM orders WHERE id = 1", conn)
    assert conn.statements == []
    text = explain_readonly(SQL, conn)
    assert text.startswith("Seq Scan")
    assert conn.statements[0].startswith("EXPLAIN ")
    assert "DELETE" not in conn.statements[0].upper()
