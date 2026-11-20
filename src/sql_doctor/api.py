"""提交 SQL 和可选的 EXPLAIN 文本。接口不接受数据库口令。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from sql_doctor.analyze import compare_plans, diagnose
from sql_doctor.i18n import install, negotiate, translate_payload
from sql_doctor.mcp_server import mount


class DiagnoseIn(BaseModel):
    sql: str
    explain: str | None = None
    dialect: str = "postgres"
    existing_indexes: list[list[str]] | None = None


class History:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
              id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def add(self, report: dict) -> str:
        report_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO reports VALUES (?, ?, ?)",
            (report_id, json.dumps(report, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        return report_id

    def get(self, report_id: str) -> dict:
        row = self.conn.execute("SELECT payload FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise KeyError(report_id)
        return json.loads(row["payload"])


def create_app(db_path: str = ":memory:") -> FastAPI:
    app = FastAPI(title="AI SQL Doctor", version="0.1.6")
    install(app)
    mount(app)
    app.state.history = History(db_path)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/diagnose")
    def run(body: DiagnoseIn, request: Request):
        locale = negotiate(request.headers.get("accept-language"), request.query_params.get("lang"))
        if body.dialect != "postgres":
            return translate_payload({
                "parsed": False,
                "findings": [
                    {
                        "name": "暂不支持的数据库",
                        "severity": "info",
                        "evidence": body.dialect,
                        "reason": "MVP 只实现 PostgreSQL 规则，避免把其他数据库的计划误判成同一套结论。",
                        "impact": "不会给出跨数据库的优化承诺。",
                        "direction": "使用 postgres。",
                        "risk": "无。",
                        "verification": "确认 EXPLAIN 来自 PostgreSQL。",
                    }
                ],
                "index_candidates": [],
                "performance_claim": None,
            }, locale)
        report = diagnose(body.sql, body.explain, body.dialect, body.existing_indexes)
        report_id = app.state.history.add(report)
        return translate_payload({"id": report_id, "report": report}, locale)

    @app.get("/api/reports/{left_id}/compare/{right_id}")
    def compare(left_id: str, right_id: str):
        try:
            left = app.state.history.get(left_id)
            right = app.state.history.get(right_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="诊断记录不存在") from exc
        return compare_plans(left.get("explain_nodes") or [], right.get("explain_nodes") or [])

    return app


app = create_app("sql-doctor.sqlite3")
