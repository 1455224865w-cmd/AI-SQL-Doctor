# AI SQL Doctor

AI SQL Doctor 解释 SQL 可能慢在哪里。证据来自 SQL 结构和 PostgreSQL 的 EXPLAIN 文本，不是模型的感觉。

## 0.1.0 能做什么

- 用 `sqlglot` 格式化并解析 PostgreSQL 和 MySQL 语句。MySQL 只做结构诊断。不同列用 OR 连接时会单独标出来。
- 识别表、JOIN、CTE、GROUP BY、ORDER BY、LIMIT 和 OFFSET。
- 报告前导 `LIKE`、深分页、列上的 `lower`/`upper`、`SELECT *`。
- 解析 EXPLAIN 节点的估算行数和实际行数。顺序扫描只作为信息，不直接判错。
- 估算和实际行数相差超过 10 倍时给出中等严重度提示。
- 给出候选索引。候选不是性能承诺，响应里的 `performance_claim` 固定为 `null`。
- 写入语句会被标成高风险，接口不执行 SQL。

## 不做的事

- 不连接数据库，也不保存口令。
- 不把 MySQL、SQL Server 或 Oracle 的执行计划套进 PostgreSQL 规则。MySQL 若附带计划文本，会明确标成未解读。
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

## 语言和 Spring AI

默认语言是中文。请求带 `Accept-Language: en` 或 `?lang=en` 时，错误信息和工具说明返回英文。源码、SQL、日志原文不翻译。

Spring AI 不内嵌在本服务里。把 `spring-ai/pom-snippet.xml` 的 `spring-ai-starter-mcp-client` 加到 Spring AI 应用，连接配置由 `spring-ai/application-mcp.yml` 指向 Nacos，地址写在 `nacos/spring-mcp.yaml`。端点默认是 `/mcp`。本仓库的测试覆盖 MCP 的 initialize、tools/list 和 tools/call，不编译 Java。

## 配置

服务地址不写进镜像。设置 `NACOS_SERVER` 后，进程启动时读取 Nacos 中的服务配置，默认 dataId 见 `nacos/service.properties`。没有 Nacos 时使用 `APP_HOST`、`APP_PORT`、`APP_DATABASE` 和 `APP_LOCALE`。

Spring AI 的 MCP 地址放在 Nacos 的 `nacos/spring-mcp.yaml`。`spring-ai/application-mcp.yml` 只指向 Nacos，不写服务地址。

## 镜像

```bash
docker build -t ai-sql-doctor:local .
```

`main` 分支的 `.github/workflows/image.yml` 会把镜像推到 `ghcr.io/wangcheng-coder/ai-sql-doctor`。

## 页面

打开服务根路径 `/`。五个项目使用同一套版式：顶栏、左右两栏、中英文切换。页面只调用本服务已有的接口。
