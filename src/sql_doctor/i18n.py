"""中英文切换。默认中文，已有调用不传语言时行为不变。"""

from __future__ import annotations

import re
from contextvars import ContextVar

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

current_locale: ContextVar[str] = ContextVar("locale", default="zh")
LOCALES = ("zh", "en")
TEXT_FIELDS = {
    "name", "summary", "message", "detail", "reason", "impact", "direction",
    "risk", "verification", "answer", "error", "prompt",
}

def negotiate(header: str | None, query: str | None = None) -> str:
    if query in LOCALES:
        return query
    if not header:
        return "zh"
    for part in header.split(","):
        token = part.split(";", 1)[0].strip().lower().replace("_", "-")
        if token.startswith("en"):
            return "en"
        if token.startswith("zh"):
            return "zh"
    return "zh"


def localize_error(message: str, locale: str) -> str:
    if locale != "en":
        return message
    if message in EN:
        return EN[message]
    for pattern, template in PATTERNS:
        matched = pattern.fullmatch(message)
        if matched:
            return template.format(*matched.groups())
    return message


def text(key: str, locale: str) -> str:
    table = TEXT.get(locale) or TEXT["zh"]
    return table.get(key) or TEXT["zh"][key]


def translate_payload(value, locale: str):
    if locale != "en":
        return value
    if isinstance(value, dict):
        translated = {}
        for key, item in value.items():
            if key == "suggestions" and isinstance(item, list):
                translated[key] = [
                    localize_error(piece, "en") if isinstance(piece, str) else translate_payload(piece, "en")
                    for piece in item
                ]
            elif key in TEXT_FIELDS and isinstance(item, str):
                translated[key] = localize_error(item, "en")
            else:
                translated[key] = translate_payload(item, "en")
        return translated
    if isinstance(value, list):
        return [translate_payload(item, "en") for item in value]
    return value


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def bind_locale(request: Request, call_next):
        token = current_locale.set(negotiate(request.headers.get("accept-language"), request.query_params.get("lang")))
        try:
            return await call_next(request)
        finally:
            current_locale.reset(token)

    @app.exception_handler(HTTPException)
    async def translate_http(request: Request, exc: HTTPException):
        locale = negotiate(request.headers.get("accept-language"), request.query_params.get("lang"))
        detail = exc.detail
        if isinstance(detail, str):
            detail = localize_error(detail, locale)
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.get("/api/meta")
    def meta(request: Request):
        locale = negotiate(request.headers.get("accept-language"), request.query_params.get("lang"))
        return {
            "locale": locale,
            "locales": list(LOCALES),
            "mcp": "/mcp",
            "springAi": "streamable-http",
            "message": text("meta.ready", locale),
        }


