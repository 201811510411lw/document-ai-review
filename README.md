# document-ai-review

企业内部 AI 文档智能审核系统，当前 V1 聚焦 **食品安全证照检测**。

本项目不是单纯 OCR 工具，而是面向企业内部审核场景的 **Document AI Review Agent / Skill 平台**。OCR 只是底层读取能力，核心目标是把证照、报告、合同等非结构化文件转为可校验、可追溯、可复核的结构化审核结果。

`README.md` 是本项目唯一主上下文。当前不使用 `CONTEXT.md` / `CONTEXT-MAP.md`，也不要求创建 `AGENTS.md` / `CLAUDE.md`。

---

## 1. 项目定位

`document-ai-review` 用于建设企业内部文档智能审核能力，解决证照、资质、报告、合同等材料审核过程中存在的效率、准确性、协同和审计问题。

核心目标：

- 提升企业内部文档审核效率；
- 实现证照、报告、合同等材料的自动化抽取和规则校验；
- 将非结构化文件转为结构化审核数据；
- 将人工经验沉淀为可配置的审核规则和 Skill；
- 将审核过程、审核依据、审核结果完整留痕；
- 支持企业内部私有化部署，避免敏感材料直接上传公有云模型。

当前 V1 不优先做合同审核，也不拆分 Java / Python 双服务，而是先用纯 Python 架构聚焦 **食品安全证照检测**，把证照审核链路跑通，再扩展到 QC 证照校验、烟草证一致性校验、法务合同审核等场景。

---

## 2. 当前 V1 范围

### 2.1 V1 目标

当前阶段优先实现：

```text
食品安全证照检测
```

V1 主要解决：

- 供应商是否上传了食品安全相关证照；
- 证照图片、PDF、文件路径或 OCR 文本是否可以被正常处理；
- 证照类型是否可以识别为食品安全相关证照；
- 证照中的关键字段是否可以被结构化抽取；
- 抽取字段是否可以被规范化为稳定的数据结构；
- 证照是否过期；
- 证照主体名称是否与业务系统供应商名称一致；
- 统一社会信用代码是否一致；
- 经营项目是否覆盖食品销售、预包装食品、散装食品等业务范围；
- 审核任务、审核结果、规则结果、人工复核和审计日志是否可以沉淀为可追溯、可复核的结构化数据。

### 2.2 输入来源

V1 先支持本地最小闭环，输入可以来自：

- 上传的食品安全证照图片或 PDF；
- 已存在的证照图片或 PDF 文件路径；
- 外部系统或测试脚本传入的 OCR 文本；
- 供应商名称；
- 统一社会信用代码；
- 供应商经营地址；
- 证照类型或待识别证照类型。

V1 可以先使用 SQLite 或 MySQL 保存数据，优先保证本地可运行、可验证、可复核。

后续可以扩展为：

- ERP 系统；
- OA 系统；
- 文件服务器；
- 对象存储；
- 第三方验真平台；
- 内部主数据平台；
- 其他业务系统通过 HTTP API 调用 Python 服务。

---

## 3. V1 技术栈

V1 采用纯 Python 架构：

- Python；
- FastAPI；
- LangGraph；
- LangChain；
- Pydantic；
- SQLite / MySQL。

Java / Spring Boot 不是 V1 范围。后续如果需要接入企业业务系统，可以让 Java、ERP、OA 或其他业务系统通过 HTTP API 调用当前 Python 服务。

---

## 4. 系统架构

### 4.1 总体架构

```text
业务系统 / 管理后台 / 测试脚本
    ↓
FastAPI HTTP API
    ↓
Review Service
    ↓
Skill Registry
    ↓
food_license Skill.review(input_context)
    ↓
LangGraph 食品安全证照检测工作流
    ↓
LangChain 字段抽取 / Python 规则引擎 / 人工复核决策
    ↓
ReviewResult
    ↓
SQLite / MySQL 保存任务、结果、规则结果、人工复核、审计日志
```

