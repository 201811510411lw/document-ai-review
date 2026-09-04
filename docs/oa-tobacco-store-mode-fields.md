# OA 烟草门店模式字段口径

## 结论

OA 烟草商品建档申请使用表单字段是否为空区分门店模式：

| OA 字段 | 非空时的门店模式 | 应用内 `review_mode` |
| --- | --- | --- |
| `mdms` | 单店 | `standard` |
| `mdms1` | 店中店 | `store_in_store` |

门店模式只根据字段是否非空判断。字段值 `0`、`1` 表示烟草是否经过收银系统，当前证照一致性审核不处理该信息，不得使用该值改变门店模式或审核结论。

## 字段值含义

`mdms` 用于单店：

- `0`：单店，烟草经过收银系统。
- `1`：单店，烟草不经过收银系统。

`mdms1` 用于店中店：

- `0`：店中店，烟草经过收银系统。
- `1`：店中店，烟草不经过收银系统。

无论值为 `0` 还是 `1`，只要对应字段非空，就表示选择了该字段对应的门店模式。

## 判定规则

1. `mdms IS NOT NULL` 且 `mdms1 IS NULL`：判定为单店。
2. `mdms IS NULL` 且 `mdms1 IS NOT NULL`：判定为店中店。
3. `mdms` 与 `mdms1` 均为空：返回非重试错误 `OA_STORE_MODE_MISSING`。
4. `mdms` 与 `mdms1` 均非空：返回非重试错误 `OA_STORE_MODE_CONFLICT`。
5. 同一请求的附件来源行中 `mdms` / `mdms1` 的空值位置不一致：返回非重试错误 `OA_STORE_MODE_INCONSISTENT`。

审核逻辑不校验非空字段的具体值；具体值只作为来源证据保留，不参与门店模式或证照一致性结论。

OA 字段应作为门店模式的首要依据。营业执照附件数量及 OCR 字段匹配用于验证材料是否符合所选模式，以及在店中店模式下分配“烟草持证主体营业执照”和“加盟店营业执照”，不应继续作为门店模式的首要推断依据。

## 来源位置

业务提供的信息指向 StarRocks 表：

```text
ods_oa_ecology_formtable_main_283_cdc
```

当前仓库运行代码直接查询 OA ecology MySQL 的 `formtable_main_283`；仓库 StarRocks 建表脚本定义的是每日全量表 `ods_oa_ecology_formtable_main_283_df`，其中已经包含 `mdms` 和 `mdms1` 字段。

本次实现继续使用 OA ecology MySQL，不会把运行来源切换到 StarRocks。部署验收时仍需确认实际 OA MySQL 表存在这两个字段，并核对 OA MySQL、StarRocks `_cdc` 表与 `_df` 表中的字段语义是否一致。

## 当前实现状态

截至 2026-09-04，OA 自动审核已经从源端 MySQL `formtable_main_283` 读取 `mdms` 和 `mdms1`，并按本文档规则确定门店模式。原始字段值、最终 `review_mode` 和 `review_mode_source=oa_mysql_fields` 会保存在来源证据快照中。

当前处理步骤为：

1. 从精确的 `workflow_id + requestid` 来源记录读取 `mdms`、`mdms1`。
2. 按本文档规则确定 `review_mode`，保留两个字段的原始值作为来源证据。
3. 使用附件数量和 OCR 结果校验所选模式的材料完整性。
4. 店中店模式下，再根据 OCR 字段分配两张营业执照的业务角色；无法唯一分配时进入人工复核。
5. 将最终模式、判定来源和冲突信息持久化，并随审核详情保留以便审计。

## 信息来源

本口径来自业务方于 2026-09-04 提供的 OA 字段说明截图：

> `mdms` 不为空表示单店，`mdms1` 不为空表示店中店；字段值 `0/1` 表示烟草是否经过收银系统，当前审核不处理收银系统差异。
