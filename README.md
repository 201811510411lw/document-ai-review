# document-ai-review

企业内部 AI 文档智能审核 demo。

项目目标是把营业执照、食品证照、烟草证、QC 报告、合同等非结构化材料转为可抽取、可校验、可追溯、可人工复核的结构化审核结果，减少人工核对证照、报告和合同条款的重复工作。

## 当前功能

### 证照审核

- 支持营业执照单证审核。
- 支持食品经营许可证审核。
- 支持食品生产许可证审核。
- 支持烟草专卖零售许可证审核。
- 支持营业执照与烟草证一致性校验的用例入口和结果结构。

### QC 文档审核

- 支持商品批次报告 / 第三方检验报告等 QC 文档审核流程。
- 支持提取商品名称、供应商、批号、生产日期、签发日期、检验结论等字段。
- 支持审核结果查询和人工复核。

### 审核工作台

- 提供 Vue 前端控制台 `web-console`。
- 支持审核结果列表、详情、人工确认、异常标记等工作台能力。
- 支持企业微信登录和通知 worker 的后端接口。

### 结果保存与追溯

- 使用统一 `ReviewResult` 保存审核结果。
- 支持完整 JSON 快照保存。
- 支持按业务场景写入投影表，便于列表查询和筛选。
- 支持人工复核状态、复核人、复核意见和审计事件记录。

## 业务场景

项目来自 `docs/PRD.md` 中的三类业务场景：

| 场景 | 说明 | 当前状态 |
| --- | --- | --- |
| QC 证照及批次报告审核 | 审核营业执照、食品许可证、生产许可证、批次报告、第三方检验报告 | 已有主要 demo 流程 |
| 营业执照与烟草证一致性校验 | 比对主体名称、经营场所、负责人、有效期等字段 | 已有用例入口和结构化结果 |
| 法务合同内容审核 | 审核合同条款、识别风险、生成修改建议 | 当前偏占位，后续扩展 |

## 技术栈

后端：

- Python 3.12
- FastAPI
- Pydantic v2
- LangGraph
- LangChain
- PyMySQL
- pytest

前端：

- Vue 3
- Vite
- Pinia
- Axios
- Vant

文档和规则：

- `docs/PRD.md`：产品需求
- `docs/SPEC.md`：技术规范，包含架构、技术选型、数据模型、API、目录结构
- `docs/API.md`：API 契约
- `AGENTS.md`：Codex 项目说明
- `.agents/skills/`：业务审核规则口径

## 项目结构

```text
document-ai-review/
├── AGENTS.md
├── README.md
├── ai-service/
│   ├── app/
│   │   ├── api/
│   │   ├── capabilities/
│   │   ├── core/
│   │   ├── integrations/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── tools/
│   │   ├── use_cases/
│   │   └── workflows/
│   ├── tests/
│   └── requirements.txt
├── web-console/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
├── docs/
│   ├── PRD.md
│   ├── SPEC.md
│   └── API.md
├── .agents/
│   └── skills/
└── ci-config/
```

## 本地运行

默认 Python 环境：

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python
```

安装后端依赖：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pip install -r requirements.txt
```

启动后端：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

启动前端：

```bash
cd web-console
npm run dev
```

## 测试

运行后端测试：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest
```

当前文档结构相关测试：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest \
  tests/test_terminal_architecture_docs.py \
  tests/test_business_license_extension_boundaries.py \
  tests/test_langgraph_langchain_architecture_adr.py
```

## 配置

本地配置通过仓库根目录 `.env` 或 `ai-service/.env` 读取。

常用配置包括：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `SRM_MYSQL_*`
- `REVIEW_RESULT_MYSQL_*`
- `WEB_CONSOLE_AUTH_*`
- `WECOM_*`

不要提交 `.env`、数据库密码、API key、GitHub token、本地数据库、缓存和构建产物。

## 当前边界

- 当前 demo 不引入 Java / Spring Boot。
- LLM 可辅助抽取、解释和结构化输出，但最终合规结论应逐步收口到确定性规则。
- `contract_review` 仍偏占位，后续再补标准业务流程。
- 企业微信、SRM、OCR、LLM 能力通过配置和 adapter 接入，本地 demo 可使用测试替身或样例数据验证。

## 文档

- [docs/PRD.md](docs/PRD.md)
- [docs/SPEC.md](docs/SPEC.md)
- [docs/API.md](docs/API.md)
