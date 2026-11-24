"""SQL 结构、执行计划文本和候选优化。建议都是候选，不表示已经变快。"""

from __future__ import annotations

import json
import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

NODE_RE = re.compile(
    r"^(?P<kind>.+?)(?:\s+on\s+(?P<relation>\S+))?\s+"
    r"\(cost=(?P<cost_start>[\d.]+)\.\.(?P<cost_end>[\d.]+)\s+rows=(?P<rows>\d+)\s+width=(?P<width>\d+)\)"
    r"(?:\s+\(actual time=(?P<actual_start>[\d.]+)\.\.(?P<actual_end>[\d.]+)\s+"
    r"rows=(?P<actual_rows>\d+)\s+loops=(?P<loops>\d+)\))?"
)


def finding(name, severity, evidence, reason, impact, direction, risk, verification) -> dict:
    return {
        "name": name,
        "severity": severity,
        "evidence": evidence,
        "reason": reason,
        "impact": impact,
        "direction": direction,
        "risk": risk,
        "verification": verification,
    }


def format_sql(sql: str, dialect: str = "postgres") -> str:
    return sqlglot.parse_one(sql, read=dialect).sql(dialect=dialect, pretty=True)


def _structure(parsed) -> dict:
    likes = []
    for item in parsed.find_all(exp.Like):
        value = item.expression.this if isinstance(item.expression, exp.Literal) else item.expression.sql()
        likes.append({"expression": item.sql(), "pattern": str(value)})
    offset = parsed.args.get("offset")
    limit = parsed.args.get("limit")
    return {
        "statement": type(parsed).__name__,
        "tables": sorted({table.name for table in parsed.find_all(exp.Table)}),
        "joins": [join.sql() for join in parsed.find_all(exp.Join)],
        "ctes": [cte.alias for cte in parsed.find_all(exp.CTE)],
        "group_by": parsed.args.get("group").sql() if parsed.args.get("group") else None,
        "order_by": parsed.args.get("order").sql() if parsed.args.get("order") else None,
        "limit": limit.sql() if limit else None,
        "offset": int(offset.expression.this) if offset and isinstance(offset.expression, exp.Literal) else None,
        "likes": likes,
        "select_star": any(True for _ in parsed.find_all(exp.Star)),
    }


def _sql_findings(parsed, structure: dict) -> list[dict]:
    found = []
    if not isinstance(parsed, exp.Select):
        found.append(
            finding(
                "非只读语句",
                "high",
                type(parsed).__name__,
                "MVP 只分析语句，不执行它。写入语句默认被拒绝。",
                "如果误执行，会改动数据或结构。",
                "先改成只读的 EXPLAIN，或在独立环境由人确认后再执行。",
                "工具不会自动执行这条语句。",
                "确认连接账号没有写入权限。",
            )
        )
        return found
    if structure["select_star"]:
        found.append(
            finding(
                "查询返回全部列",
                "info",
                "SELECT *",
                "调用方如果只需要少数列，会多读数据。是否多余取决于业务。",
                "列很多或含大字段时，I/O 会升高。",
                "候选改写是列出实际使用的列。",
                "漏列会改变结果，不能直接替换生产 SQL。",
                "对照调用方使用的字段后，再用 EXPLAIN 比较。",
            )
        )
    for item in structure["likes"]:
        if str(item["pattern"]).startswith("%"):
            found.append(
                finding(
                    "前导模糊匹配",
                    "medium",
                    item["expression"],
                    "以 % 开头的 LIKE 通常用不上普通 B-Tree 索引。",
                    "表变大后，这个条件可能变成大范围扫描。",
                    "候选方案是改写匹配方式，或评估专门的文本索引。",
                    "改写可能改变匹配结果。",
                    "用同一批参数比较原 SQL 和候选 SQL 的结果集。",
                )
            )
    if structure["offset"] and structure["offset"] > 1000:
        found.append(
            finding(
                "深分页",
                "medium",
                f"OFFSET {structure['offset']}",
                "大 OFFSET 仍要扫描并丢弃前面的行。",
                "页码越往后越慢。",
                "候选方案是用上一页的排序键做范围查询。",
                "结果顺序和缺页行为可能变化。",
                "在相近数据量上比较两版 EXPLAIN ANALYZE，并核对结果集。",
            )
        )
    for join in parsed.find_all(exp.Join):
        if join.args.get("on") is None and not join.args.get("using"):
            found.append(
                finding(
                    "连接没有条件",
                    "info",
                    join.sql(),
                    "这个连接没有 ON 或 USING。它会按交叉连接解释，有时是有意写的。",
                    "两边行数都大时，结果集会迅速变大。",
                    "如果本意是等值连接，补上连接条件后再比较结果。",
                    "补错条件会改变结果集。",
                    "核对连接键，并用同一批数据比较行数。不写提升比例。",
                )
            )
    scopes = []
    where = parsed.args.get("where")
    if where is not None:
        scopes.append(where)
    for join in parsed.find_all(exp.Join):
        on_clause = join.args.get("on")
        if on_clause is not None:
            scopes.append(on_clause)
    for scope in scopes:
        for func in scope.find_all(exp.Lower, exp.Upper):
            if isinstance(func.this, exp.Column):
                found.append(
                    finding(
                        "条件里的列套了函数",
                        "medium",
                        func.sql(),
                        "普通 B-Tree 索引通常不能直接服务被函数包住的列。",
                        "过滤选择性高时，可能退化为扫描更多行。",
                        "候选方案是表达式索引，或把数据改成可直接比较的形式。",
                        "表达式索引会增加写入成本。",
                        "先看现有索引，再用 EXPLAIN 确认是否出现 Index Scan。",
                    )
                )
    return found