V1 不再采用 `backend-java` + `ai-service` 的双服务架构。当前只有一个 Python 服务：`ai-service`。

Skill 是平台运行时的一等业务对象，也是配置、Prompt、规则、模型、工作流和文档的组织边界。平台只通过稳定 Skill 接口调用审核能力，核心调用形式为：

```text
Skill.review(input_context) -> ReviewResult
```

`food_license` 是 V1 的第一个内置 Skill。所有入口都必须通过 Review Service + Skill Registry 路由到具体 Skill，不能由 API 层直接调用 `extract_fields`、`run_rules`、`summarize_risk` 或 `route_review` 等 Skill 内部节点。

### 4.2 服务边界

| 模块 | 职责 |
| --- | --- |
| FastAPI | 对外暴露 HTTP API，包括健康检查、创建审核任务、查询审核结果、人工复核 |
| Review Service | 创建审核任务，依赖 Skill Registry 路由并执行 Skill，保存 ReviewResult，协调人工复核和审计日志 |
| Skill Registry | Skill 平台层入口，显式注册内置 Skill，加载并校验 `metadata.yaml`，提供 `get` / `list` 能力 |
| Skill | 一等业务能力单元，封装配置、Prompt、规则、模型、工作流、节点和 Skill 文档 |
| LangGraph | 在 Skill 内部编排审核工作流和节点状态流转 |
| LangChain | 在 Skill 内部负责模型调用、Prompt、结构化输出、工具封装 |
| Python 规则引擎 | 执行确定性规则校验，输出规则结果和风险等级；通用基础设施放在 `app/rules/` |
| Pydantic models | 定义审核请求、证照字段、规则结果、审核结果等结构化数据 |
| Repository / Service 层 | 管理审核任务、审核结果保存、人工复核、审计日志 |
| SQLite / MySQL | 保存审核任务、审核结果、规则结果、人工复核记录和审计日志 |

更详细的纯 Python V1 架构说明见 [docs/v1-python-architecture.md](docs/v1-python-architecture.md)。
Skill 架构边界见 [docs/skill-architecture.md](docs/skill-architecture.md)。

---

## 5. V1 最小闭环

```text
上传食品安全证照文件，或传入文件路径 / OCR 文本
    ↓
FastAPI 创建审核任务
    ↓
Review Service 调用 Skill Registry
    ↓
Registry 路由到 food_license Skill
    ↓
food_license Skill.review(input_context)
    ↓
LangGraph 执行 Skill 内部审核工作流
    ↓
文档加载节点
    ↓
证照类型识别节点
    ↓
字段抽取节点
    ↓
字段规范化节点
    ↓
规则校验节点
    ↓
风险汇总节点
    ↓
人工复核路由节点
    ↓
保存审核任务、审核结果、规则结果、审计日志
    ↓
返回结构化审核结果
```

### 5.1 详细流程说明

1. 用户、测试脚本或外部系统通过 FastAPI 发起食品安全证照审核；
2. 请求可以上传证照文件，也可以传入文件路径或 OCR 文本；
3. FastAPI 创建审核任务，并通过 Service / Repository 层保存任务初始状态；
4. Review Service 调用 Skill Registry；
5. Skill Registry 根据快捷入口、声明文档类型和输入上下文选择 `food_license` Skill；
6. `food_license.review(input_context)` 启动 Skill 内部 LangGraph 审核工作流；
7. 文档加载节点读取图片、PDF、文件路径或 OCR 文本；
8. 证照类型识别节点判断材料是否属于食品安全相关证照；
9. 字段抽取节点通过 LangChain 调用模型、Prompt 和结构化输出能力；
10. 字段规范化节点清洗日期、主体名称、统一社会信用代码、经营项目等字段；
11. 规则校验节点调用 Python 规则引擎执行 `food_license` Skill 内部规则；
12. 风险汇总节点根据规则结果生成总体风险等级和审核建议；
13. 人工复核路由节点判断是否需要进入人工复核；
14. Service / Repository 层保存审核结果、规则结果、人工复核状态和审计日志；
15. FastAPI 返回结构化审核结果。

