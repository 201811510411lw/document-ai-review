# 架构设计

## 服务边界

- backend-java：对外接口、MySQL 查询、审核任务、结果落库。
- ai-service：证照解析、字段抽取、规则校验、风险报告。

## V1 流程

```text
Java 接收 license_id
  ↓
Java 查询 MySQL 证照表
  ↓
Java 调用 Python AI 服务
  ↓
Python 执行食品安全证照检测 Skill
  ↓
Python 返回风险项和审核结论
  ↓
Java 保存结果并进入人工复核
```

## 扩展方向

后续通过新增 Skill 扩展合同审核、QC 报告校验、烟草证与营业执照一致性校验。