def _index_candidates(parsed, existing: list[list[str]] | None = None) -> list[dict]:
    if not isinstance(parsed, exp.Select):
        return []
    where = parsed.args.get("where")
    columns = []
    if where:
        for eq in where.find_all(exp.EQ):
            if isinstance(eq.this, exp.Column):
                columns.append(eq.this.name)
    order = parsed.args.get("order")
    order_columns = []
    if order:
        for ordered in order.find_all(exp.Ordered):
            if isinstance(ordered.this, exp.Column):
                order_columns.append(ordered.this.name)
    if not columns and not order_columns:
        return []
    ordered_unique = []
    for name in columns + order_columns:
        if name not in ordered_unique:
            ordered_unique.append(name)
    candidate = {
        "columns": ordered_unique,
        "statement": "CREATE INDEX 候选 (" + ", ".join(ordered_unique) + ")",
        "reason": "等值条件放在前面，排序列放在后面，只是候选顺序。",
        "risk": "索引增加写入和存储成本，也不能保证变快。",
        "verification": "在测试库创建后比较 EXPLAIN ANALYZE，确认仍返回相同结果。不要在生产直接创建。",
        "checked_existing": existing is not None,
    }
    if existing is not None:
        known = [tuple(name.lower() for name in columns) for columns in existing]
        if tuple(name.lower() for name in ordered_unique) in known:
            return []
    return [candidate]


def parse_explain(text: str) -> list[dict]:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return _parse_explain_json(stripped)
    return _parse_explain_text(text)


def _parse_explain_text(text: str) -> list[dict]:
    nodes = []
    current = None
    for raw in text.splitlines():
        if "(cost=" in raw:
            body = raw.strip()
            if body.startswith("->"):
                body = body[2:].strip()
            matched = NODE_RE.match(body)
            if not matched:
                current = None
                continue
            data = matched.groupdict()
            indent = len(raw) - len(raw.lstrip(" "))
            current = {
                "kind": data["kind"].strip(),
                "relation": data["relation"],
                "estimated_rows": int(data["rows"]),
                "cost_start": float(data["cost_start"]),
                "cost_end": float(data["cost_end"]),
                "actual_rows": int(data["actual_rows"]) if data["actual_rows"] is not None else None,
                "depth": indent // 2,
                "evidence": raw.strip(),
                "filter": None,
                "rows_removed": None,
            }
            nodes.append(current)
            continue
        if current is None:
            continue
        detail = raw.strip()
        removed = re.search(r"Rows Removed by Filter:\s*(\d+)", detail)
        buffers = re.search(r"shared hit=(\d+).*?read=(\d+)", detail)
        if removed:
            current["rows_removed"] = int(removed.group(1))
        elif buffers:
            current["shared_hit"] = int(buffers.group(1))
            current["shared_read"] = int(buffers.group(2))
        elif detail.startswith("Filter:"):
            current["filter"] = detail
    return nodes


def _parse_explain_json(text: str) -> list[dict]:
    if len(text) > 1_000_000:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    plans = []
    if isinstance(data, list):
        plans.extend(item.get("Plan") for item in data if isinstance(item, dict) and isinstance(item.get("Plan"), dict))
    elif isinstance(data, dict) and isinstance(data.get("Plan"), dict):
        plans.append(data["Plan"])
    nodes = []

    def walk(plan: dict, depth: int) -> None:
        if depth > 30:
            return
        removed = plan.get("Rows Removed by Filter")
        nodes.append(
            {
                "kind": str(plan.get("Node Type") or ""),
                "relation": plan.get("Relation Name"),
                "estimated_rows": int(plan.get("Plan Rows") or 0),
                "cost_start": float(plan.get("Startup Cost") or 0),
                "cost_end": float(plan.get("Total Cost") or 0),
                "actual_rows": int(plan["Actual Rows"]) if "Actual Rows" in plan else None,
                "depth": depth,
                "evidence": str(plan.get("Node Type") or ""),
                "filter": plan.get("Filter"),
                "rows_removed": int(removed) if isinstance(removed, int) else None,
            }
        )
        for child in plan.get("Plans") or []:
            if isinstance(child, dict):
                walk(child, depth + 1)

    for plan in plans:
        walk(plan, 0)
    return nodes


