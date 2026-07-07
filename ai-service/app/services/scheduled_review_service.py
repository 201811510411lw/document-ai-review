"""
每天定时自动审核服务 —— 凌晨 2:00 自动拉取 SRM 前一天新增的证照进行 OCR+LLM 审核。

工作流程:
  1. 读取上次同步时间戳（从 review_result 库 settings 表）
  2. 对每种证照类型，查询 SRM 库 created >= 上次同步时间的记录
  3. 跳过已在 review_result 表中存在 source_record_id 的记录
  4. 逐条调用 OCR + LLM 审核管线
  5. 全部完成后更新同步时间戳

线程安全：用一个 threading.Lock 防止多实例重复执行。
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from app.integrations.mysql_client import MySqlFetchClient, MySqlSettings, mysql_settings_from_env
from app.integrations.srm.business_license_tasks import (
    BusinessLicenseSourceTask,
    fetch_business_license_source_tasks,
)
from app.integrations.srm.document_records import (
    DocumentRecord,
    map_srm_certification_row,
)
from app.integrations.srm.food_license_tasks import (
    FoodLicenseSourceTask,
    fetch_food_license_source_tasks,
)
from app.integrations.srm.food_production_license_tasks import (
    FoodProductionLicenseSourceTask,
    fetch_food_production_license_source_tasks,
)
from app.integrations.srm.product_report_tasks import (
    ProductReportSourceTask,
    fetch_product_report_source_tasks,
)
from app.models import ReviewDocumentInput, ReviewInput
from app.services.review_service import ReviewService

logger = logging.getLogger(__name__)
_LockType = type(threading.Lock())

# ---------------------------------------------------------------------------
# 按日期范围查询的 SQL（替换原 order by rand() limit 1）
# ---------------------------------------------------------------------------

SRM_SQL_TEMPLATE = """
select
    t1.*,
    t2.refId as attachmentRefId,
    t2.refType,
    t2.attachmentName,
    t2.storeId,
    t2.removed,
    t2.url
from
    srm.certification t1
left join srm.attachment t2 on
    t1.uuid = t2.refId
where
    t2.tenant = '8560'
    and t2.refType = 'certification'
    and t2.url is not null
    and t2.url <> ''
    and t1.category = '{category}'
    and t1.typeName = '{type_name}'
    and t1.deleted = 0
    and t2.removed = 0
    and t1.created >= '{since_iso}'
"""

# 商品报告 category = 'sku'
SRM_PRODUCT_SQL_TEMPLATE = """
select
    t1.uuid, t1.tenant, t1.category, t1.typeName, t1.typeCode,
    t1.vendorId, t1.vendorName, t1.num, t1.number, t1.state,
    t1.deleted, t2.removed,
    t2.uuid as attachment_uuid, t2.refId as refId,
    t2.attachmentName, t2.storeId, t2.url,
    t1.created, t1.lastModified, t1.expiredBegin, t1.expiredEnd
from
    srm.certification t1
left join srm.attachment t2 on
    t1.uuid = t2.refId
where
    t2.tenant = '8560'
    and t1.category in ('sku', 'vendor', 'manufacturer')
    and t1.typeName = '产品报告'
    and t1.deleted = 0
    and t2.removed = 0
    and t2.url is not null
    and t2.url <> ''
    and t1.created >= '{since_iso}'
