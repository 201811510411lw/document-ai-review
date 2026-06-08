# V1 Python Architecture

本文档说明 `document-ai-review` 在 **食品安全证照检测 V1** 阶段采用的纯 Python 架构。

`README.md` 仍然是项目唯一主上下文；本文档只承载更细的 V1 架构设计，不替代 README。

---

## 1. 纯 Python V1 架构说明

V1 不引入 Java / Spring Boot，不拆分为 `backend-java` + `ai-service` 两个服务。当前只建设一个 Python 服务：`ai-service`。

```text
业务系统 / 管理后台 / 测试脚本
    ↓
FastAPI HTTP API
    ↓
Review Service
    ↓
Skill Registry
    ↓
Skill.review(input_context)
    ↓
LangGraph Skill 内部工作流
    ↓
LangChain 字段抽取 / Python 规则引擎 / 人工复核决策
    ↓
ReviewResult
    ↓
Repository
    ↓
SQLite / MySQL
```

V1 的目标是优先跑通本地最小闭环：

```text
上传食品安全证照文件，或传入文件路径 / OCR 文本
    ↓
FastAPI 创建审核任务
    ↓
Review Service 调用 Skill Registry
    ↓
Registry 路由到 food_license Skill
    ↓
food_license.review(input_context) 执行审核
    ↓
保存审核任务、审核结果、规则结果、审计日志
    ↓
返回结构化审核结果
```

---

## 2. 职责边界

### 2.1 FastAPI

FastAPI 是 V1 的 HTTP API 边界，负责：

- 健康检查；
- 创建食品安全证照审核任务；
- 接收上传文件、文件路径或 OCR 文本；
- 查询审核任务和审核结果；
- 提供人工复核接口；
- 将请求转交给 Service 层，不直接承载审核规则或模型调用逻辑。

### 2.2 Review Service

Review Service 是 V1 审核用例编排层，负责：

- 创建审核任务；
- 构造 `input_context`；
- 调用 Skill Registry 选择并执行 Skill；
- 接收 `ReviewResult`；
- 保存审核结果、规则结果、人工复核状态和审计日志；
- 为食品安全证照快捷入口和后续平台通用入口复用同一套审核逻辑。

Review Service 不直接调用 `extract_fields`、`run_rules`、`summarize_risk` 或 `route_review` 等 Skill 内部节点。

### 2.3 Skill Registry

V1 Skill Registry 使用显式注册内置 Skill，不做目录扫描、外部 Skill 加载、插件市场、热加载或租户级覆盖。

Registry 负责：

- 加载并校验内置 Skill 的 `metadata.yaml`；
- 根据快捷入口、声明文档类型、`supported_document_types`、`input_modes` 和 `supports(input_context)` 选择 Skill；
- 调用 `Skill.review(input_context) -> ReviewResult`；
- 确保审核结果和审计日志记录 `skill_name`、`skill_version` 和 `ruleset_version`。

`metadata.yaml` 是 Skill 运行时 manifest，也是 `name`、`version`、`supported_document_types`、`input_modes` 和 `ruleset_version` 等元信息的权威来源。

### 2.4 Skill

Skill 是运行时一等业务对象，也是配置、Prompt、规则、模型、工作流和文档组织边界。平台只调用稳定 Skill 接口：

```text
name
version
supported_document_types
supports(input_context)
review(input_context) -> ReviewResult
```

`food_license` 是 V1 的第一个内置 Skill。食品安全证照检测的 LangGraph、LangChain Chain、Prompt、节点、模型适配、审核策略、具体规则和 `rules.yaml` 都属于 `app/skills/food_license/` 纵向包。

### 2.5 LangGraph

LangGraph 是 V1 审核流程的核心编排方式，负责：

- 在 Skill 内部定义食品安全证照检测工作流状态；
- 串联文档加载、证照类型识别、字段抽取、字段规范化、规则校验、风险汇总、人工复核路由等节点；
- 管理节点之间的状态传递；
- 将可变的审核流程显式建模，便于后续扩展其他 Skill。

这些节点是 Skill 内部实现细节，不是平台对 Skill 的公共调用接口。

### 2.6 LangChain

LangChain 负责模型相关能力，主要包括：

- LLM / 多模态模型调用；
- Prompt 模板管理；
- 结构化输出；
- 工具封装；
- 字段抽取 Chain。

LangChain 不负责最终确定性规则判断。证照是否过期、主体名称是否一致、信用代码是否一致等规则由 Python 规则引擎执行。

### 2.7 Python 规则引擎

Python 规则引擎负责执行可解释、可测试、可配置的确定性规则：

- 证照是否存在；
- 许可证编号是否为空；
- 证照是否过期；
- 主体名称是否一致；
- 统一社会信用代码是否一致；
- 经营项目是否覆盖食品业务；
- 经营场所是否近似匹配。

规则引擎输出规则结果列表，并为风险汇总节点提供依据。

`app/rules/` 只放通用规则基础设施，例如规则协议、`RuleEngine`、通用结果结构和默认风险汇总辅助函数。食品安全证照具体业务规则和 `rules.yaml` 放在 `app/skills/food_license/rules/` 内。

V1 只支持 Skill 包内静态 `rules.yaml`。`rules.yaml` 必须包含 `ruleset_version`。V1 不做数据库规则、外部规则覆盖、热加载规则或租户级规则覆盖。

### 2.8 Repository

Repository 层负责数据访问：

- 审核任务；
- 审核结果；
- 字段抽取结果；
- 规则结果；
- 人工复核记录；
- 审计日志。

V1 可以先使用 SQLite，后续按部署需要切换到 MySQL。