EN = {
    "未知工具": "Unknown tool",
    "SQL 不能为空": "SQL is required",
    "SQL 超过长度限制": "SQL exceeds the length limit",
    "诊断记录不存在": "Diagnosis record does not exist",
    "只允许对单条 SELECT 执行 EXPLAIN，不会把语句发给数据库": "EXPLAIN is allowed only for a single SELECT and the statement is not sent",
    "非只读语句": "Not a read-only statement",
    "查询返回全部列": "Query returns every column",
    "前导模糊匹配": "Leading wildcard match",
    "深分页": "Deep pagination",
    "连接没有条件": "Join has no condition",
    "条件里的列套了函数": "A column is wrapped in a function",
    "顺序扫描": "Sequential scan",
    "缓存读入偏多": "Shared reads are high",
    "过滤丢弃了大量行": "The filter discarded many rows",
    "行数估算误差": "Row estimate is far from actual rows",
    "计划成本集中": "Planner cost is concentrated",
    "包含多条语句": "Multiple statements",
    "SQL 无法解析": "SQL could not be parsed",
    "暂不支持的数据库": "Unsupported database",
    "无。": "None.",
    "MVP 只分析语句，不执行它。写入语句默认被拒绝。": "The statement is analyzed and not executed. Writes are rejected by default.",
    "如果误执行，会改动数据或结构。": "Executing it by mistake would change data or schema.",
    "先改成只读的 EXPLAIN，或在独立环境由人确认后再执行。": "Use a read-only EXPLAIN, or have a person confirm it in an isolated environment.",
    "工具不会自动执行这条语句。": "The tool does not execute this statement.",
    "确认连接账号没有写入权限。": "Confirm that the database account cannot write.",
    "顺序扫描本身不是错误。小表或需要读出大部分行时，它可能是合理计划。": "A sequential scan is not an error. It can be reasonable for a small table or when most rows are needed.",
    "表很大且过滤后只剩很少行时，才值得检查索引和条件。": "Check indexes and filters when the table is large and the filter leaves few rows.",
    "结合过滤条件和现有索引判断，不要只因为看到 Seq Scan 就加索引。": "Judge the filter and existing indexes; do not add an index only because the plan says Seq Scan.",
    "盲目加索引可能没有收益。": "Adding an index blindly may not help.",
    "看实际行数、过滤条件和现有索引后再决定。": "Decide after looking at actual rows, filters, and existing indexes.",
    "一次诊断只接受一条语句，避免后面的写入被前面的查询带过去。": "One diagnosis accepts one statement so a later write is not carried along by an earlier query.",
    "如果整段被执行，可能改动数据。": "Executing the whole text could change data.",
    "拆成单条语句后再诊断。": "Split it into one statement before diagnosing it.",
    "工具不会执行这段文本。": "The tool does not execute this text.",
    "确认文本里只剩一条 SELECT。": "Confirm that only one SELECT remains.",
    "这个连接没有 ON 或 USING。它会按交叉连接解释，有时是有意写的。": "This join has no ON or USING. It is interpreted as a cross join, which is sometimes intentional.",
    "两边行数都大时，结果集会迅速变大。": "When both sides have many rows, the result grows quickly.",
    "如果本意是等值连接，补上连接条件后再比较结果。": "If an equijoin was intended, add the condition and compare the results.",
    "补错条件会改变结果集。": "A wrong condition changes the result.",
    "核对连接键，并用同一批数据比较行数。不写提升比例。": "Check the join keys and compare row counts on the same data. Do not state a speedup.",
    "调用方如果只需要少数列，会多读数据。是否多余取决于业务。": "Selecting every column reads extra data when the caller needs only a few. Whether that matters depends on the caller.",
    "列很多或含大字段时，I/O 会升高。": "I/O increases when there are many columns or large values.",
    "候选改写是列出实际使用的列。": "A candidate rewrite lists only the columns that are used.",
    "漏列会改变结果，不能直接替换生产 SQL。": "Omitting a column changes the result, so this cannot replace production SQL directly.",
    "对照调用方使用的字段后，再用 EXPLAIN 比较。": "Compare EXPLAIN after checking the columns the caller uses.",
    "以 % 开头的 LIKE 通常用不上普通 B-Tree 索引。": "A LIKE pattern that starts with % usually cannot use an ordinary B-tree index.",
    "表变大后，这个条件可能变成大范围扫描。": "As the table grows, this predicate can scan a large range.",
    "候选方案是改写匹配方式，或评估专门的文本索引。": "A candidate is to change the match or evaluate a text search index.",
    "改写可能改变匹配结果。": "A rewrite can change which rows match.",
    "用同一批参数比较原 SQL 和候选 SQL 的结果集。": "Compare the original and candidate results with the same parameters.",
    "大 OFFSET 仍要扫描并丢弃前面的行。": "A large OFFSET still scans and discards earlier rows.",
    "页码越往后越慢。": "Later pages get slower.",
    "候选方案是用上一页的排序键做范围查询。": "A candidate is to page with the previous sort key.",
    "结果顺序和缺页行为可能变化。": "Order and missing-row behavior can change.",
    "在相近数据量上比较两版 EXPLAIN ANALYZE，并核对结果集。": "Compare EXPLAIN ANALYZE and the result sets on a similar amount of data.",
    "普通 B-Tree 索引通常不能直接服务被函数包住的列。": "An ordinary B-tree index usually cannot serve a column wrapped in a function.",
    "过滤选择性高时，可能退化为扫描更多行。": "A selective filter may still scan more rows.",
    "候选方案是表达式索引，或把数据改成可直接比较的形式。": "A candidate is an expression index, or storing the value in a directly comparable form.",
    "表达式索引会增加写入成本。": "An expression index adds write cost.",
    "先看现有索引，再用 EXPLAIN 确认是否出现 Index Scan。": "Check existing indexes, then use EXPLAIN to see whether an Index Scan appears.",
    "估算行数和实际行数相差超过 10 倍。": "Estimated rows and actual rows differ by more than ten times.",
    "优化器可能因此选错连接或扫描方式。": "The planner may choose the wrong join or scan because of that.",
    "先更新统计信息，再重新 EXPLAIN ANALYZE。": "Update statistics, then run EXPLAIN ANALYZE again.",
    "统计信息变化后计划可能改变，需要重新验证。": "The plan can change after statistics change and must be checked again.",
    "比较 ANALYZE 前后的同一条 SQL。": "Compare the same SQL before and after ANALYZE.",
    "计划文本里的 shared read 明显高于 shared hit。这是当时的缓存现象，不是稳定的耗时结论。": "shared read is much higher than shared hit in the plan text. That is a cache observation, not a stable timing conclusion.",
    "冷缓存或大范围读取都会出现这种情况。": "A cold cache or a large read can both look like this.",
    "在相近负载下再取一次 EXPLAIN ANALYZE，确认不是偶发的冷启动。": "Take another EXPLAIN ANALYZE under a similar load to see whether this was a cold start.",
    "不能据此直接加索引。": "Do not add an index from this observation alone.",
    "比较两次实际时间，不把 read 的差值写成提升比例。": "Compare the two actual times. Do not turn the difference in reads into a speedup.",
    "扫描之后丢掉的行数超过保留行数的 10 倍。这是计划文本里的证据，不是已经变慢的结论。": "Rows removed after the scan exceed the kept rows by more than ten times. This is evidence in the plan, not a conclusion that it is slow.",
    "条件选择性可能很差，或者统计信息过时。": "The predicate may not be selective, or the statistics may be stale.",
    "先核对过滤条件能否更早缩小范围，再用 EXPLAIN ANALYZE 比较。": "Check whether the filter can reduce rows earlier, then compare EXPLAIN ANALYZE.",
    "改写条件可能改变结果集。": "Changing the predicate can change the result.",
    "比较改写前后的结果集和实际时间，不写提升比例。": "Compare result sets and actual time. Do not state a speedup.",
    "这个节点的独占计划成本占整棵计划的一半以上。数字来自规划器估算，不是实测耗时。": "This node's exclusive planner cost is more than half of the plan. The number is an estimate, not measured time.",
    "读计划时可以先看这个节点，但估算成本高不等于查询已经变慢。": "Read this node first, but a high estimate does not mean the query is slow.",
    "用 EXPLAIN ANALYZE 的实际时间核对，再决定要不要改索引或 SQL。": "Check actual time with EXPLAIN ANALYZE before changing an index or the SQL.",
    "只按估算成本改索引可能没有收益。": "Changing an index from estimated cost alone may not help.",
    "比较两次 EXPLAIN ANALYZE 的实际时间，不把估算成本差写成提升比例。": "Compare actual time from two EXPLAIN ANALYZE runs. Do not turn the estimate gap into a speedup.",
    "解析器没有得到完整语句，后续诊断没有可靠结构。": "The parser did not get a complete statement, so later diagnosis has no reliable structure.",
    "不能在错误 SQL 上给出优化结论。": "Do not draw an optimization conclusion from invalid SQL.",
    "先修正语法。": "Fix the syntax first.",
    "用数据库的语法检查确认语句。": "Check the statement with the database parser.",
    "MVP 只实现 PostgreSQL 规则，避免把其他数据库的计划误判成同一套结论。": "Only PostgreSQL rules are implemented, so another database's plan is not judged with the same conclusions.",
    "不会给出跨数据库的优化承诺。": "No cross-database optimization promise is made.",
    "使用 postgres。": "Use postgres.",
    "确认 EXPLAIN 来自 PostgreSQL。": "Confirm that the EXPLAIN output comes from PostgreSQL.",
    "等值条件放在前面，排序列放在后面，只是候选顺序。": "Equality columns come before sort columns. This is only a candidate order.",
    "索引增加写入和存储成本，也不能保证变快。": "An index adds write and storage cost and does not guarantee a speedup.",
    "在测试库创建后比较 EXPLAIN ANALYZE，确认仍返回相同结果。不要在生产直接创建。": "Create it on a test database, compare EXPLAIN ANALYZE, and confirm the same result. Do not create it directly in production.",
    "诊断不会给出变快比例。": "The diagnosis does not state a speedup.",
}

