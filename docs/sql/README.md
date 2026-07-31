# StarRocks 来源表

这里的脚本定义文档审核来源查询所消费的 StarRocks 表，不负责从 SRM 或 OA 复制、调度或清洗数据。集成职责见[外部集成](../INTEGRATIONS.md)，数据库权限、调度和验证见[运维手册](../OPERATIONS.md)。

在配置的 `STARROCKS_DATABASE` 中按顺序执行：

1. `create_starrocks_srm_batch_report_source_tables.sql`
2. `create_starrocks_oa_ecology_source_tables.sql`

第一份脚本创建 SRM 证照表、共享附件表和批次报告相关表；第二份脚本创建烟草证一致性审核使用的五张 `ods_oa_ecology_*_df` 来源表。

启用来源审核 API 或 `daily-review-scheduler` 前，必须由独立同步作业保持这些表的数据新鲜度。应用通过 `STARROCKS_*` 连接读取来源；`REVIEW_RESULT_MYSQL_*` 指向独立的事务结果库，用于 Review Result、业务投影、人工复核、审计和通知队列。

建表后至少验证：

- 当前账号可以读取目标数据库和所有来源表。
- SRM/OA 同步租户、删除标记和业务类型筛选符合[能力矩阵](../CAPABILITIES.md)。
- 附件路径或 URL 对运行服务可访问，且不包含越界路径。
- 来源库与结果库没有误配为同一职责或同一配置前缀。