### 2.9 人工复核

人工复核基础设施属于平台，包括人工复核状态、动作、复核人、备注、记录保存和审计日志。

是否需要人工复核、初始人工复核状态和复核原因由 Skill 在 `review(input_context)` 中根据规则结果和审核策略决定。V1 人工复核状态枚举为 `NOT_REQUIRED`、`PENDING`、`COMPLETED`。

---

## 3. 推荐目录结构

V1 采用平台横向基础设施 + Skill 纵向包结构：

```text
ai-service/
└── app/
    ├── api/
    ├── core/
    ├── models/
    ├── repositories/
    ├── services/
    │   ├── review_service.py
    │   ├── skill_registry.py
    │   └── manual_review_service.py
    ├── rules/
    │   ├── engine.py
    │   ├── protocol.py
    │   └── result.py
    └── skills/
        └── food_license/
            ├── skill.py
            ├── metadata.yaml
            ├── README.md
            ├── models.py
            ├── prompts/
            ├── chains/
            ├── graphs/
            ├── nodes/
            ├── review_policy.py
            └── rules/
                ├── rules.yaml
                └── rule_defs.py
```

更完整的 Skill 边界说明见 [skill-architecture.md](skill-architecture.md)。

---

## 4. 食品安全证照检测 LangGraph 节点设计

### 4.1 工作流状态

LangGraph state 至少应包含：

- `task_id`：审核任务 ID；
- `input`：上传文件、文件路径或 OCR 文本；
- `supplier`：供应商名称、统一社会信用代码、经营地址等业务侧信息；
- `skill_name`：Skill 名称，例如 `food_license`；
- `skill_version`：Skill 版本，例如 `v1`；
- `ruleset_version`：规则集版本，来自 Skill `metadata.yaml` 或 Skill 内部 `rules.yaml`；
- `document`：统一文档内容；
- `document_type`：证照类型识别结果；
- `extracted_fields`：食品安全证照抽取字段；
- `normalized_fields`：规范化后的字段；
- `rule_results`：规则校验结果；
- `risk_level`：总体风险等级；
- `summary`：审核建议摘要；
- `needs_manual_review`：是否需要人工复核；
- `audit_events`：工作流执行过程中的关键事件。

### 4.2 节点列表

| 节点 | 输入 | 输出 | 职责 |
| --- | --- | --- | --- |
| `load_document` | 文件、文件路径或 OCR 文本 | 统一文档内容 | 加载并标准化文档输入 |
| `classify_document` | 统一文档内容 | 证照类型 | 判断是否为食品安全相关证照 |
| `extract_fields` | 文档内容、证照类型 | 抽取字段 | 通过 LangChain 和结构化输出抽取证照字段 |
| `normalize_fields` | 抽取字段 | 规范化字段 | 清洗日期、信用代码、经营项目、名称等字段 |
| `run_rules` | 规范化字段、供应商信息 | 规则结果 | 执行 Python 规则引擎 |
| `summarize_risk` | 规则结果 | 风险等级、审核建议 | 汇总风险结果 |
| `route_review` | 风险等级、规则结果 | 人工复核路由 | 判断自动通过、自动驳回或进入人工复核 |

这些节点属于 `food_license` Skill 内部实现。平台入口、Review Service 和 Registry 不直接调用这些节点，只调用 `food_license.review(input_context)`。

### 4.3 路由建议

V1 可以采用简单路由：

- 存在高风险规则失败：进入人工复核或自动驳回，具体由 PRD 决定；
- 仅存在中风险规则失败：进入人工复核；
- 仅存在低风险规则失败：可标记为低风险通过或进入人工复核；
- 全部规则通过：自动通过。

---

## 5. 数据保存范围

V1 至少保存：

- 审核任务：任务 ID、输入类型、供应商信息、任务状态、创建时间、更新时间；
- 审核结果：文档类型、`skill_name`、`skill_version`、`ruleset_version`、总体风险等级、审核建议、是否需要人工复核；
- Skill 专属结果：通过 `skill_result` 保存食品安全证照结构化字段、规范化字段和其他 Skill 专属 payload；
- 规则结果：规则编码、规则名称、是否通过、未通过时产生的风险等级、提示信息；
- 人工复核记录：复核动作、复核人、复核备注、复核时间；
- 审计日志：任务创建、工作流开始、节点执行、规则校验、人工复核等关键事件。

SQLite 可作为 V1 本地最小闭环默认选择；MySQL 可作为后续部署或集成环境选择。

---

## 6. V1 不做事项

V1 暂不实现：

- Java / Spring Boot 服务；
- `backend-java` 模块；
- 完整权限系统；
- 独立管理后台；
- 企业微信、邮件、OA 待办通知；
- 第三方证照验真平台；
- RAG / 知识库；
- 合同审核、QC 证照、烟草证等其他 Skill；
- 生产级多租户和复杂组织权限。

---

## 7. 后续 Java / 企业系统集成扩展方式

Java 不是 V1 范围，但后续企业系统仍可通过 HTTP API 集成当前 Python 服务：

```text
ERP / OA / Java 业务系统
    ↓
HTTP API
    ↓
ai-service
    ↓
Review Service + Skill Registry
    ↓
Skill.review(input_context)
    ↓
结构化审核结果
```

后续扩展可以选择：

- 业务系统调用 Python 服务创建审核任务；
- 业务系统上传文件或传入对象存储路径；
- Python 服务返回同步审核结果；
- Python 服务提供审核结果查询接口；
- Python 服务在审核完成后回调业务系统；
- Java 服务只作为企业业务系统集成层，不承担 V1 的核心审核逻辑。
