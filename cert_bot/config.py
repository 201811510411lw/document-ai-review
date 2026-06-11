"""
企业微信证照机器人 — 配置管理
从 .env 或环境变量加载配置
"""

import os
from pathlib import Path

# 项目根目录（cert_bot 的上级）
ROOT_DIR = Path(__file__).resolve().parent.parent

# 自动加载 .env 文件（如果存在）
_env_path = ROOT_DIR / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_env_path))
        print(f"[config] 已加载环境变量: {_env_path}")
    except ImportError:
        pass

# ============================================================
# 数据库配置
# ============================================================
# SQLite（本地测试用，可随时切到 MySQL）
_env_db_path = os.getenv("CERT_BOT_DB_PATH", "")
DB_PATH = _env_db_path if _env_db_path else str(ROOT_DIR / "cert_bot.db")

# ============================================================
# 企业微信自建应用配置
# 上线前在 .env 文件中填写真实值
# ============================================================
WECOM = {
    # 企业 ID（在企微后台 "我的企业" → "企业信息" 查看）
    "corp_id": os.getenv("WECOM_CORP_ID", ""),
    # 自建应用 AgentId（在 "应用管理" → "自建" 查看）
    "agent_id": os.getenv("WECOM_AGENT_ID", ""),
    # 自建应用 Secret
    "secret": os.getenv("WECOM_SECRET", ""),
    # 回调配置 Token（在 "应用管理" → "自建" → "接收消息" 设置）
    "token": os.getenv("WECOM_TOKEN", ""),
    # 回调配置 EncodingAESKey
    "encoding_aes_key": os.getenv("WECOM_ENCODING_AES_KEY", ""),
}

# ============================================================
# 推送目标配置
# ============================================================
# 每日提醒推送给哪些用户（UserID，多个用 | 分隔）
# 留空表示推送给全部
NOTIFY_USERS = os.getenv("NOTIFY_USERS", "")
# 或推送到指定群聊（ChatId）
NOTIFY_CHAT = os.getenv("NOTIFY_CHAT", "")

# ============================================================
# 效期检查配置
# ============================================================
# 临近过期提醒天数
EXPIRY_WARNING_DAYS = int(os.getenv("EXPIRY_WARNING_DAYS", "30"))
# 每日检查时间（24 小时制）
CHECK_HOUR = int(os.getenv("CHECK_HOUR", "9"))
CHECK_MINUTE = int(os.getenv("CHECK_MINUTE", "0"))

# ============================================================
# Web 服务配置
# ============================================================
HOST = os.getenv("CERT_BOT_HOST", "0.0.0.0")
PORT = int(os.getenv("CERT_BOT_PORT", "8000"))


def validate():
    """检查必填配置是否已填写（用于启动时校验）"""
    missing = []
    if not WECOM["corp_id"]:
        missing.append("WECOM_CORP_ID")
    if not WECOM["agent_id"]:
        missing.append("WECOM_AGENT_ID")
    if not WECOM["secret"]:
        missing.append("WECOM_SECRET")
    if not WECOM["token"]:
        missing.append("WECOM_TOKEN")
    if not WECOM["encoding_aes_key"]:
        missing.append("WECOM_ENCODING_AES_KEY")
    return missing
