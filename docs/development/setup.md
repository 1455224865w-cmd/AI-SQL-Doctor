# 开发

```bash
pip install -e ".[dev]"
pytest
```

测试覆盖 JOIN 之外的深分页、函数包列、模糊匹配、EXPLAIN 行数误差、DELETE 和无法解析的语句。不要为了让诊断更“积极”而把 info 改成 high。
