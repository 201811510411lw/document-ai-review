"""
企业微信证照机器人 — 企业微信 API 封装

提供消息发送、文件下发等功能
"""

import json
import time
import hashlib
import base64
import requests
import xml.etree.ElementTree as ET
from typing import Optional
from . import config

# ============================================================
# 基础 API
# ============================================================

API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

_token_cache = {"access_token": None, "expires_at": 0}


def get_access_token() -> str:
    """
    获取 access_token（自动缓存）
    文档: https://developer.work.weixin.qq.com/document/path/91039
    """
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    if not config.WECOM["corp_id"] or not config.WECOM["secret"]:
        raise ValueError("企业微信配置不完整: 请设置 WECOM_CORP_ID 和 WECOM_SECRET")

    resp = requests.get(
        f"{API_BASE}/gettoken",
        params={
            "corpid": config.WECOM["corp_id"],
            "corpsecret": config.WECOM["secret"],
        },
        timeout=10,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"获取 access_token 失败: {data.get('errmsg')}")

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 7200) - 60  # 提前 60s 过期
    return data["access_token"]


# ============================================================
# 消息发送
# ============================================================

def send_text_message(content: str, to_user: str = "", to_chat: str = "") -> dict:
    """
    发送文本消息

    参数:
        content — 消息内容
        to_user — 接收人 UserID（多个用 | 分隔），空则使用 NOTIFY_USERS
        to_chat — 群聊 ChatId
    """
    return _send_message(
        msgtype="text",
        content={"content": content},
        to_user=to_user or config.NOTIFY_USERS,
        to_chat=to_chat or config.NOTIFY_CHAT,
    )


def send_markdown_message(content: str, to_user: str = "", to_chat: str = "") -> dict:
    """
    发送 markdown 消息

    支持语法: 标题(#)、粗体(**)、超链接、引用(>)、有序列表(1.)
    文档: https://developer.work.weixin.qq.com/document/path/90236
    """
    return _send_message(
        msgtype="markdown",
        content={"content": content},
        to_user=to_user or config.NOTIFY_USERS,
        to_chat=to_chat or config.NOTIFY_CHAT,
    )


def send_file_by_url(file_url: str, file_name: str, to_user: str = "", to_chat: str = "") -> dict:
    """
    从 OSS URL 下载文件 → 上传到微信临时素材 → 发送给用户

    参数:
        file_url  — OSS 文件地址
        file_name — 显示的文件名
    """
    print(f"[wecom] 准备下发文件: {file_name}")

    # 1. 下载 OSS 文件
    resp = requests.get(file_url, timeout=30)
    resp.raise_for_status()
    file_data = resp.content

    # 2. 上传到微信临时素材
    media_id = _upload_media(file_data, file_name, "file")
    if not media_id:
        print(f"[wecom] 上传素材失败: {file_name}")
        return {"errcode": -1, "errmsg": "upload media failed"}

    # 3. 发送文件消息
    return _send_message(
        msgtype="file",
        content={"media_id": media_id},
        to_user=to_user or config.NOTIFY_USERS,
        to_chat=to_chat or config.NOTIFY_CHAT,
    )


def _send_message(msgtype: str, content: dict, to_user: str = "", to_chat: str = "") -> dict:
    """通用消息发送"""
    token = get_access_token()
    body = {
        "msgtype": msgtype,
        "agentid": config.WECOM["agent_id"],
        msgtype: content,
    }

    if to_chat:
        body["chatid"] = to_chat
        url = f"{API_BASE}/appchat/send?access_token={token}"
    else:
        body["touser"] = to_user or "@all"
        url = f"{API_BASE}/message/send?access_token={token}"

    resp = requests.post(url, json=body, timeout=10)
    data = resp.json()
    if data.get("errcode") != 0:
        print(f"[wecom] 发送消息失败: {data.get('errmsg')} (errcode={data.get('errcode')})")
    else:
        print(f"[wecom] 消息已发送 (type={msgtype})")
    return data


def _upload_media(file_data: bytes, file_name: str, media_type: str = "file") -> Optional[str]:
    """
    上传临时素材到企业微信

    返回 media_id，失败返回 None
    文档: https://developer.work.weixin.qq.com/document/path/90253
    """
    token = get_access_token()
    url = f"{API_BASE}/media/upload?access_token={token}&type={media_type}"

    resp = requests.post(
        url,
        files={"media": (file_name, file_data)},
        timeout=60,
    )
    data = resp.json()
    if data.get("errcode") != 0:
        print(f"[wecom] 上传素材失败: {data.get('errmsg')}")
        return None
    return data.get("media_id")


