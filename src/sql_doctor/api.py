"""提交 SQL 和可选的 EXPLAIN 文本。接口不接受数据库口令。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from sql_doctor.analyze import compare_plans, diagnose_for_dialect
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

    def recent(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, payload, created_at FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        items = []
        for row in rows:
            payload = json.loads(row["payload"])
            items.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "parsed": payload.get("parsed"),
                "finding_count": len(payload.get("findings") or []),
            })
        return items

    def get(self, report_id: str) -> dict:
        row = self.conn.execute("SELECT payload FROM reports WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise KeyError(report_id)
        return json.loads(row["payload"])


def _mount_console(app: FastAPI) -> None:
    web = Path(__file__).resolve().parent / "web"

    @app.get("/", include_in_schema=False)
    def console_page():
        return FileResponse(web / "index.html")

    app.mount("/assets", StaticFiles(directory=web), name="assets")


def create_app(db_path: str = ":memory:") -> FastAPI:
    app = FastAPI(title="AI SQL Doctor", version="0.1.9")
    install(app)
    mount(app)
    _mount_console(app)
    app.state.history = History(db_path)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/diagnose")
    def run(body: DiagnoseIn, request: Request):
        locale = negotiate(request.headers.get("accept-language"), request.query_params.get("lang"))
        report = diagnose_for_dialect(body.sql, body.explain, body.dialect, body.existing_indexes)
        if report.get("parsed") is False and report.get("findings") and report["findings"][0].get("name") == "暂不支持的数据库":
            return translate_payload(report, locale)
        report_id = app.state.history.add(report)
        return translate_payload({"id": report_id, "report": report}, locale)

    @app.get("/api/reports")
    def reports():
        return app.state.history.recent()

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
