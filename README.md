# document-ai-review

企业内部 AI 文档智能审核系统，当前 V1 聚焦 **食品安全证照检测**。

本项目不是单纯 OCR 工具，而是面向企业内部审核场景的 **Document AI Review Agent / Skill 平台**。OCR 只是底层读取能力，核心目标是把证照、报告、合同等非结构化文件转为可校验、可追溯、可复核的结构化审核结果。

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

当前 V1 不优先做合同审核，而是先聚焦 **食品安全证照检测**，把证照审核链路跑通，再扩展到 QC 证照校验、烟草证一致性校验、法务合同审核等场景。

---

## 2. 当前 V1 范围

### 2.1 V1 目标

当前阶段优先实现：

```text
食品安全证照检测
```

V1 主要解决：

- 供应商是否上传了食品安全相关证照；
- 证照图片或 PDF 是否可以被正常解析；
- 证照中的关键字段是否可以被结构化抽取；
- 证照是否过期；
- 证照主体名称是否与业务系统供应商名称一致；
- 统一社会信用代码是否一致；
- 经营项目是否覆盖食品销售、预包装食品、散装食品等业务范围；
- 审核结果是否可以沉淀为可追溯、可复核的结构化数据。

### 2.2 输入来源

V1 先假设证照信息来自 MySQL 业务表：

- MySQL 业务表中的证照记录；
- 证照图片或 PDF 文件路径；
- 供应商名称；
- 统一社会信用代码；
- 供应商经营地址；
- 证照类型；
- 业务系统中的审核状态。

后续可以扩展为：

- ERP 系统；
- OA 系统；
- 文件服务器；
- 对象存储；
- 第三方验真平台；
- 内部主数据平台。

---

## 3. 系统架构

### 3.1 总体架构

```text
Java Spring Boot 对外暴露接口
    ↓
Python FastAPI + LangChain 提供 AI 能力
    ↓
OCR / 多模态模型 / 规则引擎 / RAG / 知识库
```

系统采用 Java + Python 双服务架构：

- Java 负责业务入口、权限控制、任务管理、数据库读写、人工复核、通知和审计；
- Python 负责文档解析、OCR、多模态模型调用、字段抽取、规则校验、风险报告生成；
- 两个服务通过 HTTP API 交互；
- 审核结果最终由 Java 服务落库，保证业务系统侧的数据闭环。

### 3.2 服务调用链路

```text
业务系统 / 管理后台
    ↓
backend-java
    ↓
MySQL 查询证照记录
    ↓
创建审核任务
    ↓
调用 ai-service
    ↓
文档解析 / 字段抽取 / 规则校验
    ↓
返回审核结论和风险明细
    ↓
backend-java 保存审核结果
    ↓
人工复核 / 通知 / 审计留痕
```

---

## 4. 服务职责

| 服务 | 职责 |
| --- | --- |
| `backend-java` | 对外 API、权限、任务管理、MySQL 业务数据读取、审核结果落库、人工复核、通知、审计留痕 |
| `ai-service` | 文档解析、证照字段抽取、规则校验、风险报告生成、LangChain / LLM 编排 |

### 4.1 backend-java 职责

`backend-java` 是业务后端服务，主要职责包括：

- 提供审核任务创建接口；
- 从 MySQL 查询供应商和证照记录；
- 管理审核任务状态；
- 调用 Python AI 服务；
- 保存 AI 返回的结构化字段、规则命中结果、风险等级和审核报告；
- 提供人工复核入口；
- 支持审核通过、审核驳回、人工确认等操作；
- 记录操作日志和审计日志；
- 后续对接企业微信、邮件、OA 待办等通知渠道。

### 4.2 ai-service 职责

`ai-service` 是 AI 能力服务，主要职责包括：

- 接收 Java 服务传入的审核任务；
- 加载证照图片或 PDF；
- 调用 OCR 或多模态模型解析文档内容；
- 抽取食品安全证照字段；
- 对抽取结果进行格式化和标准化；
- 根据规则配置执行校验；
- 生成风险项、风险等级、审核建议；
- 返回结构化审核结果给 Java 服务。

---

## 5. 仓库目录概览

项目采用 monorepo 结构：

```text
document-ai-review/
├── backend-java/                    # Java Spring Boot 后端服务
├── ai-service/                      # Python FastAPI AI 服务
├── deploy/                          # Docker / docker-compose / Kubernetes 部署配置
├── docs/                            # 项目设计文档
├── rules/                           # 业务审核规则配置
├── scripts/                         # 初始化脚本、测试脚本、工具脚本
├── README.md                        # 项目说明文档
└── .env.example                     # 环境变量示例
```

目录说明：