---

## 6. 推荐目录结构

项目采用以 `ai-service` 为核心的纯 Python 结构：

```text
document-ai-review/
├── ai-service/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── health.py
│   │   │   ├── review.py
│   │   │   └── manual_review.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── errors.py
│   │   ├── rules/
│   │   │   ├── engine.py
│   │   │   ├── protocol.py
│   │   │   └── result.py
│   │   ├── models/
│   │   │   ├── review.py
│   │   │   └── rule.py
│   │   ├── repositories/
│   │   │   ├── review_task_repository.py
│   │   │   └── audit_log_repository.py
│   │   ├── services/
│   │   │   ├── review_service.py
│   │   │   └── manual_review_service.py
│   │   └── skills/
│   │       ├── base.py
│   │       ├── registry.py
│   │       └── food_license/
│   │           ├── skill.py
│   │           ├── metadata.yaml
│   │           ├── README.md
│   │           ├── models.py
│   │           ├── prompts/
│   │           ├── chains/
│   │           ├── graphs/
│   │           ├── nodes/
│   │           ├── review_policy.py
│   │           └── rules/
│   │               ├── rules.yaml
│   │               └── rule_defs.py
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── docs/
│   ├── agents/
│   ├── prd-food-license-v1.md
│   ├── api-food-license-v1.md
│   ├── skill-architecture.md
│   └── v1-python-architecture.md
├── scripts/
│   └── init_db.sql
├── docker-compose.yml
├── README.md
└── .env.example
```

`app/skills/base.py` 是 Skill 基础接口 / 协议，定义平台可依赖的 Skill 级契约。`app/skills/registry.py` 是显式注册内置 Skill、加载并校验 `metadata.yaml`、提供 `get` / `list` 的入口。Review Service 依赖 Skill Registry，但 Registry 本身属于 Skill 平台层，不放在 `app/services/` 下。

`app/rules/` 只放通用规则基础设施，不放食品安全证照业务规则。`FOOD_LICENSE_EXPIRED`、`CREDIT_CODE_MATCH` 等具体规则和 `rules.yaml` 放在 `app/skills/food_license/rules/` 内。

`metadata.yaml` 是 Skill 运行时 manifest，是 `name`、`version`、`supported_document_types`、`input_modes` 和 `ruleset_version` 等元信息的权威来源。V1 Skill Registry 使用显式内置注册，不做目录扫描、外部 Skill 加载、插件市场、热加载或租户级覆盖。

---

## 7. 食品安全证照 LangGraph 节点

V1 食品安全证照检测工作流建议由以下节点组成：

| 节点 | 职责 |
| --- | --- |
| `load_document` | 加载上传文件、文件路径或 OCR 文本，生成统一文档输入 |
| `classify_document` | 判断材料是否为食品安全相关证照 |
| `extract_fields` | 使用 LangChain、Prompt 和结构化输出抽取证照字段 |
| `normalize_fields` | 规范化日期、主体名称、统一社会信用代码、经营项目等字段 |
| `run_rules` | 调用 Python 规则引擎执行食品安全证照规则 |
| `summarize_risk` | 汇总规则结果，生成总体风险等级和审核建议 |
| `route_review` | 判断是否自动通过、自动驳回或进入人工复核 |

---

## 8. 食品安全证照字段抽取

V1 建议抽取以下字段：

| 字段 | 说明 |
| --- | --- |
| `subject_name` | 主体名称 |
| `credit_code` | 统一社会信用代码 |
| `license_no` | 许可证编号 |
| `business_address` | 经营场所 |
| `legal_person` | 法定代表人 / 负责人 |
| `business_items` | 经营项目 |
| `valid_from` | 有效期开始日期 |
| `valid_to` | 有效期截止日期 |
| `issue_authority` | 发证机关 |
| `issue_date` | 发证日期 |

示例结构：

