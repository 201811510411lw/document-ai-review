"""标准证照类型映射表。

将 OCR 识别到的证照标题原文通过模糊匹配映射为标准证照类型名称，
与数据库存储的系统类型进行比对校验。

数据流：
  OCR 标题原文 → match_document_type() → 标准显示名
  数据库系统类型 (food_license) → SYSTEM_TO_DISPLAY → 标准显示名
  两者比较 → 校验通过/不通过
"""

from typing import Literal, TypedDict

# ─── 精确关键词映射表 ───────────────────────────────────────────────
# (关键词, 标准显示名, 系统类型)
# 按关键词长度降序排列，确保最长匹配优先
_RAW_MAP: list[tuple[str, str, str]] = [
    # ── 生产端（对应系统类型：food_production_license） ──
    ("特殊医学用途配方食品生产许可证", "食品生产许可证", "food_production_license"),
    ("婴幼儿配方食品生产许可证", "食品生产许可证", "food_production_license"),
    ("食品生产加工小作坊许可证", "食品生产许可证", "food_production_license"),
    ("仅销售预包装食品备案凭证", "食品经营许可证", "food_license"),
    ("仅销售预包装食品备案", "食品经营许可证", "food_license"),
    ("网络食品交易第三方平台备案", "食品经营许可证", "food_license"),
    ("食品添加剂生产许可证", "食品生产许可证", "food_production_license"),
    ("保健食品生产许可证", "食品生产许可证", "food_production_license"),
    ("食品经营许可证", "食品经营许可证", "food_license"),
    ("食品生产许可证", "食品生产许可证", "food_production_license"),
    ("食品小作坊登记证", "食品生产许可证", "food_production_license"),
    ("小餐饮经营许可证", "食品经营许可证", "food_license"),
    ("食品小经营店登记证", "食品经营许可证", "food_license"),
    ("小食杂店登记证", "食品经营许可证", "food_license"),
    ("小作坊登记证", "食品生产许可证", "food_production_license"),
    ("食品摊贩登记卡", "食品经营许可证", "food_license"),
    ("食品摊贩备案卡", "食品经营许可证", "food_license"),
]

# 按关键词长度降序排列（已在列表定义中保持顺序）
TITLE_KEYWORD_MAP: list[tuple[str, str, str]] = sorted(
    _RAW_MAP,
    key=lambda x: len(x[0]),
    reverse=True,
)

# ─── 系统类型 ↔ 显示名映射 ───────────────────────────────────────

SYSTEM_TO_DISPLAY: dict[str, str] = {
    "food_license": "食品经营许可证",
    "food_production_license": "食品生产许可证",
}

DISPLAY_TO_SYSTEM: dict[str, str] = {v: k for k, v in SYSTEM_TO_DISPLAY.items()}

# ─── 经营范围特征词 ────────────────────────────────────────────────

_PRODUCTION_SCOPE_KEYWORDS = frozenset({"生产", "加工", "制造"})
_OPERATION_SCOPE_KEYWORDS = frozenset({"销售", "餐饮", "服务", "经营"})

# ─── 类型定义 ──────────────────────────────────────────────────────


class DocumentTypeMatchResult(TypedDict, total=False):
    display_name: str
    system_type: str
    match_status: Literal["exact", "fuzzy", "ambiguous", "unknown", "fallback"]


# ─── 公开接口 ──────────────────────────────────────────────────────


def match_document_type(raw_text: str | None) -> str | None:
    """将 OCR 标题原文映射为标准证照类型显示名。

    只做精确关键词匹配和关键词模糊匹配，不涉及经营范围。
    返回标准显示名（如"食品经营许可证"），找不到返回 None。
    """
    if not raw_text:
        return None

    text = _normalize(raw_text)
    if not text:
        return None

    # 1) 精确关键词匹配（最长优先）
    for keyword, display_name, _ in TITLE_KEYWORD_MAP:
        if keyword in text:
            return display_name

    # 2) 模糊匹配规则
    has_生产 = "生产" in text
    has_许可或登记 = any(t in text for t in ("许可", "登记"))
    has_经营 = any(t in text for t in ("经营", "餐饮", "销售"))
    has_备案 = "备案" in text

    # 2a) 含"生产"且含"许可/登记" → 生产端
    if has_生产 and has_许可或登记:
        return "食品生产许可证"

    # 2b) 含"经营/餐饮/销售" → 经营端
    if has_经营:
        return "食品经营许可证"

    # 2c) 含"备案" → 经营端（备案类基本都属于经营端）
    if has_备案:
        return "食品经营许可证"

    # 2d) 仅含"登记"无其他关键词 → 需要经营范围判定
    if "登记" in text or "登记卡" in text:
        return None  # 调用方需提供经营范围

    return None


def resolve_document_type(
    raw_text: str | None,
    system_document_type: str | None = None,
    business_scope: str | None = None,
) -> DocumentTypeMatchResult:
    """完整解析：结合经营范围判定无法识别的登记类证照。"""
    if not raw_text:
        return _fallback_result(system_document_type)

    text = _normalize(raw_text)
    if not text:
        return _fallback_result(system_document_type)

    # 精确/模糊匹配
    display_name = match_document_type(text)
    if display_name:
        system_type = DISPLAY_TO_SYSTEM.get(display_name, "unknown")
        return DocumentTypeMatchResult(
            display_name=display_name,
            system_type=system_type,
            match_status="exact" if _is_exact_match(text, display_name) else "fuzzy",
        )

    # 仅含"登记" → 用经营范围判定
    if business_scope:
        scope = _normalize(business_scope)
        has_production = any(kw in scope for kw in _PRODUCTION_SCOPE_KEYWORDS)
        has_operation = any(kw in scope for kw in _OPERATION_SCOPE_KEYWORDS)

        if has_production and not has_operation:
            return DocumentTypeMatchResult(
                display_name="食品生产许可证",
                system_type="food_production_license",
                match_status="ambiguous",
            )
        if has_operation and not has_production:
            return DocumentTypeMatchResult(
                display_name="食品经营许可证",
                system_type="food_license",
                match_status="ambiguous",
            )

    return DocumentTypeMatchResult(
        display_name="未知",
        system_type="unknown",
        match_status="unknown",
    )


def system_to_display(system_type: str | None) -> str:
    """系统类型 → 显示名。"""
    return SYSTEM_TO_DISPLAY.get(system_type or "") or ""


def display_to_system(display_name: str | None) -> str:
    """显示名 → 系统类型。"""
    return DISPLAY_TO_SYSTEM.get(display_name or "") or ""


# ─── 内部辅助 ──────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """去空格、全角半角归一。"""
    return "".join(text.strip().split())


def _is_exact_match(text: str, display_name: str) -> bool:
    """判断是否为精确匹配（非模糊推断）。"""
    for keyword, dn, _ in TITLE_KEYWORD_MAP:
        if keyword in text and dn == display_name:
            # 关键词占文本大部分 → 精确
            if len(keyword) >= min(5, len(text)):
                return True
    return False


def _fallback_result(system_document_type: str | None) -> DocumentTypeMatchResult:
    """无原始标题时的降级结果。"""
    display = system_to_display(system_document_type)
    return DocumentTypeMatchResult(
        display_name=display or "未知",
        system_type=system_document_type or "unknown",
        match_status="fallback",
    )
