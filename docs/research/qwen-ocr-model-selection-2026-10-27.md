# 阿里云百炼 / 通义千问证件 OCR 模型选型研究

**研究日期：** 2026-10-27
**范围：** 烟草专卖零售许可证等证件图像中的字段和证件号码识别；仅依据阿里云百炼官方文档，未改业务代码。

## 结论

首选 `qwen3.5-ocr` 做烟草证图像的 OCR 和字段初步抽取。官方明确将它定位为文档解析、文字定位、关键信息提取模型，并说明业务卡证抽取效果升级；模型页还列出 Image 输入、Text 输出、16,384 最大输出长度和 65,536 上下文。它支持 OpenAI 兼容 Chat/Responses API，也支持 DashScope 多模态接口；但模型能力表明确写明不支持原生结构化输出和 Function Calling，因此业务侧必须对文本结果做严格解析、格式校验和确定性规则审核。

`qwen-vl-ocr`（稳定别名，当前能力等同 `qwen-vl-ocr-2025-11-20`）适合作为兼容旧链路或对比基线：官方将其定位为基于 Qwen3-VL 的 OCR 模型，提供文字定位、高精识别、信息抽取、表格/公式/多语言识别和图像旋转矫正。官方同时建议新项目迁移到 `qwen3.5-ocr`，并将 `qwen-vl-ocr-2024-10-28` 标为早期不推荐版本。其高级 OCR 任务和旋转矫正应走 DashScope SDK/接口；OpenAI 兼容 SDK 可迁移基础调用，但高级参数不能直接传入，需要 Prompt 模拟并自行解析。

`qwen3.8-max` 和 `qwen3.7-plus` 都支持图像输入、1M 上下文、Function Calling 和结构化输出，适合在 OCR 之后做复杂字段归一化、跨页语义理解或规则解释。官方没有把它们定位为专用 OCR 模型；对于证件号码这类逐字符精度要求高的任务，不应以它们替代专用 OCR，除非在真实烟草证样本上完成对比评测。两者的通用视觉能力可作为回退/二次复核：`qwen3.8-max` 偏最高能力但成本较高，`qwen3.7-plus` 是能力与成本均衡的通用模型。

## 对比

| 模型 | 官方定位与证据 | 接口/能力兼容性 | 烟草证号码建议 |
| --- | --- | --- | --- |
| `qwen3.5-ocr` | Qwen3.5 OCR；文档解析、文字定位、关键信息提取；业务卡证抽取升级 | Image→Text；支持 OpenAI Chat 和 Responses、DashScope 多模态；不支持原生结构化输出、Function Calling、联网搜索、批量推理；Responses 可直接传 PDF | **首选**。用 Prompt 约束字段输出，再由 Pydantic/规则层校验号码格式、长度、校验位和置信/人工复核条件 |
| `qwen-vl-ocr`（稳定别名） | Qwen3-VL OCR；高精文字定位、信息抽取、表格/公式/多语言、旋转矫正 | DashScope SDK/多模态接口可用全部高级 OCR 任务；OpenAI 兼容 SDK 便于迁移但不能直接调用高级 OCR 参数；旧版 Responses 不支持 | **兼容基线/回退**。适合需要内置 OCR task、旋转矫正或现有链路依赖该模型时；新项目优先迁移 3.5 OCR |
| `qwen3.8-max` | 通用旗舰文本/视觉理解与推理；官方推荐最高能力档 | 文本/图像/视频输入；1M 上下文；支持 Function Calling、内置工具、结构化输出；可处理大图（官方表列 16M 像素/图） | 不作为首级 OCR。可用于 OCR 后复杂语义复核、跨页关联和异常解释；成本和延迟需评估 |
| `qwen3.7-plus` | 通用视觉语言与 Agent 能力；官方推荐办公/文档处理的均衡模型 | 文本/图像/视频输入；1M 上下文；支持 Function Calling、内置工具、结构化输出；可处理大图（官方表列 16M 像素/图） | 不作为首级 OCR。可作为较低成本的二次抽取/复核或 `qwen3.8-max` 的对照模型 |

## 推荐调用与数据流