```json
{
  "subject_name": "成都示例食品有限公司",
  "credit_code": "91510100MA00000000",
  "license_no": "JY15101000000000",
  "business_address": "成都市示例区示例路 100 号",
  "legal_person": "张三",
  "business_items": ["预包装食品销售", "散装食品销售"],
  "valid_from": "2023-01-01",
  "valid_to": "2028-01-01",
  "issue_authority": "成都市市场监督管理局",
  "issue_date": "2023-01-01"
}
```

---

## 9. 食品安全证照规则示例

V1 建议先实现以下规则：

| 规则编码 | 规则名称 | 风险等级 | 说明 |
| --- | --- | --- | --- |
| `FOOD_LICENSE_EXISTS` | 证照是否存在 | 高 | 未上传证照、文件路径为空或 OCR 文本为空 |
| `FOOD_LICENSE_NO_REQUIRED` | 许可证编号是否为空 | 高 | 食品经营许可证编号不能为空 |
| `FOOD_LICENSE_EXPIRED` | 证照是否过期 | 高 | 当前日期超过证照有效期截止日期 |
| `SUBJECT_NAME_MATCH` | 主体名称是否一致 | 中 | 证照主体名称与供应商名称不一致 |
| `CREDIT_CODE_MATCH` | 统一社会信用代码是否一致 | 高 | 证照信用代码与业务系统信用代码不一致 |
| `BUSINESS_SCOPE_COVERED` | 经营项目是否覆盖食品业务 | 中 | 经营项目不包含食品销售相关范围 |
| `ADDRESS_SIMILARITY` | 经营场所是否近似匹配 | 低 | 证照地址与业务系统地址相似度较低 |

规则配置示例：

```yaml
ruleset_version: food-license-rules-v1
rules:
  - code: FOOD_LICENSE_EXISTS
    name: 证照是否存在
    risk_level: HIGH
    enabled: true

  - code: FOOD_LICENSE_EXPIRED
    name: 证照是否过期
    risk_level: HIGH
    enabled: true

  - code: SUBJECT_NAME_MATCH
    name: 主体名称是否一致
    risk_level: MEDIUM
    enabled: true
    params:
      similarity_threshold: 0.85
```

---

## 10. 审核结果设计

Python 服务返回的审核结果建议包含：

```json
{
  "task_id": "review-task-001",
  "document_type": "food_license",
  "skill_name": "food_license",
  "skill_version": "v1",
  "ruleset_version": "food-license-rules-v1",
  "status": "REVIEWED",
  "risk_level": "HIGH",
  "needs_manual_review": true,
  "rule_results": [
    {
      "rule_code": "SUBJECT_NAME_MATCH",
      "rule_name": "主体名称是否一致",
      "passed": false,
      "risk_level_on_failure": "MEDIUM",
      "message": "证照主体名称与业务系统供应商名称不一致"
    }
  ],
  "manual_review": {
    "status": "PENDING",
    "reasons": ["证照主体名称与业务系统供应商名称不一致"]
  },
  "summary": "发现 1 项中风险问题，建议人工复核供应商主体名称。",
  "skill_result": {
    "extracted_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "valid_to": "2028-01-01"
    },
    "normalized_fields": {
      "subject_name": "成都示例食品有限公司",
      "credit_code": "91510100MA00000000",
      "license_no": "JY15101000000000",
      "valid_to": "2028-01-01"
    }
  }
}
```

`ReviewResult` 是平台级契约；`skill_result` 承载 Skill 专属 payload。食品安全证照的 `extracted_fields`、`normalized_fields` 等字段应放在 `skill_result` 内，避免把 `food_license` 专属结构固化为所有 Skill 的顶层字段。

人工复核基础设施属于平台，包括状态、动作、记录保存和审计日志；是否需要人工复核、初始复核状态和复核原因由 Skill 根据规则结果和审核策略决定。

---

## 11. 数据保存范围

V1 至少保存以下数据：

