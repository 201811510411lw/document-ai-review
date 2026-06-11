"""
企业微信证照机器人 — 消息处理逻辑

解析用户查询、搜索数据库、组装回复内容
"""

from typing import Optional
from . import database


def handle_query(content: str) -> str:
    """
    处理用户查询消息

    支持的命令:
      - "查询xxx公司" / "xxx公司" → 搜索公司证照
      - "查看全部" / "所有记录" → 列出最近 10 条
      - "即将过期" / "临期" → 列出 30 天内过期
      - "统计" / "概况" → 数据统计概览
      - "帮助" / "help" → 显示帮助

    返回:
        格式化的回复文本（markdown 格式）
    """
    content = content.strip()

    # 帮助
    if content in ("帮助", "help", "功能", "?"):
        return _build_help_text()

    # 统计/概况
    if content in ("统计", "概况", "统计信息", "总览"):
        return _build_stats_text()

    # 即将过期
    if content in ("即将过期", "临期", "快过期", "expiring"):
        return _build_expiring_list_text()

    # 已过期
    if content in ("已过期", "过期的", "过期记录"):
        return _build_expired_list_text()

    # 所有记录
    if content in ("查看全部", "全部记录", "所有记录", "全部"):
        return _build_all_records_text()

    # 查询公司 — 匹配 "查询xxx" 或直接公司名
    keyword = content
    for prefix in ["查询", "搜索", "找", "查看"]:
        if content.startswith(prefix):
            keyword = content[len(prefix):].strip()
            break

    if keyword:
        return _build_company_search_text(keyword)

    return "请发送「帮助」查看可用命令"


