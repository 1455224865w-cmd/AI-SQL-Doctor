# 路线

## 远程仓库

- 仓库：https://github.com/1455224865w-cmd/AI-SQL-Doctor
- `main` 已推送初始提交 `69237b5`。
- CI 工作流是 `.github/workflows/ci.yml`，只安装项目并运行 `pytest`。
- 首次推送的运行已成功：https://github.com/1455224865w-cmd/AI-SQL-Doctor/actions/runs/44689653062
- Milestone「0.2 下一步」跟踪下面三个 Issue：
  - #1 只读连接测试库执行 EXPLAIN
  - #2 对照现有索引后再给候选
  - #3 保存诊断历史并比较两次计划
## 已完成：0.1.0

PostgreSQL SQL 解析、EXPLAIN 文本解析、基础诊断、候选索引和诊断报告。

## 下一步

0.1.1 已完成的部分写在变更记录里。仍未完成的是需要真实数据库或仍未替换存储的部分。

1. 只读连接测试库，执行 EXPLAIN，不允许 INSERT、UPDATE、DELETE、DDL。
2. 读取现有索引后再生成候选，避免建议重复索引。
3. 保存诊断历史，并排比较两次计划。没有实际耗时就不写提升比例。

## 暂不做

自动创建索引，自动改写生产 SQL，以及一套规则覆盖所有数据库。
