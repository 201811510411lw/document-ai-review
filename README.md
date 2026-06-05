# document-ai-review

企业文档智能审核平台。

架构：Java Backend + Python AI Service。

V1：食品安全证照检测。

- backend-java：Spring Boot 对外接口、MySQL、任务、结果落库。
- ai-service：FastAPI + LangChain，负责证照解析、字段抽取、规则校验。
- deploy：本地编排。
- docs：架构文档。
- rules：规则配置。
