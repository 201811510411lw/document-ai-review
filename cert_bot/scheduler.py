"""
企业微信证照机器人 — 定时任务

每日效期检查 + 企业微信推送
"""

import logging
from datetime import datetime
from . import config, database, handlers, wecom_client

logger = logging.getLogger(__name__)


def check_expiry_job():
    """
    每日效期检查任务

    流程:
      1. 刷新所有记录的 expire_status
      2. 查询即将过期的记录
      3. 生成 markdown 通知
      4. 推送到企业微信
    """
    logger.info("🕐 开始执行每日效期检查...")

    # 1. 刷新效期状态
    total, updated = database.refresh_all_expire_status()
    logger.info(f"📊 已刷新 {updated}/{total} 条记录的状态")

    # 2. 查询即将过期的记录
    expiring = database.get_expiring_records(config.EXPIRY_WARNING_DAYS)
    expired = database.get_expired_records()

    if not expiring and not expired:
        logger.info("✅ 暂无临期或过期证照，跳过推送")
        return

    # 3. 生成通知
    notification = handlers.build_expiry_notification(config.EXPIRY_WARNING_DAYS)

    # 4. 推送到企业微信
    try:
        wecom_client.send_markdown_message(notification)
        logger.info(f"✅ 效期日报已推送（临期:{len(expiring)} 过期:{len(expired)}）")
    except Exception as e:
        logger.error(f"❌ 推送效期日报失败: {e}")


def init_scheduler(scheduler):
    """
    注册定时任务到 APScheduler

    参数:
        scheduler — APScheduler 实例
    """
    hour = config.CHECK_HOUR
    minute = config.CHECK_MINUTE

    scheduler.add_job(
        check_expiry_job,
        "cron",
        hour=hour,
        minute=minute,
        id="daily_expiry_check",
        replace_existing=True,
        misfire_grace_time=300,  # 任务错过执行时间后 5 分钟内仍可执行
    )

    logger.info(f"📅 每日效期检查已注册: {hour:02d}:{minute:02d}")