1. 对原始证件图像调用 `qwen3.5-ocr`，Prompt 要求只输出约定字段（例如许可证号、字号、经营者、地址、有效期），模糊字符使用明确占位符，不得猜测。
2. 解析文本后先做字段级确定性校验：号码正则/长度、日期合法性、证照类型和有效期规则；失败或模糊结果进入人工复核。
3. 需要内置旋转矫正、文字框或 OCR task 时，改用 DashScope 接口的 `ocr_options`；不要把这些高级参数假设成 OpenAI 兼容接口能力。
4. 对跨页 PDF，`qwen3.5-ocr` Responses API 可直接传 PDF；官方限制为文件不超过 100 MB，`document_parsing` 任务最多 50 页，其他任务最多 10 页。`qwen-vl-ocr-2025-11-20` 及更早版本不支持 Responses API，应先逐页转图。
5. 若需要结构化 JSON，优先让模型输出受控纯文本/JSON 片段，再由服务端模型解析和校验；不要把 `qwen3.5-ocr` 页面中的“不支持结构化输出”误读为可依赖的 schema 保证。通用模型的结构化输出也不能代替号码校验。

## 兼容性和风险

- **模型 ID 漂移：** 百炼文档把 `qwen-vl-ocr` 标为稳定版并说明当前能力等同 `qwen-vl-ocr-2025-11-20`；部署时应记录实际响应中的 `model`、请求 ID 和时间，避免只依赖别名。
- **OCR 结果不是合规裁判：** 官方资料描述识别能力，没有对烟草专卖零售许可证号码准确率、召回率或字段级置信度作承诺；必须用脱敏真实样本建立字符级/字段级评测集。
- **结构化输出限制：** `qwen3.5-ocr` 不支持原生结构化输出；Prompt 生成 JSON 仍可能出现转义、漏字段或幻觉，需严格解析失败即复核。
- **Prompt 格式风险：** 官方 FAQ 警告 `qwen3.5-ocr` 的 Prompt 若包含完整 HTML 结构，可能返回 HTML 而非纯文本；应使用纯文本指令，或不传 `text` 采用默认 Prompt。
- **接口地域和配额：** OpenAI 兼容端点的 Workspace/地域 URL 不同，API Key 也按地域区分；实际部署需核对账号权限、RPM/TPM、价格和可用地域。
- **隐私合规：** 烟草证可能含个人/经营主体信息。本文未核实当前租户的数据保留、跨境和日志策略，接入前需由项目合规负责人确认。

## 官方来源（访问日期：2026-10-27）

1. [qwen3.5-ocr 模型信息](https://help.aliyun.com/zh/model-studio/qwen3-5-ocr)：模型定位、输入/输出模态、上下文与能力限制。
2. [文字识别模型 qwen-vl-ocr 如何使用](https://help.aliyun.com/zh/model-studio/qwen-vl-ocr)：Qwen-OCR 模型选型、DashScope/OpenAI 兼容调用、OCR 任务、Responses/PDF 限制和 FAQ。
3. [视觉理解模型](https://help.aliyun.com/zh/model-studio/vision-model)：`qwen3.8-max`、`qwen3.7-plus` 的视觉输入、上下文、像素上限、结构化输出和工具支持。
4. [文本生成模型](https://help.aliyun.com/zh/model-studio/text-generation-model)：`qwen3.8-max` 与 `qwen3.7-plus` 的通用场景、能力档位和 1M 上下文说明。
5. [模型上下架与更新](https://help.aliyun.com/zh/model-studio/newly-released-models)：`qwen-vl-ocr`（2025-11-20）及 Qwen3.7 系列官方发布日期/定位。
6. [百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)：`qwen3.5-ocr`、`qwen-vl-ocr` 的模型 ID/价格信息（价格可能随地域和活动变化，部署前应重新核对）。

## 未决问题

- 当前仓库是否已有覆盖正反面、低清、旋转、反光、遮挡和旧版证件的脱敏烟草证评测集？没有评测集就无法证明某个模型对“证件号码”更优。
- 烟草证字段是否要求文字框坐标、字符级置信度或仅需文本？这会决定是否必须使用 `qwen-vl-ocr` 的内置高精定位任务。
- 生产环境是否允许将原图发送至百炼，以及应使用哪个地域/专属网络端点？需结合租户合规、网络和配额确认。