"""


# ---------------------------------------------------------------------------
# 文档类型配置
# ---------------------------------------------------------------------------

DOCUMENT_TYPE_CONFIG = [
    {
        "document_type": "business_license",
        "sql": SRM_SQL_TEMPLATE.format(category="vendor", type_name="营业执照", since_iso="{since_iso}"),
        "fetch_tasks_fn": fetch_business_license_source_tasks,
        "use_case": "business_license",
    },
    {
        "document_type": "food_license",
        "sql": SRM_SQL_TEMPLATE.format(category="vendor", type_name="食品经营许可证", since_iso="{since_iso}"),
        "fetch_tasks_fn": fetch_food_license_source_tasks,
        "use_case": "food_license",
    },
    {
        "document_type": "food_production_license",
        "sql": SRM_SQL_TEMPLATE.format(category="vendor", type_name="食品生产许可证", since_iso="{since_iso}"),
        "fetch_tasks_fn": fetch_food_production_license_source_tasks,
        "use_case": "food_production_license",
    },
    {
        "document_type": "product_report",
        "sql": SRM_PRODUCT_SQL_TEMPLATE.format(since_iso="{since_iso}"),
        "fetch_tasks_fn": fetch_product_report_source_tasks,
        "use_case": "product_report",
    },
]

# 各审核结果表的 source_record_id 去重查询
DEDUP_SQL_TEMPLATE = "SELECT COUNT(*) FROM {table} WHERE source_record_id = %s"

DEDUP_TABLE_MAP = {
    "business_license": "business_license_reviews",
    "food_license": "food_license_reviews",
    "food_production_license": "food_production_license_reviews",
    "product_report": "product_report_reviews",
}

# 同步时间戳的 settings key
LAST_SYNC_TIME_KEY = "daily_review_last_sync_time"
# 默认首次同步：往前拉 7 天的数据
DEFAULT_SYNC_LOOKBACK_DAYS = 7


# ---------------------------------------------------------------------------
# 核心同步函数
# ---------------------------------------------------------------------------

class SyncProgress:
    """同步进度（用于日志和后续展示）"""
    def __init__(self):
        self.total = 0
        self.skipped = 0
        self.new = 0
        self.succeeded = 0
        self.failed = 0
        self.errors: list[str] = []


def _get_last_sync_time_from_db(review_db: MySqlFetchClient) -> str:
    """读取上次成功同步时间，没有则返回 N 天前的日期"""
    try:
        rows = review_db.fetch_all(
            f"SELECT setting_value FROM settings WHERE setting_key = '{LAST_SYNC_TIME_KEY}'"
        )
        if rows:
            return str(rows[0].get("setting_value") or "")
    except Exception:
        pass
    return (date.today() - timedelta(days=DEFAULT_SYNC_LOOKBACK_DAYS)).isoformat()


def _update_last_sync_time_in_db(review_db: MySqlFetchClient) -> None:
    """更新同步时间戳为当前时间"""
    now = datetime.now().isoformat()
    try:
        escaped_now = now.replace("'", "''")
        review_db.fetch_all(
            f"INSERT INTO settings (setting_key, setting_value) "
            f"VALUES ('{LAST_SYNC_TIME_KEY}', '{escaped_now}') "
            f"ON DUPLICATE KEY UPDATE setting_value = '{escaped_now}'"
        )
    except Exception as e:
        logger.warning("[scheduled-review] 更新同步时间失败: %s", e)


def is_already_reviewed(
    review_db: MySqlFetchClient,
    document_type: str,
    source_record_id: str,
) -> bool:
    """检查该 source_record_id 是否已在审核结果表中存在"""
    table = DEDUP_TABLE_MAP.get(document_type)
    if not table or not source_record_id:
        return False
    try:
        escaped_id = source_record_id.replace("'", "''")
        sql = f"SELECT COUNT(*) AS cnt FROM {table} WHERE source_record_id = '{escaped_id}'"
        rows = review_db.fetch_all(sql)
        return rows and int(rows[0]["cnt"]) > 0
    except Exception as e:
        logger.warning("[scheduled-review] 去重查询失败 %s/%s: %s", document_type, source_record_id, e)
        return False


def run_daily_sync(
    srm_client: MySqlFetchClient,
    review_db: MySqlFetchClient,
    review_service: ReviewService,
    *,
    since_date: str | None = None,
) -> SyncProgress:
    """
    执行一次完整的每日同步。

    参数:
        since_date: 可选，覆盖同步起始日期（YYYY-MM-DD 格式）。
                    不传则从 review_db 的 settings 表读取上次同步时间。

    返回 SyncProgress 对象，包含处理统计。
    """
    lock = _get_sync_lock()
    if not lock.acquire(blocking=False):
        logger.warning("[scheduled-review] 上一次同步还在执行中，跳过本次")
        progress = SyncProgress()
        progress.errors.append("上一次同步未完成")
        return progress

    try:
        since = since_date or _get_last_sync_time_from_db(review_db)
        logger.info("[scheduled-review] 开始同步, 起始日期: %s", since)
        since_iso = since[:10] + " 00:00:00" if " " not in since else since

        progress = SyncProgress()

        for cfg in DOCUMENT_TYPE_CONFIG:
            doc_type = cfg["document_type"]
            use_case = cfg["use_case"]

            # 构建日期过滤 SQL
            sql = cfg["sql"].format(since_iso=since_iso)
            logger.info("[scheduled-review] 查询 %s: created >= %s", doc_type, since_iso)

            try:
                rows = srm_client.fetch_all(sql)
            except Exception as e:
                logger.error("[scheduled-review] 查询 %s 失败: %s", doc_type, e)
                progress.errors.append(f"查询 {doc_type} 失败: {e}")
                continue

            if not rows:
                logger.info("[scheduled-review] %s 无新增记录", doc_type)
                continue

            # 用现有的 fetch_tasks_fn 处理原始行 → task 对象
            try:
                tasks = cfg["fetch_tasks_fn"](srm_client, sql)
            except Exception as e:
                logger.warning("[scheduled-review] fetch_tasks_fn 处理 %s 失败: %s，改用直接映射", doc_type, e)
                # 降级方案：手动映射
                tasks = []
                for row in rows:
                    try:
                        record = map_srm_certification_row(row)
                        tasks.append(_manual_task(record, use_case))
                    except Exception as row_e:
                        logger.warning("[scheduled-review] 跳过行 %s: %s", row.get("uuid"), row_e)

            progress.total += len(rows)

            for task in tasks:
                record_id = task.record.record_id or ""
                company_name = task.record.vendor_name or "未知"

                # 去重：检查是否已审核过
                if record_id and is_already_reviewed(review_db, doc_type, record_id):
                    progress.skipped += 1
                    logger.info("[scheduled-review] 跳过已审核 %s/%s", doc_type, record_id)
                    continue

                # 执行审核
                progress.new += 1
                try:
                    result = review_service.review(task.review_input, use_case_name=use_case)
                    if result and getattr(result, "status", None) != "failed":
                        progress.succeeded += 1
                        logger.info("[scheduled-review] ✅ %s - %s 审核完成", company_name, doc_type)
                    else:
                        progress.failed += 1
                        logger.warning("[scheduled-review] ⚠️ %s - %s 审核返回异常", company_name, doc_type)
                except Exception as e:
                    progress.failed += 1
                    err_msg = f"{company_name}/{doc_type}: {e}"
                    progress.errors.append(err_msg)
                    logger.error("[scheduled-review] ❌ %s", err_msg)

        # 全部处理完毕，更新时间戳（即使有失败也更新，避免重复处理已成功的）
        _update_last_sync_time_in_db(review_db)
        logger.info(
            "[scheduled-review] 同步完成: 总计=%d, 跳过=%d, 新增=%d, 成功=%d, 失败=%d",
            progress.total, progress.skipped, progress.new,
            progress.succeeded, progress.failed,
        )
        return progress

    finally:
        lock.release()


def _manual_task(record: DocumentRecord, use_case: str) -> Any:
    """降级方案：将 DocumentRecord 转为类似现有 task 的结构"""
    from pydantic import BaseModel

    class _Task(BaseModel):
        record: DocumentRecord
        review_input: ReviewInput

    return _Task(
        record=record,
        review_input=ReviewInput(
            supplier_name=record.vendor_name or "",
            supplier_credit_code=record.business_num or record.business_number or "",
            declared_document_type=record.declared_document_type,
            file=ReviewDocumentInput(
                file_uri=record.file_url or "",
                file_name=record.file_name or "",
            ),
            source={
                "source_system": record.source_system,
                "tenant": record.tenant,
                "record_id": record.record_id,
                "attachment_ref_id": record.attachment_ref_id,
                "document_category": record.document_category,
                "document_type_code": record.document_type_code,
                "file_store_key": record.file_store_key,
                "source_payload": record.source_payload,
            },
        ),
    )


_lock: _LockType | None = None


def _get_sync_lock() -> _LockType:
    global _lock
    if _lock is None:
        _lock = threading.Lock()
    return _lock


# ---------------------------------------------------------------------------
# 定时调度器
# ---------------------------------------------------------------------------

class DailyReviewScheduler:
    """
    每天定时执行一次自动审核的调度器。

    用法:
        scheduler = DailyReviewScheduler()
        scheduler.start()   # 在后台线程启动
        ...
        scheduler.stop()    # 应用关闭时停止
    """

    def __init__(
        self,
        srm_settings: MySqlSettings | None = None,
        review_db_settings: MySqlSettings | None = None,
        *,
        run_hour: int = 2,
        run_minute: int = 0,
        check_interval_seconds: int = 60,
    ):
        self.srm_settings = srm_settings or mysql_settings_from_env("SRM_MYSQL")
        self.review_db_settings = review_db_settings or mysql_settings_from_env("REVIEW_RESULT_MYSQL")
        self.run_hour = run_hour
        self.run_minute = run_minute
        self.check_interval = check_interval_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("[scheduler] 调度器已在运行")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="daily-review-scheduler")
        self._thread.start()
        logger.info(
            "[scheduler] 每日审核调度器已启动，计划运行时间 %02d:%02d，检查间隔 %ds",
            self.run_hour, self.run_minute, self.check_interval,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            logger.info("[scheduler] 调度器已停止")

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _should_run_now(self) -> bool:
        now = datetime.now()
        return now.hour == self.run_hour and now.minute == self.run_minute

    def _run_loop(self) -> None:
        # 避免启动后立即触发（万一启动时间正好是目标时间）
        _last_run_date = date.today()

        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                # 每天只运行一次
                if self._should_run_now() and _last_run_date != now.date():
                    _last_run_date = now.date()
                    logger.info("[scheduler] 触发每日自动审核")
                    self._execute_sync()
                else:
                    # 未到时间，继续等待
                    time.sleep(self.check_interval)
            except Exception as e:
                logger.error("[scheduler] 调度循环异常: %s", e)
                time.sleep(self.check_interval)

    def _execute_sync(self) -> None:
        """执行一次同步"""
        try:
            srm_client = MySqlFetchClient(self.srm_settings)
            review_db_client = MySqlFetchClient(self.review_db_settings)
            from app.repositories import build_review_result_repository_from_env
            review_repo = build_review_result_repository_from_env()
            review_service = ReviewService(repository=review_repo)
            progress = run_daily_sync(srm_client, review_db_client, review_service)
            logger.info(
                "[scheduler] 自动审核完成: 新增=%d, 跳过=%d, 成功=%d, 失败=%d",
                progress.new, progress.skipped, progress.succeeded, progress.failed,
            )
        except Exception as e:
            logger.error("[scheduler] 自动审核执行异常: %s", e)