- `backend-java/`：Java 后端接口与业务逻辑；
- `ai-service/`：Python AI 服务，承载 OCR、LLM、规则校验和审核 Skill；
- `deploy/`：部署配置，例如 Docker Compose、Kubernetes YAML、Nginx 配置等；
- `docs/`：架构设计、接口契约、数据库设计、Skill 设计等文档；
- `rules/`：食品安全证照、烟草证、合同审核等规则配置；
- `scripts/`：数据库初始化、测试数据生成、批量任务脚本；
- `.env.example`：本地开发和部署所需环境变量示例。

---

## 6. ai-service 内部结构设计

`ai-service` 作为 AI 能力服务，建议采用如下结构：

```text
ai-service/
├── app/
│   ├── main.py                         # FastAPI 启动入口
│   ├── config.py                       # 全局配置
│   ├── api/                            # API 接口层
│   │   ├── upload.py                   # 文件上传接口
│   │   ├── review.py                   # 审核任务接口
│   │   ├── report.py                   # 审核报告接口
│   │   └── callback.py                 # ERP/OA 回调接口
│   ├── core/                           # 核心能力层
│   │   ├── task_manager.py             # 审核任务调度
│   │   ├── file_manager.py             # 文件管理
│   │   ├── skill_router.py             # Skill 路由
│   │   └── audit_logger.py             # 审计日志
│   ├── parsers/                        # 文档解析层
│   │   ├── image_parser.py             # 图片解析
│   │   ├── pdf_parser.py               # PDF 解析
│   │   └── ocr_parser.py               # OCR 解析封装
│   ├── extractors/                     # 知识抽取层
│   │   └── food_license_extractor.py   # 食品安全证照字段抽取
│   ├── skills/                         # 业务 Skill 层
│   │   └── food_license_review_skill.py # 食品安全证照审核 Skill
│   ├── rules/                          # 规则引擎层
│   │   ├── rule_engine.py              # 通用规则引擎
│   │   └── food_license_rules.py       # 食品安全证照规则
│   ├── llm/                            # 大模型调用层
│   │   ├── base_client.py              # 模型客户端基类
│   │   ├── local_llm_client.py         # 私有化模型调用
│   │   └── prompt_runner.py            # Prompt 执行封装
│   ├── rag/                            # 知识库 / RAG 层
│   │   ├── retriever.py                # 检索器
│   │   └── vector_store.py             # 向量库封装
│   ├── integrations/                   # 外部系统集成
│   │   ├── mysql_client.py             # MySQL 查询封装
│   │   ├── object_storage_client.py    # 对象存储 / 文件服务封装
│   │   └── callback_client.py          # 回调 Java 服务
│   ├── models/                         # 数据模型
│   │   ├── review_task.py              # 审核任务模型
│   │   ├── food_license.py             # 食品安全证照模型
│   │   └── review_result.py            # 审核结果模型
│   ├── db/                             # 数据库层
│   │   └── session.py                  # 数据库连接
│   └── prompts/                        # Prompt 模板
│       └── food_license_extract.md     # 食品安全证照抽取 Prompt
├── rules_config/                       # 规则配置文件
├── knowledge_base/                     # 知识库材料
├── storage/                            # 本地文件缓存
├── scripts/                            # 工具脚本
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── .env.example
```

---

## 7. backend-java 内部结构设计

`backend-java` 作为业务后端服务，建议采用如下结构：

```text
backend-java/
├── pom.xml
├── src/
│   └── main/
│       ├── java/
│       │   └── com/company/review/
│       │       ├── ReviewApplication.java
│       │       ├── controller/
│       │       │   └── FoodLicenseReviewController.java
│       │       ├── service/
│       │       │   └── FoodLicenseReviewService.java
│       │       ├── client/
│       │       │   └── AiReviewClient.java
│       │       ├── entity/
│       │       │   ├── SupplierLicense.java
│       │       │   ├── ReviewTask.java
│       │       │   └── ReviewResult.java
│       │       ├── mapper/
│       │       │   ├── SupplierLicenseMapper.java
│       │       │   ├── ReviewTaskMapper.java
│       │       │   └── ReviewResultMapper.java
│       │       ├── dto/
│       │       │   ├── CreateReviewTaskRequest.java
│       │       │   ├── AiReviewRequest.java
│       │       │   └── AiReviewResponse.java
│       │       └── common/
│       │           ├── Result.java
│       │           └── ReviewStatus.java
│       └── resources/
│           ├── application.yml
│           └── mapper/
└── README.md
```

---

## 8. V1 审核流程

```text
Java 查询 MySQL 证照记录
    ↓
Java 创建审核任务
    ↓
Java 调用 Python AI 服务
    ↓
Python 解析证照图片 / PDF
    ↓
Python 抽取食品安全证照字段
    ↓
Python 规则库校验
    ↓
Python 返回风险结果
    ↓
Java 保存审核结果
    ↓
人工复核 / 通知 / 审计留痕
```

### 8.1 详细流程说明

