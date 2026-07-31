# ai-service

`ai-service` 是 `document-ai-review` 的 Python FastAPI 服务，提供 Review Use Case HTTP 入口、LangGraph Workflow、OCR/LLM Capability、确定性 Domain Rule、结果持久化、人工复核和外部系统 adapter。

## Scope

- FastAPI 提供健康检查、认证、证照/QC 审核、OA 烟草一致性、企业微信通知和影刀验真接口。
- Thin Use Case 组装输入并调用 Workflow；Workflow 编排抽取、规则和人工复核状态。
- `ReviewResult` 统一保存结果，MySQL repository 维护业务投影、审计和通知队列。
- 当前能力状态与限制以[文档导航](../docs/README.md)和[能力矩阵](../docs/CAPABILITIES.md)为准。

## Install

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pip install -r requirements.txt
```

## Run

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

服务启动时还会尝试启动每日审核调度器；外部数据库配置失败不会阻断 API，具体准备和验证见[运维手册](../docs/OPERATIONS.md)。

## Test

本地测试不得触发真实外部 RPA。需要隔离时设置 `RPA_VERIFICATION_TOBACCO_ENABLED=false`。

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python scripts/generate_api_operation_inventory.py --check
```