def build_expiry_notification(days: int = 30) -> str:
    """
    构建每日效期提醒通知（markdown 格式）

    参数:
        days — 临近过期天数阈值
    """
    expiring = database.get_expiring_records(days)
    expired = database.get_expired_records()

    lines = [
        "# 📋 证照效期日报",
        "",
        f"> 生成时间：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 即将过期
    lines.append(f"## ⚠️ 即将过期（{len(expiring)} 条）")
    if expiring:
        for r in expiring:
            days_left = r.get("expire_days_remaining", "?")
            name = r.get("company_name", "未知")
            ltype = r.get("license_type", "")
            expire = r.get("expire_date", "未知")
            lines.append(f"- **{name}** {ltype}")
            lines.append(f"  - 到期: {expire}（剩余 {days_left} 天）")
    else:
        lines.append("- ✅ 暂无即将过期的证照")
    lines.append("")

    # 已过期
    if expired:
        lines.append(f"## ❌ 已过期（{len(expired)} 条）")
        for r in expired:
            name = r.get("company_name", "未知")
            expire = r.get("expire_date", "未知")
            days_over = abs(r.get("expire_days_remaining", 0))
            lines.append(f"- **{name}** 已于 {expire} 过期（超期 {days_over} 天）")
        lines.append("")

    lines.append("---")
    lines.append("💡 发送「查询+公司名」查看详细证照信息")
    lines.append("💡 发送「帮助」查看全部功能")

    return "\n".join(lines)


# ============================================================
# 内部构建函数
# ============================================================

def _build_help_text() -> str:
    return """**🤖 证照机器人使用指南**

**查询公司证照**
  `查询贵州益佰` — 搜索某公司的证照
  `贵州益佰` — 直接输入公司名也可

**列表查看**
  `即将过期` — 30 天内到期的证照
  `已过期` — 已过期的证照
  `全部` — 所有记录
  `统计` — 数据概况

**文件下载**
  查询结果中包含 **OSS 下载链接**，点击即可下载证照原图
  多个文件会同时提供多个链接

**每日提醒**
  每天 09:00 自动推送效期日报
"""


def _build_stats_text() -> str:
    stats = database.get_stats()
    return f"""**📊 证照数据概况**

- 总计: **{stats['total']}** 条证照记录
- ✅ 正常: {stats['valid']}
- ⚠️ 即将过期: {stats['expiring_soon']}
- ❌ 已过期: {stats['expired']}
- ❓ 未知: {stats['unknown']}
- 📦 导入批次: {stats['batches']}

💡 发送「即将过期」查看详情
"""


def _build_expiring_list_text() -> str:
    records = database.get_expiring_records(30)
    if not records:
        return "✅ 暂无 30 天内即将过期的证照"

    lines = ["**⚠️ 即将过期的证照（30 天内）**", ""]
    for r in records:
        lines.append(f"- **{r['company_name']}** ({r.get('license_type', '')})")
        lines.append(f"  到期: {r.get('expire_date', '')} 剩余 {r.get('expire_days_remaining', '?')} 天")
    lines.append("")
    lines.append('💡 发送「查询+公司名」查看详情和下载链接')
    return "\n".join(lines)


def _build_expired_list_text() -> str:
    records = database.get_expired_records()
    if not records:
        return "✅ 暂无已过期的证照"

    lines = ["**❌ 已过期的证照**", ""]
    for r in records:
        days_over = abs(r.get("expire_days_remaining", 0))
        lines.append(f"- **{r['company_name']}** ({r.get('license_type', '')})")
        lines.append(f"  已于 {r.get('expire_date', '')} 过期（超期 {days_over} 天）")
    lines.append("")
    lines.append('💡 发送「查询+公司名」查看详情和下载链接')
    return "\n".join(lines)


def _build_all_records_text() -> str:
    records = database.get_all_records(limit=10)
    if not records:
        return "📭 数据库中暂无证照记录"

    lines = ["**📋 最近 10 条证照记录**", ""]
    for r in records:
        status_icon = {"valid": "✅", "expiring_soon": "⚠️", "expired": "❌", "unknown": "❓"}
        icon = status_icon.get(r.get("expire_status", ""), "❓")
        name = r.get("company_name", "未知")
        expire = r.get("expire_date", "无")
        lines.append(f"- {icon} **{name}** 到期: {expire}")
    lines.append("")
    lines.append('💡 发送「查询+公司名」查看详情')
    return "\n".join(lines)


def _build_company_search_text(keyword: str) -> str:
    """搜索公司并返回详细结果"""
    records = database.search_records(keyword)

    if not records:
        return f"❌ 未找到包含「{keyword}」的证照记录"

    # 单条记录 → 详细结果
    if len(records) == 1:
        return _build_single_result(records[0])

    # 多条记录 → 列表 + 提示精确搜索
    lines = [f"📋 找到 **{len(records)}** 条匹配记录：", ""]
    for r in records:
        status_icon = {"valid": "✅", "expiring_soon": "⚠️", "expired": "❌", "unknown": "❓"}
        icon = status_icon.get(r.get("expire_status", ""), "❓")
        name = r.get("company_name", "未知")
        ltype = r.get("license_type", "") or "证照"
        expire = r.get("expire_date", "无")
        lines.append(f"- {icon} **{name}** — {ltype}（到期: {expire}）")
    lines.append("")
    lines.append("💡 输入更精确的公司名查看详细信息和下载链接")
    return "\n".join(lines)


def _build_single_result(record: dict) -> str:
    """构建单条记录的详细结果"""
    status_icon = {"valid": "✅", "expiring_soon": "⚠️", "expired": "❌", "unknown": "❓"}
    status = record.get("expire_status", "unknown")
    icon = status_icon.get(status, "❓")

    name = record.get("company_name", "未知")
    ltype = record.get("license_type", "未识别")
    credit = record.get("credit_code", "未识别")
    expire = record.get("expire_date", "未识别")
    days = record.get("expire_days_remaining", "?")
    legal = record.get("legal_person", "未识别")
    addr = record.get("address", "未识别")
    source_url = record.get("source_file_url", "")

    lines = [
        f"{icon} **{name}**",
        "",
        f"**证照类型:** {ltype}",
        f"**统一社会信用代码:** {credit}",
        f"**法定代表人:** {legal}",
        f"**住所:** {addr}",
    ]

    # 效期状态
    if status == "valid":
        lines.append(f"**有效截止日期:** {expire} ✅ 未过期（剩余 {days} 天）")
    elif status == "expiring_soon":
        lines.append(f"**有效截止日期:** {expire} ⚠️ 即将过期（剩余 {days} 天）")
    elif status == "expired":
        lines.append(f"**有效截止日期:** {expire} ❌ 已过期（超期 {abs(days)} 天）")
    else:
        lines.append(f"**有效截止日期:** {expire} ❓")

    # 文件下载
    if source_url:
        lines.append("")
        lines.append(f"**📎 证照文件:** [点击下载]({source_url})")

    lines.append("")
    lines.append("---")
    lines.append("💡 发送「查询+其他公司名」查看其他证照")
    return "\n".join(lines)