1. 用户或定时任务在 Java 服务中发起食品安全证照审核任务；
2. Java 服务根据供应商 ID 查询 MySQL 中的证照记录；
3. Java 服务构造审核请求，包含供应商信息、证照文件路径、证照类型等；
4. Java 服务调用 Python `ai-service` 的审核接口；
5. Python 服务读取证照图片或 PDF；
6. Python 服务通过 OCR 或多模态模型提取文本和版面信息；
7. `food_license_extractor` 抽取食品安全证照字段；
8. `food_license_review_skill` 调用规则引擎执行校验；
9. Python 服务返回字段抽取结果、规则命中结果、风险等级和审核建议；
10. Java 服务保存审核结果，并更新任务状态；
11. 若存在高风险项，进入人工复核或通知流程；
12. 所有审核过程写入审计日志。

---

## 9. 食品安全证照字段抽取

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

## 10. 食品安全证照规则示例

V1 建议先实现以下规则：

| 规则编码 | 规则名称 | 风险等级 | 说明 |
| --- | --- | --- | --- |
| `FOOD_LICENSE_EXISTS` | 证照是否存在 | 高 | 未上传证照或文件路径为空 |
| `FOOD_LICENSE_NO_REQUIRED` | 许可证编号是否为空 | 高 | 食品经营许可证编号不能为空 |
| `FOOD_LICENSE_EXPIRED` | 证照是否过期 | 高 | 当前日期超过证照有效期截止日期 |
| `SUBJECT_NAME_MATCH` | 主体名称是否一致 | 中 | 证照主体名称与供应商名称不一致 |
| `CREDIT_CODE_MATCH` | 统一社会信用代码是否一致 | 高 | 证照信用代码与业务系统信用代码不一致 |
| `BUSINESS_SCOPE_COVERED` | 经营项目是否覆盖食品业务 | 中 | 经营项目不包含食品销售相关范围 |
| `ADDRESS_SIMILARITY` | 经营场所是否近似匹配 | 低 | 证照地址与业务系统地址相似度较低 |

规则配置示例：

```yaml
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

## 11. AI 审核结果设计

Python AI 服务返回给 Java 服务的审核结果建议包含：

```json
{
  "task_id": "review-task-001",
  "document_type": "food_license",
  "status": "REVIEWED",
  "risk_level": "HIGH",
  "extracted_fields": {
    "subject_name": "成都示例食品有限公司",
    "credit_code": "91510100MA00000000",
    "license_no": "JY15101000000000",
    "valid_to": "2028-01-01"
  },
  "rule_results": [
    {
      "rule_code": "SUBJECT_NAME_MATCH",
      "rule_name": "主体名称是否一致",
      "passed": false,
      "risk_level": "MEDIUM",
      "message": "证照主体名称与业务系统供应商名称不一致"
    }
  ],
  "summary": "发现 1 项中风险问题，建议人工复核供应商主体名称。"
}
```

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
新增 Skill
    ↓
新增字段抽取器 Extractor
    ↓
新增规则配置 Rules
    ↓
新增 Prompt 模板
    ↓
复用任务管理、文件管理、审计日志、模型调用能力
```

---

## 13. 本地开发规划

建议按以下顺序落地：

```text
1. 完成 README.md 和 docs 架构文档
2. 创建 ai-service FastAPI 骨架
3. 创建食品安全证照字段模型
4. 创建食品安全证照审核 Skill
5. 创建规则引擎基础实现
6. 创建 backend-java Spring Boot 骨架
7. 打通 Java 调 Python 的审核接口
8. 增加 MySQL 表结构和初始化脚本
9. 增加 Docker Compose 本地启动配置
10. 增加人工复核和审计留痕能力
```

---

## 14. 文档规划

建议后续补充以下文档：

```text
docs/
├── architecture.md                # 系统架构设计
├── v1-food-license-design.md      # V1 食品安全证照检测设计
├── api-contract.md                # Java 与 Python 接口契约
├── database-design.md             # 数据库设计
├── skill-design.md                # Skill 设计规范
├── deployment.md                  # 部署说明
└── roadmap.md                     # 后续路线图
```

---

## 15. 当前状态

当前项目处于初始规划和骨架建设阶段：

- 已明确项目定位；
- 已明确 V1 聚焦食品安全证照检测；
- 已确认 Java + Python 双服务架构；
- 已确认 monorepo 项目结构；
- 后续需要继续补齐代码骨架、接口契约、数据库设计和部署配置。

---

## Agent skills

### Issue tracker

本项目的 issues 和 PRD 目标上使用 GitLab Issues 管理，并通过 `glab` CLI 操作；实际创建 issue 前必须先配置 GitLab remote 并完成 `glab` 认证。详见 `docs/agents/issue-tracker.md`。

### Triage labels

本项目沿用默认的五个 triage label：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

本项目采用单一领域上下文，以 `README.md` 作为主要项目上下文，不单独使用 `CONTEXT.md`。详见 `docs/agents/domain.md`。