def _explain_findings(nodes: list[dict]) -> list[dict]:
    found = []
    for node in nodes:
        if node["kind"].startswith("Seq Scan"):
            found.append(
                finding(
                    "顺序扫描",
                    "info",
                    node["evidence"],
                    "顺序扫描本身不是错误。小表或需要读出大部分行时，它可能是合理计划。",
                    "表很大且过滤后只剩很少行时，才值得检查索引和条件。",
                    "结合过滤条件和现有索引判断，不要只因为看到 Seq Scan 就加索引。",
                    "盲目加索引可能没有收益。",
                    "看实际行数、过滤条件和现有索引后再决定。",
                )
            )
        estimate = node["estimated_rows"]
        actual = node["actual_rows"]
        hit = node.get("shared_hit")
        read = node.get("shared_read")
        if hit is not None and read is not None and read >= 100 and read > hit * 10:
            found.append(
                finding(
                    "缓存读入偏多",
                    "info",
                    node["evidence"],
                    "计划文本里的 shared read 明显高于 shared hit。这是当时的缓存现象，不是稳定的耗时结论。",
                    "冷缓存或大范围读取都会出现这种情况。",
                    "在相近负载下再取一次 EXPLAIN ANALYZE，确认不是偶发的冷启动。",
                    "不能据此直接加索引。",
                    "比较两次实际时间，不把 read 的差值写成提升比例。",
                )
            )
        removed = node.get("rows_removed")
        if removed is not None and node["actual_rows"] is not None and removed > node["actual_rows"] * 10:
            found.append(
                finding(
                    "过滤丢弃了大量行",
                    "info",
                    node.get("filter") or node["evidence"],
                    "扫描之后丢掉的行数超过保留行数的 10 倍。这是计划文本里的证据，不是已经变慢的结论。",
                    "条件选择性可能很差，或者统计信息过时。",
                    "先核对过滤条件能否更早缩小范围，再用 EXPLAIN ANALYZE 比较。",
                    "改写条件可能改变结果集。",
                    "比较改写前后的结果集和实际时间，不写提升比例。",
                )
            )
        ratio_off = False
        if actual is not None and estimate > 0:
            if actual == 0:
                ratio_off = True
            elif actual / estimate > 10 or estimate / actual > 10:
                ratio_off = True
        if ratio_off:
            found.append(
                finding(
                    "行数估算误差",
                    "medium",
                    node["evidence"],
                    "估算行数和实际行数相差超过 10 倍。",
                    "优化器可能因此选错连接或扫描方式。",
                    "先更新统计信息，再重新 EXPLAIN ANALYZE。",
                    "统计信息变化后计划可能改变，需要重新验证。",
                    "比较 ANALYZE 前后的同一条 SQL。",
                )
            )
    return found


def cost_shares(nodes: list[dict]) -> list[dict]:
    """独占成本占比来自规划器估算，不是实测耗时，也不能换成提升比例。"""
    if not nodes:
        return []
    total = max(node["cost_end"] for node in nodes)
    rows = []
    for index, node in enumerate(nodes):
        child_cost = 0.0
        for later in nodes[index + 1 :]:
            if later["depth"] <= node["depth"]:
                break
            if later["depth"] == node["depth"] + 1:
                child_cost += later["cost_end"]
        exclusive = max(0.0, node["cost_end"] - child_cost)
        rows.append({**node, "exclusive_cost": exclusive, "cost_share": (exclusive / total) if total else None})
    return rows


def _cost_findings(shares: list[dict]) -> list[dict]:
    found = []
    for node in shares:
        share = node["cost_share"]
        observed = max(node["estimated_rows"], node["actual_rows"] or 0)
        if share is None or share < 0.5 or observed < 1000:
            continue
        found.append(
            finding(
                "计划成本集中",
                "info",
                node["evidence"],
                "这个节点的独占计划成本占整棵计划的一半以上。数字来自规划器估算，不是实测耗时。",
                "读计划时可以先看这个节点，但估算成本高不等于查询已经变慢。",
                "用 EXPLAIN ANALYZE 的实际时间核对，再决定要不要改索引或 SQL。",
                "只按估算成本改索引可能没有收益。",
                "比较两次 EXPLAIN ANALYZE 的实际时间，不把估算成本差写成提升比例。",
            )
        )
    return found