PATTERNS = []

TEXT = {
    "zh": {
        "meta.ready": "当前语言是中文。MCP 端点是 /mcp，供 Spring AI Streamable HTTP 客户端连接。",
        "mcp.instructions": "工具只读或只记录，不执行日志命令，不连接生产数据库，也不把推测写成事实。",
        "mcp.invalid": "请求无效",
        "mcp.protocol": "不支持的 MCP 协议版本",
        "mcp.arguments": "工具参数必须是对象",
        "mcp.json": "请求不是 JSON",
        "mcp.method": "不支持的 MCP 方法",
        "tool.sql": "诊断一条 PostgreSQL 语句和可选的 EXPLAIN 文本。不连接数据库，也不写变快比例。",
        "tool.sql.result": "诊断不会给出变快比例。",
    },
    "en": {
        "meta.ready": "The current language is English. The MCP endpoint is /mcp for a Spring AI Streamable HTTP client.",
        "mcp.instructions": "Tools only read or record. They do not run log commands, connect to production databases, or treat inferences as facts.",
        "mcp.invalid": "Invalid request",
        "mcp.protocol": "Unsupported MCP protocol version",
        "mcp.arguments": "Tool arguments must be an object",
        "mcp.json": "Request is not JSON",
        "mcp.method": "Unsupported MCP method",
        "tool.sql": "Diagnose one PostgreSQL statement and optional EXPLAIN text. It does not connect to a database or state a speedup.",
        "tool.sql.result": "The diagnosis does not state a speedup.",
    },
}