# ============================================================
# 回调验证 & 消息解密
# ============================================================

def verify_url(msg_signature: str, timestamp: str, nonce: str, echostr: str) -> Optional[str]:
    """
    验证回调 URL（企业微信 GET 验证）
    验证成功返回 echostr（原样返回），失败返回 None
    """
    if _verify_signature(msg_signature, timestamp, nonce):
        return echostr
    return None


def decrypt_message(msg_signature: str, timestamp: str, nonce: str, encrypted_xml: str) -> Optional[dict]:
    """
    解密回调消息

    参数:
        encrypted_xml — WeCom POST 过来的加密 XML 字符串

    返回:
        {
            "from_user": "UserID",
            "msg_type": "text",
            "content": "用户发送的消息内容",
        }
        解密失败返回 None
    """
    if not config.WECOM["encoding_aes_key"]:
        print("[wecom] 未配置 EncodingAESKey，跳过消息解密")
        return None

    if not _verify_signature(msg_signature, timestamp, nonce):
        print("[wecom] 回调消息签名验证失败")
        return None

    # 解析加密 XML
    try:
        root = ET.fromstring(encrypted_xml.encode("utf-8"))
        encrypt_node = root.find("Encrypt")
        if encrypt_node is None:
            return None
        encrypted_msg = encrypt_node.text
    except ET.ParseError:
        return None

    # AES 解密
    plain_xml = _aes_decrypt(encrypted_msg)
    if not plain_xml:
        return None

    # 解析明文 XML
    try:
        msg_root = ET.fromstring(plain_xml.encode("utf-8"))
        result = {
            "from_user": _get_xml_text(msg_root, "FromUserName"),
            "msg_type": _get_xml_text(msg_root, "MsgType"),
            "content": _get_xml_text(msg_root, "Content"),
            "msg_id": _get_xml_text(msg_root, "MsgId"),
            "create_time": _get_xml_text(msg_root, "CreateTime"),
        }
        return result
    except ET.ParseError:
        return None


def build_text_reply_xml(from_user: str, to_user: str, content: str) -> str:
    """
    构建文本回复 XML（用于同步响应）
    注意：异步回复请使用 send_text_message()
    """
    timestamp = str(int(time.time()))
    return f"""<xml>
<ToUserName><![CDATA[{from_user}]]></ToUserName>
<FromUserName><![CDATA[{to_user}]]></FromUserName>
<CreateTime>{timestamp}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""


# ============================================================
# 内部辅助
# ============================================================

def _verify_signature(msg_signature: str, timestamp: str, nonce: str) -> bool:
    """验证消息签名"""
    token = config.WECOM["token"]
    if not token:
        return False
    sorted_str = "".join(sorted([token, timestamp, nonce]))
    calc_sig = hashlib.sha1(sorted_str.encode("utf-8")).hexdigest()
    return calc_sig == msg_signature


def _get_xml_text(root: ET.Element, tag: str) -> str:
    """安全获取 XML 子节点文本"""
    node = root.find(tag)
    return node.text or "" if node is not None else ""


def _aes_decrypt(encrypted_msg: str) -> Optional[str]:
    """
    AES-256-CBC 解密（PKCS7 填充）

    使用 pycryptodome 库
    如果未安装，给出提示
    """
    try:
        from Crypto.Cipher import AES
    except ImportError:
        print("[wecom] 需要安装 pycryptodome 才能解密消息: pip install pycryptodome")
        return None

    try:
        aes_key = config.WECOM["encoding_aes_key"] + "="  # 补齐 base64 padding
        key = base64.b64decode(aes_key)
        cipher = AES.new(key, AES.MODE_CBC, key[:16])  # IV 取 key 前 16 字节

        decrypted = cipher.decrypt(base64.b64decode(encrypted_msg))

        # 去掉 PKCS7 填充
        pad_len = decrypted[-1]
        if pad_len < 1 or pad_len > 32:
            return None
        decrypted = decrypted[:-pad_len]

        # 去掉前 20 字节（16 字节随机串 + 4 字节网络序消息长度）
        msg_len = int.from_bytes(decrypted[16:20], "big")
        msg = decrypted[20:20 + msg_len]

        return msg.decode("utf-8")
    except Exception as e:
        print(f"[wecom] AES 解密失败: {e}")
        return None


