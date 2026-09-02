# document-ai-review

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for `201811510411lw/document-ai-review`; use GitHub REST API instead of `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default triage labels, including `ready-for-agent` for AFK-ready work. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo. Use `README.md`, `docs/PRD.md`, `docs/SPEC.md`, `docs/API.md`, and relevant `.agents/skills/*/SKILL.md` as domain sources. See `docs/agents/domain.md`.

### Verification workflow

Routine changes use focused local verification, Jenkins image construction, and post-deployment UAT acceptance. Full local test suites are not a commit, image-build, or deployment gate. See `docs/agents/verification.md`.

### 测试阶段镜像版本约束

- 当前项目尚处于测试阶段。功能修改后的 Jenkins 构建、镜像推送和测试环境部署统一使用镜像 Tag `v1`；`IMAGE_TAG` 留空时也必须解析为 `v1`。
- 用户提到“新建 Tag”或“发布新版本”但没有明确说明 Git Tag 时，默认指镜像 Tag，并固定使用 `v1`。不要自动生成 Git SHA、构建号、时间戳或语义化版本作为镜像 Tag，也不要仅为测试部署创建 Git Tag。
- 只有用户明确宣布进入正式发布阶段，或明确指定其他镜像 Tag / Git Tag 时，才可偏离 `v1`。
- `v1` 是可变镜像 Tag，验收时必须核对本次 Jenkins 源提交、镜像仓库 digest 与运行容器 `imageID`；不能只凭 Tag 名判断新版本已经部署。必要的重新拉取或滚动更新属于部署动作，仍需按用户当次授权执行。

## 项目概述

`document-ai-review` 是企业内部 AI 文档智能审核 demo，目标是把营业执照、食品证照、烟草证、QC 报告、合同等非结构化材料转为可抽取、可校验、可追溯、可人工复核的结构化审核结果。

当前主线是 `LangGraph + LangChain` 驱动的 AI Workflow / Agent Platform。`README.md` 是项目主上下文；`docs/PRD.md` 是最初的产品需求文档。

## 技术栈

- 后端：Python + FastAPI
- 工作流：LangGraph
- LLM / 工具封装：LangChain
- 数据模型：Pydantic
- 持久化：当前 demo 含 SQLite 样例，部分代码已预留 MySQL repository
- 前端：Vue 3 + Vite + Pinia + Axios + Vant
- CI：`ci-config/` 下保存 Dockerfile / Jenkinsfile

## 项目结构

```text
document-ai-review/
├── ai-service/          # Python FastAPI 后端服务
│   ├── app/
│   │   ├── api/         # HTTP API
│   │   ├── capabilities/# LangChain tools / 结构化能力
│   │   ├── core/        # 配置、基础设施
│   │   ├── integrations/# SRM、企微等外部系统适配
│   │   ├── models/      # Pydantic / 领域模型
│   │   ├── repositories/# 持久化
│   │   ├── services/    # 应用服务
│   │   ├── tools/       # OCR、规则审核等工具适配
│   │   ├── use_cases/   # Thin Entry，用例入口
│   │   └── workflows/   # LangGraph workflow
│   ├── tests/           # 后端测试
│   └── requirements.txt
├── web-console/         # Vue 前端控制台
├── docs/
│   ├── PRD.md           # 原始需求文档
│   ├── SPEC.md          # 技术规范，包含架构、技术选型、数据模型、目录结构
│   ├── API.md           # API 契约
├── .agents/skills/      # 业务审核规则口径
├── ci-config/           # CI 配置
├── README.md            # 项目主上下文
└── AGENTS.md            # Codex 项目说明
```

## 核心架构约定

- UseCase 是 Thin Entry，只负责输入组装、必要校验、调用 workflow、返回 `ReviewResult`。
- Workflow 使用 LangGraph StateGraph 编排节点、条件路由和人工复核。
- LangChain Tool / capability 负责 OCR、视觉解析、字段抽取、字段标准化、文档分类等无状态能力。
- Agent Skill 只维护 Prompt / Policy / 规则口径，不直接执行审核流程。
- Domain Rules 承担最终合规判断、风险等级、人工复核决策和 `RuleResult` 生成。
- LLM 可以辅助抽取、解释、结构化输出，但不要让 LLM 直接成为最终合规裁判。

## 当前业务能力

已存在或占位的 use case：

- `business_license`
- `food_license`
- `food_production_license`
- `tobacco_license`
- `qc_document_review`
- `tobacco_license_consistency_review`
- `contract_review`

优先维护方向：

1. `business_license` 是第一条标准主线。
2. `food_license` / `food_production_license` 已有基础流程和规则测试。
3. `qc_document_review` 下一阶段优先打通 `product_report` 产品报告 / 第三方检验报告端到端闭环。
4. `contract_review` 当前仍偏占位，后续再补标准业务 graph。

### product_report 产品报告实现约定

- 数据源使用当前 SRM MySQL：`srm.certification t1 left join srm.attachment t2 on t1.uuid = t2.refId`。
- 首期只拉取 `t2.tenant='8560'`、`t1.category='sku'`、`t1.typeName='产品报告'`、`t1.deleted=0`、`t2.removed=0` 的记录。
- `category='sku'` 表示商品维度材料，不要复用供应商证照 source task 的语义命名；新增或维护 `product_report` 专用 source task。
- SRM `typeName='产品报告'` 统一映射为 `declared_document_type='product_report'`，由 `qc_document_review` use case 处理。
- PDF 优先走远程文件下载和 PDF 文本层抽取；文本层缺失时再走 OCR / 视觉解析 adapter。不要只依赖 `ocr_text` 或 `file.stub_text` 完成真实链路。
- 产品报告核心抽取字段包括：报告编号、样品名称/产品名称、委托单位/生产商、生产日期、签发日期/批准日期、检验结论、检验项目明细。
- 第三方检验报告有效期按 `签发日期或批准日期 + 180 天` 计算；剩余天数 `<0` 为已过期，`0..30` 为三十天内即将过期，`>30` 为未过期。
- 商品名称使用报告中的 `样品名称` / `产品名称` 与 SRM 商品名做模糊匹配；生产者名称使用 `委托单位` / `生产商` 与 SRM 供应商名称比对。
- 最终通过/不通过/人工复核仍由确定性规则和 `RuleResult` 汇总，LLM 只可辅助抽取和结构化。

## 本地命令

优先使用用户指定的 Python 环境：

```bash
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python
```

后端安装依赖：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m pip install -r requirements.txt
```

后端运行：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端完整测试（仅在显式要求全量诊断时执行）：

```bash
cd ai-service
/home/lsym005226/project/starrocks-cleanup-audit/ai-env/bin/pytest
```

日常修改不要默认执行上述全量命令。按改动范围使用快速验证：

```bash
make verify-oa-tobacco
make verify-frontend
make verify-test TESTS='tests/test_file.py::test_name'
```

完整测试仅用于用户明确要求的全量检查，或无法通过专项测试隔离的跨领域故障诊断。

前端运行：

```bash
cd web-console
npm run dev
```

前端构建：

```bash
cd web-console
npm run build
```

## 编码规范

- 先读现有代码和测试，再改实现。
- 保持改动聚焦，不做无关重构。
- 功能完成后只执行覆盖当前改动的专项测试、必要编译检查和 `git diff --check`，不要默认运行全量后端测试或重复本地生产构建。
- Jenkins 镜像构建成功后不再重复编译；部署到 UAT 后，以真实新请求完成业务验收。OA 场景必须使用新的 `workflow_id + requestid`，核对运行镜像来源、持久化结果、实际回调载荷、OA 业务接收状态和节点流转。
- `make verify-full` 仅用于用户明确要求，或专项测试无法隔离的跨领域故障诊断，不属于提交、构建和部署门禁。
- 新增业务规则时，优先同步 `.agents/skills/<skill>/SKILL.md` 和对应测试。
- 修改公共结果结构时，同时检查 API、repository、workflow projection、前端消费方和测试。
- Python 代码优先使用 Pydantic / TypedDict 等结构化模型，不用临时 dict 串业务主路径。
- 前端遵循现有 Vue 3 + Vite 结构，避免引入新 UI 框架。

## 注意事项

- 不要提交 `.env`、本地数据库、缓存、构建产物和 `node_modules/`。
- 不要把 `README.md`、`docs/SPEC.md` 中的架构约定静默改成另一套。
- 不要重新引入 Java / Spring Boot 作为当前 demo 后端。
- 本机没有安装 `gh` CLI；需要 GitHub 操作时直接使用 GitHub REST API。