- 审核任务：任务 ID、输入来源、供应商信息、任务状态、创建时间、更新时间；
- 审核结果：文档类型、总体风险等级、审核建议、是否需要人工复核；
- 字段抽取结果：食品安全证照结构化字段；
- 规则结果：规则编码、规则名称、是否通过、风险等级、提示信息；
- 人工复核记录：复核动作、复核人、复核备注、复核时间；
- 审计日志：任务创建、工作流执行、规则校验、人工复核等关键事件。

---

## 12. Skill 扩展方向

后续可以在当前 Skill 框架上扩展：

- QC 证照校验；
- 营业执照与烟草证一致性校验；
- 法务合同自动审核；
- ERP / OA 文件自动拉取；
- 资质报告审核；
- 供应商准入材料审核；
- 其他企业内部文档智能审核 Skill。

扩展方式：

```text
新增 Skill 纵向包
    ↓
新增 metadata.yaml
    ↓
实现 Skill.review(input_context)
    ↓
在 Skill 内部组织 LangGraph、Prompt、Chain、规则和模型
    ↓
显式注册到 Skill Registry
    ↓
复用任务管理、结果保存、审计日志和人工复核基础设施
```

V1 食品安全证照快捷入口为 `/api/v1/food-license/reviews`，它是 `food_license` 的便捷 API；后续平台通用入口为 `/api/v1/reviews`。两个入口都必须走同一套 Review Service + Skill Registry，不维护两套审核逻辑。

---

## 13. V1 不做事项

V1 暂不实现：

- Java / Spring Boot 服务；
- 独立业务后台；
- 完整权限系统；
- 企业微信、邮件、OA 待办等通知渠道；
- 第三方证照验真平台；
- RAG / 知识库；
- 合同审核、QC 证照、烟草证等其他 Skill；
- 生产级多租户和复杂组织权限。

这些能力后续可以作为企业系统集成或平台化扩展方向。

---

## 14. 本地开发规划

建议按以下顺序落地：

```text
1. 完成 README.md 和 docs 纯 Python V1 架构文档
2. 创建 ai-service FastAPI 骨架
3. 创建食品安全证照字段模型、审核任务模型、规则结果模型
4. 创建 LangGraph 食品安全证照检测工作流
5. 创建 LangChain 字段抽取 Chain 和结构化输出
6. 创建 Python 规则引擎基础实现
7. 打通 FastAPI 创建审核任务到 LangGraph 审核结果返回
8. 增加 SQLite / MySQL 表结构和初始化脚本
9. 增加人工复核接口和审计留痕能力
10. 增加 Docker Compose 本地启动配置
11. 增加端到端验收测试
```

---

## 15. 文档规划

建议后续补充以下文档：

```text
docs/
├── v1-python-architecture.md      # 纯 Python V1 架构说明
├── skill-architecture.md          # Skill 架构边界
├── prd-food-license-v1.md         # V1 食品安全证照检测 PRD
├── api-food-license-v1.md         # 食品安全证照 FastAPI 接口契约
├── database-design.md             # 数据库设计
├── deployment.md                  # 部署说明
└── roadmap.md                     # 后续路线图
```

---

## 16. 当前状态

当前项目处于初始规划和骨架建设阶段：

- 已明确项目定位；
- 已明确 V1 聚焦食品安全证照检测；
- 已确认 V1 采用纯 Python 架构；
- 已确认 FastAPI + LangGraph + LangChain + Python 规则引擎为 V1 核心技术路线；
- 已确认 Java / Spring Boot 不属于 V1 范围；
- 后续需要继续补齐代码骨架、接口契约、数据库设计和部署配置。

---

## Agent skills

### Issue tracker

本项目的 issues 和 PRD 目标上使用 GitLab Issues 管理，并通过 `glab` CLI 操作；实际创建 issue 前必须先配置 GitLab remote 并完成 `glab` 认证。详见 `docs/agents/issue-tracker.md`。

### Triage labels

本项目沿用默认的五个 triage label：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

本项目采用单一领域上下文，以 `README.md` 作为主要项目上下文，不单独使用 `CONTEXT.md`。详见 `docs/agents/domain.md`。