def _statements(sql: str, dialect: str) -> list:
    return [item for item in sqlglot.parse(sql, read=dialect) if item is not None]


STRUCTURE_DIALECTS = {"postgres", "mysql"}


def diagnose_for_dialect(sql: str, explain: str | None, dialect: str, existing_indexes: list[list[str]] | None = None) -> dict:
    """MySQL 只做结构诊断。执行计划文本仍只按 PostgreSQL 解读。"""
    if dialect not in STRUCTURE_DIALECTS:
        return {
            "parsed": False,
            "findings": [
                finding(
                    "暂不支持的数据库",
                    "info",
                    dialect,
                    "结构规则目前覆盖 PostgreSQL 和 MySQL。其他数据库的计划不会套进同一套结论。",
                    "不会给出跨数据库的优化承诺。",
                    "使用 postgres 或 mysql。",
                    "无。",
                    "确认语句方言后再诊断。",
                )
            ],
            "index_candidates": [],
            "performance_claim": None,
        }
    plan = explain if dialect == "postgres" else None
    report = diagnose(sql, plan, dialect, existing_indexes)
    if dialect != "postgres" and explain:
        report["findings"].append(
            finding(
                "执行计划未解读",
                "info",
                dialect,
                "语句结构已按该方言解析。附带的执行计划不是 PostgreSQL 文本，因此没有套用 Seq Scan、cost 这些规则。",
                "不能把 MySQL 计划里的算子名写成 PostgreSQL 结论。",
                "需要计划结论时，改用 PostgreSQL 的 EXPLAIN 文本。",
                "无。",
                "结构类发现仍然可以对照语句本身。",
            )
        )
    return report


def diagnose(sql: str, explain: str | None = None, dialect: str = "postgres", existing_indexes: list[list[str]] | None = None) -> dict:
    try:
        statements = _statements(sql, dialect)
    except ParseError as exc:
        statements = None
    if statements is not None and len(statements) > 1:
        return {
            "parsed": False,
            "formatted": None,
            "structure": None,
            "explain_nodes": [],
            "cost_shares": [],
            "findings": [
                finding(
                    "包含多条语句",
                    "high",
                    f"{len(statements)} 条语句",
                    "一次诊断只接受一条语句，避免后面的写入被前面的查询带过去。",
                    "如果整段被执行，可能改动数据。",
                    "拆成单条语句后再诊断。",
                    "工具不会执行这段文本。",
                    "确认文本里只剩一条 SELECT。",
                )
            ],
            "index_candidates": [],
            "performance_claim": None,
        }
    try:
        parsed = sqlglot.parse_one(sql, read=dialect)
    except ParseError as exc:
        return {
            "parsed": False,
            "formatted": None,
            "structure": None,
            "explain_nodes": [],
            "findings": [
                finding(
                    "SQL 无法解析",
                    "high",
                    str(exc).splitlines()[0],
                    "解析器没有得到完整语句，后续诊断没有可靠结构。",
                    "不能在错误 SQL 上给出优化结论。",
                    "先修正语法。",
                    "无。",
                    "用数据库的语法检查确认语句。",
                )
            ],
            "index_candidates": [],
            "performance_claim": None,
        }
    structure = _structure(parsed)
    nodes = parse_explain(explain) if explain else []
    shares = cost_shares(nodes)
    return {
        "parsed": True,
        "formatted": parsed.sql(dialect=dialect, pretty=True),
        "structure": structure,
        "explain_nodes": nodes,
        "cost_shares": shares,
        "findings": _sql_findings(parsed, structure) + _explain_findings(nodes) + _cost_findings(shares),
        "index_candidates": _index_candidates(parsed, existing_indexes),
        "performance_claim": None,
    }


def compare_plans(before: list[dict], after: list[dict]) -> dict:
    """并排比较两次计划。没有实测耗时时不给出提升比例。"""
    return {
        "before_nodes": before,
        "after_nodes": after,
        "before_count": len(before),
        "after_count": len(after),
        "performance_claim": None,
    }


def explain_readonly(sql: str, connection, dialect: str = "postgres") -> str:
    """只把单条 SELECT 的 EXPLAIN 交给连接。写入语句和后续语句都不会被发送。"""
    statements = _statements(sql, dialect)
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise PermissionError("只允许对单条 SELECT 执行 EXPLAIN，不会把语句发给数据库")
    statement = "EXPLAIN " + statements[0].sql(dialect=dialect)
    return connection.execute(statement)
