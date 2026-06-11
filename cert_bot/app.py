"""
企业微信证照机器人 — FastAPI 主入口

提供:
  - 健康检查
  - 企业微信回调（验证 + 消息处理）
  - 手动触发效期检查
  - 批量导入
  - 记录查询
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

from . import config, database, handlers, wecom_client, importer as importer_module
from .scheduler import check_expiry_job, init_scheduler

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("cert_bot")

# APScheduler
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
except ImportError:
    logger.warning("APScheduler 未安装，定时任务不可用")
    scheduler = None


# ============================================================
# 应用生命周期
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭生命周期"""
    # 启动时执行
    logger.info("🚀 证照机器人启动中...")

    # 校验配置
    missing = config.validate()
    if missing:
        logger.warning(f"⚠️  以下配置未填写: {', '.join(missing)}")
        logger.warning("   请在 .env 文件中配置后重启服务")

    # 初始化数据库
    database.init_db()
    logger.info(f"✅ 数据库已初始化 ({config.DB_PATH})")

    # 启动定时调度器
    if scheduler:
        init_scheduler(scheduler)
        scheduler.start()
        logger.info("✅ 定时调度器已启动")

    logger.info("✅ 证照机器人就绪")
    yield

    # 关闭时执行
    if scheduler:
        scheduler.shutdown()
        logger.info("🛑 定时调度器已停止")


# ============================================================
# FastAPI 应用
# ============================================================

app = FastAPI(
    title="企业微信证照机器人",
    description="证照识别、效期校验、企业微信通知",
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# 路由: 健康检查
# ============================================================

@app.get("/health")
async def health():
    """服务健康检查"""
    return {
        "status": "ok",
        "time": time.time(),
    }


# ============================================================
# 路由: 企业微信回调
# ============================================================

@app.get("/wecom/callback")
async def wecom_verify(
    msg_signature: str = Query(alias="msg_signature"),
    timestamp: str = Query(),
    nonce: str = Query(),
    echostr: str = Query(),
):
    """
    企业微信回调 URL 验证（GET 请求）

    企业微信后台配置回调 URL 时，会发送 GET 请求验证
    需要正确响应 echostr
    """
    result = wecom_client.verify_url(msg_signature, timestamp, nonce, echostr)
    if result is not None:
        logger.info("✅ 回调 URL 验证通过")
        return PlainTextResponse(result)
    logger.warning("❌ 回调 URL 验证失败")
    return PlainTextResponse("验证失败")


@app.post("/wecom/callback")
async def wecom_callback(
    request: Request,
    msg_signature: str = Query(alias="msg_signature"),
    timestamp: str = Query(),
    nonce: str = Query(),
):
    """
    企业微信消息回调（POST 请求）

    用户向自建应用发消息时，企业微信会推送到此接口
    异步处理：先返回 success，再调用 API 回复
    """
    body = await request.body()
    body_str = body.decode("utf-8")
    logger.debug(f"收到回调: {body_str[:200]}")

    # 解密消息
    msg = wecom_client.decrypt_message(msg_signature, timestamp, nonce, body_str)
    if msg is None:
        # 解密失败或无 EncodingAESKey，仍然返回 success
        logger.warning("消息解密失败，忽略")
        return PlainTextResponse("success")

    # 记录日志
    logger.info(f"收到来自 {msg['from_user']} 的消息: {msg['content'][:100]}")

    # 异步处理查询（不阻塞回调响应）
    import asyncio
    asyncio.ensure_future(_process_message_async(msg))

    # 立即返回 success（企业微信 5 秒超时）
    return PlainTextResponse("success")


async def _process_message_async(msg: dict):
    """异步处理消息并回复"""
    try:
        content = msg.get("content", "").strip()
        if not content:
            return

        # 仅处理文本消息
        if msg.get("msg_type") != "text":
            return

        # 处理查询
        reply = handlers.handle_query(content)

        # 通过 API 回复
        wecom_client.send_markdown_message(reply, to_user=msg["from_user"])

        logger.info(f"✅ 已回复 {msg['from_user']}")
    except Exception as e:
        logger.error(f"❌ 处理消息异常: {e}")


# ============================================================
# 路由: 效期检查
# ============================================================

@app.post("/scheduler/check-expiry")
async def manual_check_expiry():
    """手动触发效期检查（POST 请求）"""
    logger.info("🔄 手动触发效期检查")
    try:
        check_expiry_job()
        return {"status": "ok", "message": "效期检查已完成"}
    except Exception as e:
        logger.error(f"效期检查失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ============================================================
# 路由: 批量导入
# ============================================================

from pydantic import BaseModel


class ImportRequest(BaseModel):
    urls: list[str]
    prompt: Optional[str] = None


@app.post("/importer/run")
async def run_import(req: ImportRequest):
    """
    批量导入证照

    用法:
        POST /importer/run
        {"urls": ["https://oss.../img1.jpg", "https://oss.../img2.jpg"]}

    对每个 URL 自动识别并存入数据库
    """
    if not req.urls:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "urls 列表不能为空"},
        )

    logger.info(f"🔄 批量导入: {len(req.urls)} 个文件")
    try:
        kwargs = {"prompt": req.prompt} if req.prompt else {}
        result = importer_module.import_from_urls(req.urls, **kwargs)
        return {"status": "ok", "data": result}
    except Exception as e:
        logger.error(f"批量导入失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)},
        )


# ============================================================
# 路由: 记录查询
# ============================================================

@app.get("/records")
async def list_records(
    expiring: bool = Query(default=False, description="仅查看即将过期"),
    expired: bool = Query(default=False, description="仅查看已过期"),
    keyword: str = Query(default="", description="按公司名搜索"),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """查询证照记录"""
    if expiring:
        records = database.get_expiring_records(30)
    elif expired:
        records = database.get_expired_records()
    elif keyword:
        records = database.search_records(keyword)
    else:
        records = database.get_all_records(limit=limit)

    return {
        "status": "ok",
        "total": len(records),
        "records": records,
    }


@app.get("/records/{record_id}")
async def get_record(record_id: int):
    """查询单条记录详情"""
    record = database.get_record(record_id)
    if not record:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"记录 {record_id} 不存在"},
        )
    return {"status": "ok", "record": record}


@app.delete("/records/{record_id}")
async def delete_record(record_id: int):
    """删除记录"""
    ok = database.delete_record(record_id)
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"记录 {record_id} 不存在"},
        )
    return {"status": "ok", "message": f"记录 {record_id} 已删除"}


@app.get("/stats")
async def get_stats():
    """获取统计信息"""
    stats = database.get_stats()
    return {"status": "ok", "data": stats}
