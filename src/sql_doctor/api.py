"""提交 SQL 和可选的 EXPLAIN 文本。接口不接受数据库口令。"""

from fastapi import FastAPI
from pydantic import BaseModel

from sql_doctor.analyze import diagnose


class DiagnoseIn(BaseModel):
    sql: str
    explain: str | None = None
    dialect: str = "postgres"


def create_app() -> FastAPI:
    app = FastAPI(title="AI SQL Doctor", version="0.1.0")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/diagnose")
    def run(body: DiagnoseIn):
        if body.dialect != "postgres":
            return {
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
            }
        return diagnose(body.sql, body.explain, body.dialect)

    return app


app = create_app()
