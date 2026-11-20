# AI SQL Doctor

AI SQL Doctor 解释 SQL 可能慢在哪里。证据来自 SQL 结构和 PostgreSQL 的 EXPLAIN 文本，不是模型的感觉。

## 0.1.0 能做什么

- 用 `sqlglot` 格式化并解析 PostgreSQL 语句。
- 识别表、JOIN、CTE、GROUP BY、ORDER BY、LIMIT 和 OFFSET。
- 报告前导 `LIKE`、深分页、列上的 `lower`/`upper`、`SELECT *`。
- 解析 EXPLAIN 节点的估算行数和实际行数。顺序扫描只作为信息，不直接判错。
- 估算和实际行数相差超过 10 倍时给出中等严重度提示。
- 给出候选索引。候选不是性能承诺，响应里的 `performance_claim` 固定为 `null`。
- 写入语句会被标成高风险，接口不执行 SQL。

## 不做的事

- 不连接数据库，也不保存口令。
- 不支持把 MySQL、SQL Server 或 Oracle 的计划套进 PostgreSQL 规则。
- 不自动创建索引。

## 本地运行

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn sql_doctor.api:app --reload
```

`POST /api/diagnose`，正文是 `sql` 和可选的 `explain`。

## 许可证

Apache-2.0。
