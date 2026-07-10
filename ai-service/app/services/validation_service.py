"""前端校验规则引擎。

将 LLM 审核输出的 rule_results 转换为前端 validation_fields 格式。
无 LLM 结果时使用 Python 字段比对作为降级方案。

校验规则来源：
  - 场景一：QC 证照及批次报告审核（需求文档 3.1）
  - 场景二：营业执照与烟草证一致性校验（需求文档 3.2）
  - .agents/skills/*.md 中定义的 LLM 审核规则

数据流：
  LLM rule_results  →  ValidationService  →  validation_fields（前端展示）
                                         →  verification_result（核验通过/未通过）
                                         →  match_ratio（匹配率）
"""

from datetime import date
from typing import Any


# ─── 规则代码 → 前端字段映射 ───────────────────────────────────────
# 注意：LLM 输出的 rule_code 同时存在带前缀和不带前缀的变体，
# 这里对同一字段含义的不同 code 映射到同一个 field 名，
# _from_rule_results 会按 field 名去重。

_RULE_CODE_FIELD_MAP: dict[str, dict[str, Any]] = {
    # ── 营业执照 ──
    "BUSINESS_LICENSE_DOCUMENT_TYPE": {
        "field": "证照类型",
        "category": "type",
        "required": True,
    },
    "BUSINESS_LICENSE_SUBJECT_NAME_MATCH": {
        "field": "主体名称",
        "category": "field",
        "required": True,
    },
    "BUSINESS_LICENSE_CREDIT_CODE_MATCH": {
        "field": "统一社会信用代码",
        "category": "field",
        "required": True,
    },
    "BUSINESS_LICENSE_VALID_TO_CHECK": {
        "field": "有效期",
        "category": "validity",
        "required": True,
    },
    "BUSINESS_LICENSE_KEY_FIELD_INTEGRITY": {
        "field": "关键字段完整性",
        "category": "integrity",
        "required": True,
    },
    "BUSINESS_LICENSE_EVIDENCE_REQUIRED": {
        "field": "OCR 证据完整性",
        "category": "evidence",
        "required": False,
    },
    # ── 食品经营许可证 ──
    "FOOD_LICENSE_TYPE_MATCH": {
        "field": "证照类型",
        "category": "type",
        "required": True,
    },
    "FOOD_LICENSE_SUBJECT_NAME_MATCH": {
        "field": "经营者名称",
        "category": "field",
        "required": True,
    },
    "SUBJECT_NAME_MATCH": {
        "field": "经营者名称",
        "category": "field",
        "required": True,
    },
    "FOOD_LICENSE_CREDIT_CODE_MATCH": {
        "field": "统一社会信用代码",
        "category": "field",
        "required": True,
    },
    "CREDIT_CODE_MATCH": {
        "field": "统一社会信用代码",
        "category": "field",
        "required": True,
    },
    "FOOD_LICENSE_VALIDITY_PERIOD": {
        "field": "有效期",
        "category": "validity",
        "required": True,
    },
    "VALIDITY_PERIOD_CHECK": {
        "field": "有效期",
        "category": "validity",
        "required": True,
    },
    # ── 食品生产许可证 ──
    "FOOD_PRODUCTION_LICENSE_TYPE_MATCH": {
        "field": "证照类型",
        "category": "type",
        "required": True,
    },
    "FOOD_PRODUCTION_LICENSE_PRODUCER_NAME_MATCH": {
        "field": "生产者名称",
        "category": "field",
        "required": True,
    },
    "PRODUCER_NAME_MATCH": {
        "field": "生产者名称",
        "category": "field",
        "required": True,
    },
    "FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH": {
        "field": "统一社会信用代码",
        "category": "field",
        "required": True,
    },
    "FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD": {
        "field": "有效期",
        "category": "validity",
        "required": True,
    },
    # ── 产品报告 ──
    "DOCUMENT_TYPE_MATCH": {
        "field": "文档类型",
        "category": "type",
        "required": True,
    },
    "PRODUCT_REPORT_TYPE_MATCH": {
        "field": "文档类型",
        "category": "type",
        "required": True,
    },
    "VENDOR_NAME_MATCH": {
        "field": "供应商名称",
        "category": "field",
        "required": True,
    },
    "PRODUCT_REPORT_VENDOR_NAME_MATCH": {
        "field": "供应商名称",
        "category": "field",
        "required": True,
    },
    "PRODUCT_NAME_MATCH": {
        "field": "产品名称",
        "category": "field",
        "required": True,
    },
    "PRODUCT_REPORT_PRODUCT_NAME_MATCH": {
        "field": "产品名称",
        "category": "field",
        "required": True,
    },
    "BATCH_OR_PRODUCTION_DATE_PRESENT": {
        "field": "批次/生产日期",
        "category": "field",
        "required": True,
    },
    "PRODUCT_REPORT_BATCH_OR_DATE": {
        "field": "批次/生产日期",
        "category": "field",
        "required": True,
    },
    "PRODUCT_REPORT_CONCLUSION_PASS": {
        "field": "检验结论",
        "category": "conclusion",
        "required": True,
    },
    # ── 商品批次报告 ──
    "BATCH_REPORT_TEXT_PRESENT": {
        "field": "文档文本",
        "category": "evidence",
        "required": True,
    },
    "BATCH_REPORT_TYPE_MATCH": {
        "field": "文档类型",
        "category": "type",
        "required": True,
    },
    "BATCH_REPORT_PRODUCT_NAME_MATCH": {
        "field": "商品名称",
        "category": "field",
        "required": True,
    },
    "BATCH_REPORT_PRODUCER_NAME_MATCH": {
        "field": "生产者名称",
        "category": "field",
        "required": True,
    },
    "BATCH_REPORT_PRODUCTION_DATE_MATCH": {
        "field": "生产日期/批号",
        "category": "field",
        "required": True,
    },
    "BATCH_REPORT_EXPIRY_CHECK": {
        "field": "生产日期时效性",
        "category": "validity",
        "required": True,
    },
    "BATCH_REPORT_KEY_FIELD_INTEGRITY": {
        "field": "关键字段完整性",
        "category": "integrity",
        "required": True,
    },
    # ── 烟草证 ──
    "TOBACCO_LICENSE_TYPE_MATCH": {
        "field": "证照类型",
        "category": "type",
        "required": True,
    },
    # ── 烟草证一致性 ──
    "TOBACCO_CONSISTENCY_TYPE_MATCH": {
        "field": "证照类型",
        "category": "type",
        "required": True,
    },
    "TOBACCO_CONSISTENCY_NAME_MATCH": {
        "field": "企业名称",
        "category": "field",
        "required": True,
    },
    "TOBACCO_CONSISTENCY_ADDRESS_MATCH": {
        "field": "经营场所",
        "category": "field",
        "required": True,
    },
    "TOBACCO_CONSISTENCY_LEGAL_PERSON_MATCH": {
        "field": "负责人",
        "category": "field",
        "required": True,
    },
    "TOBACCO_CONSISTENCY_VALIDITY": {
        "field": "有效期",
        "category": "validity",
        "required": True,
    },
}

# ─── 字段规格定义（降级比对用） ───────────────────────────────────

_VALIDATION_FIELD_SPECS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "business_license": [
        ("证照类型", ("document_type",)),
        ("主体名称", ("subject_name",)),
        ("统一社会信用代码", ("credit_code",)),
        ("法定代表人", ("legal_person",)),
        ("有效期开始", ("valid_from", "established_date", "issue_date")),
        ("有效期结束", ("valid_to",)),
        ("住所", ("business_address",)),
    ],
    "food_license": [
        ("证照类型", ("document_type",)),
        ("经营者名称", ("subject_name",)),
        ("统一社会信用代码", ("credit_code",)),
        ("许可证编号", ("license_no",)),
        ("经营场所", ("business_address",)),
        ("法定代表人/负责人", ("legal_person",)),
        ("经营项目", ("business_items",)),
        ("有效期开始", ("valid_from",)),
        ("有效期结束", ("valid_to",)),
        ("发证机关", ("issue_authority",)),
        ("签发日期", ("issue_date",)),
    ],
    "food_production_license": [
        ("证照类型", ("document_type",)),
        ("生产者名称", ("producer_name",)),
        ("统一社会信用代码", ("credit_code",)),
        ("许可证编号", ("license_no",)),
        ("生产地址", ("production_address",)),
        ("法定代表人/负责人", ("legal_person",)),
        ("食品类别", ("food_categories",)),
        ("有效期开始", ("valid_from",)),
        ("有效期结束", ("valid_to",)),
        ("发证机关", ("issue_authority",)),
        ("签发日期", ("issue_date",)),
    ],
    "product_report": [
        ("文档类型", ("document_type",)),
        ("报告编号", ("report_no",)),
        ("样品名称", ("sample_name", "product_name")),
        ("委托单位", ("entrusting_party", "vendor_name_extracted")),
        ("生产商", ("manufacturer_name",)),
        ("批号", ("batch_no",)),
        ("生产日期", ("production_date",)),
        ("签发日期", ("issue_date", "sign_date")),
        ("批准日期", ("approval_date",)),
        ("有效截止日", ("issue_date", "sign_date")),
        ("检验结论", ("inspection_conclusion", "inspection_result")),
    ],
    "batch_report": [
        ("文档类型", ("document_type",)),
        ("商品名称", ("product_name",)),
        ("生产者名称", ("producer_name", "company_name")),
        ("生产日期", ("production_date",)),
        ("生产批号", ("batch_no",)),
    ],
    "tobacco_license": [
        ("证照类型", ("document_type",)),
        ("企业名称", ("subject_name",)),
        ("许可证编号", ("license_no",)),
        ("有效期开始", ("valid_from",)),
        ("有效期结束", ("valid_to",)),
        ("经营场所", ("business_address",)),
        ("法定代表人", ("legal_person",)),
    ],
    "business_tobacco_consistency": [
        ("证照类型", ("document_type",)),
        ("企业名称", ("subject_name",)),
        ("经营场所", ("business_address",)),
        ("负责人", ("legal_person",)),
        ("有效期", ("valid_to",)),
    ],
}

_DATE_KEYS = {
    "valid_from",
    "valid_to",
    "issue_date",
    "sign_date",
    "approval_date",
    "production_date",
    "established_date",
}

_SOURCE_FIELD_KEYS = {
    "subject_name",
    "producer_name",
    "entrusting_party",
    "manufacturer_name",
    "product_name",
    "production_date",
    "credit_code",
}

# ─── 公开接口 ─────────────────────────────────────────────────────


def compute_validation_fields(
    detail: dict[str, Any],
    document_type: str = "",
) -> list[dict[str, Any]]:
    """计算校验字段列表，供前端展示。

    以 _VALIDATION_FIELD_SPECS 定义的字段清单为基础，
    有 rule_results 时在其上叠加覆盖，确保所有字段都能展示。
    """
    # 1) 先拿字段规格清单作为基线
    fields = _field_comparison(detail, document_type)
    seen_fields: set[str] = {f["field"] for f in fields}

    # 2) 有 LLM 规则结果时，叠加覆盖
    rule_results = detail.get("rule_results") or []
    if rule_results:
        rule_fields = _from_rule_results(rule_results, detail)
        for rf in rule_fields:
            field_name = rf["field"]
            if field_name in seen_fields:
                # 更新已有项（rule_results 有值的才覆盖）
                for i, f in enumerate(fields):
                    if f["field"] == field_name:
                        if rf.get("recognized") or rf.get("expected"):
                            fields[i].update(
                                {k: v for k, v in rf.items() if v is not None and v != ""}
                            )
                        break
            else:
                fields.append(rf)
                seen_fields.add(field_name)
    return fields


def compute_verification_result(
    validation_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """计算综合核验结果。

    返回:
      {"result": "pass"|"fail", "summary": "...", "failed_items": [...]}
    """
    if not validation_fields:
        return {"result": "unknown", "summary": "无校验项", "failed_items": []}

    failed = [f for f in validation_fields if not f.get("match")]
    required_failed = [f for f in failed if f.get("required")]

    if not required_failed:
        return {
            "result": "pass",
            "summary": "所有必要校验项已通过",
            "failed_items": [],
        }

    return {
        "result": "fail",
        "summary": f"存在 {len(required_failed)} 项校验不通过",
        "failed_items": [
            {
                "field": f["field"],
                "reason": _fail_reason(f),
            }
            for f in required_failed
        ],
    }


def compute_match_ratio(
    data: dict[str, Any] | list[dict[str, Any]],
    risk_level: str = "",
) -> int:
    """计算匹配率。

    参数可以是带 rule_results 的 detail dict，也可以是 validation_fields 列表。
    """
    # 优先从 rule_results 计算
    rule_results = data.get("rule_results") if isinstance(data, dict) else None
    if rule_results:
        total = len(rule_results)
        if total == 0:
            return _risk_to_match_ratio(risk_level)
        passed = sum(1 for r in rule_results if r.get("passed") is True)
        return round((passed / total) * 100)

    # 从 validation_fields 计算
    fields = data if isinstance(data, list) else []
    if not fields:
        return _risk_to_match_ratio(risk_level)
    # 统一按全部字段计算匹配率：matched / total * 100
    total = len(fields)
    matched = sum(1 for f in fields if f.get("match") is True)
    return round((matched / total) * 100)


def compute_field_coverage(fields: list[dict[str, Any]]) -> dict[str, int]:
    """计算字段覆盖率（有多少字段识别出了值 vs 总字段数）。"""
    total = len(fields)
    covered = sum(1 for f in fields if f.get("recognized"))
    return {
        "total": total,
        "covered": covered,
        "coverage": round((covered / total) * 100) if total > 0 else 0,
    }


# ─── 规则结果转换 ────────────────────────────────────────────────


def _from_rule_results(
    rule_results: list[dict[str, Any]],
    detail: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """将 LLM rule_results 转换为前端 validation_fields 格式，按 field 名去重。

    当 rule_results 中 lack details.actual/expected 时，从 detail 中的
    extracted_fields / normalized_fields 回填。
    """
    extracted = dict((detail or {}).get("extracted_fields") or {})
    normalized = dict((detail or {}).get("normalized_fields") or {})
    source = _source_fallback_fields(detail)

    seen_fields: set[str] = set()
    fields: list[dict[str, Any]] = []
    for rule in rule_results:
        rule_code = str(rule.get("rule_code") or "")
        details = rule.get("details") or {}
        spec = _RULE_CODE_FIELD_MAP.get(rule_code)
        if not spec:
            field_name = rule.get("rule_name") or rule_code
            if field_name in seen_fields:
                continue
            seen_fields.add(field_name)
            actual = _rule_detail_value(rule, "actual")
            expected = _rule_detail_value(rule, "expected")
            if not actual:
                actual = _lookup_field_value(extracted, normalized, field_name)
            if not expected:
                expected = source.get(field_name, "")
            fields.append(
                {
                    "field": field_name,
                    "recognized": actual,
                    "expected": expected,
                    "match": bool(rule.get("passed", False)),
                    "risk": rule.get("risk_level_on_failure") or "",
                    "required": True,
                    "missing_recognized": not actual,
                    "missing_expected": not expected,
                    "match_reason": details.get("match_reason") or "",
                    "confidence": details.get("confidence") or "",
                }
            )
            continue

        field_name = spec["field"]
        if field_name in seen_fields:
            continue
        seen_fields.add(field_name)

        actual = _rule_detail_value(rule, "actual")
        expected = _rule_detail_value(rule, "expected")
        # rule_results 中缺值则从 extracted/source 回填
        if not actual:
            actual = _lookup_field_value(extracted, normalized, field_name)
        if not expected:
            expected = source.get(field_name, "")

        # 证照类型字段：英文系统类型 → 中文显示名
        if field_name in ("证照类型", "文档类型"):
            # "unknown" 是 _normalize_document_type 对空值的旧有 fallback，
            # 已存数据中可能还有，统一按空值处理
            if actual and actual.strip().lower() == "unknown":
                actual = ""
            if expected and expected.strip().lower() == "unknown":
                expected = ""
            from app.capabilities.document_type_mapping import system_to_display
            if actual and not _is_chinese(actual):
                actual = system_to_display(actual) or actual
            if expected and not _is_chinese(expected):
                expected = system_to_display(expected) or expected

        passed = bool(rule.get("passed", False))
        risk = rule.get("risk_level_on_failure") or ""

        fields.append(
            {
                "field": field_name,
                "recognized": actual,
                "expected": expected,
                "match": passed,
                "risk": risk if not passed else "",
                "required": spec.get("required", True),
                "missing_recognized": not actual,
                "missing_expected": not expected,
                "match_reason": details.get("match_reason") or "",
                "confidence": details.get("confidence") or "",
                "_rule_code": rule_code,
                "_category": spec.get("category", ""),
            }
        )
    return fields


def _source_fallback_fields(detail: dict[str, Any] | None) -> dict[str, str]:
    """从 detail 中提取 source 字段用于回填 rule_results 中缺省的 expected 值。"""
    if not detail:
        return {}
    source_evidence = dict(detail.get("source_evidence") or {})
    source = source_evidence.get("source") if isinstance(source_evidence.get("source"), dict) else {}
    source_fields = (
        source_evidence.get("source_fields")
        if isinstance(source_evidence.get("source_fields"), dict)
        else {}
    )
    supplier_name = str(source_evidence.get("supplier_name") or "")
    source_supplier_name = str(
        source_fields.get("supplier_name")
        or source_fields.get("vendor_name")
        or source.get("vendor_name")
        or supplier_name
        or ""
    )
    source_product_name = str(source_fields.get("sku_name") or source.get("sku_name") or "")
    source_production_date = str(
        source_fields.get("production_date") or source.get("production_date") or ""
    )
    return {
        "主体名称": supplier_name,
        "经营者名称": supplier_name,
        "生产者名称": source_supplier_name,
        "供应商名称": supplier_name,
        "企业名称": supplier_name,
        "商品名称": source_product_name,
        "产品名称": source_product_name,
        "生产日期/批号": source_production_date,
        "生产日期": source_production_date,
        "统一社会信用代码": str(source_evidence.get("supplier_credit_code") or ""),
        "许可证编号": str(source_evidence.get("license_no") or ""),
        "经营场所": str(source_evidence.get("business_address") or supplier_name),
        "负责人": str(source_evidence.get("legal_person") or ""),
        "法定代表人": str(source_evidence.get("legal_person") or ""),
    }


def _lookup_field_value(
    extracted: dict[str, Any],
    normalized: dict[str, Any],
    field_name: str,
) -> str:
    """根据前端字段名在 extracted/normalized 中查找对应值。"""
    key_map = {
        "主体名称": "subject_name",
        "经营者名称": "subject_name",
        "生产者名称": "producer_name",
        "供应商名称": "entrusting_party",
        "企业名称": "subject_name",
        "统一社会信用代码": "credit_code",
        "许可证编号": "license_no",
        "经营场所": "business_address",
        "负责人": "legal_person",
        "法定代表人": "legal_person",
        "有效期": "valid_to",
        "报告有效期": "valid_to",
        "有效期开始": "valid_from",
        "有效期结束": "valid_to",
        "证照类型": "__document_type__",
        "文档类型": "document_type",
        "产品名称": "product_name",
        "商品名称": "product_name",
        "样品名称": "sample_name",
        "检验结论": "inspection_conclusion",
        "批号": "batch_no",
        "生产日期/批号": "production_date",
        "生产日期": "production_date",
        "签发日期": "issue_date",
    }
    key = key_map.get(field_name)
    if not key:
        return ""
    # __document_type__ 特殊处理：通过映射表返回显示名
    if key == "__document_type__":
        raw_title = extracted.get("document_type_raw") or ""
        if raw_title:
            from app.capabilities.document_type_mapping import match_document_type
            return match_document_type(raw_title) or "未知"
        # 无原始标题 → 用系统值映射到显示名
        sys_type = str(extracted.get("document_type") or normalized.get("document_type") or "").strip().lower()
        # "unknown" 是 _normalize_document_type 旧有 fallback，按空值处理
        if sys_type == "unknown":
            sys_type = ""
        from app.capabilities.document_type_mapping import SYSTEM_TO_DISPLAY
        return SYSTEM_TO_DISPLAY.get(sys_type) or sys_type or ""
    # 优先从 normalized 取，再 fallback 到 extracted
    value = normalized.get(key) or extracted.get(key)
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(str(v) for v in value if v)
    return str(value).strip()


def _rule_detail_value(rule: dict[str, Any], key: str) -> str:
    """安全地从 rule_result.details 取字段值。"""
    details = rule.get("details") or {}
    value = details.get(key)
    if value is None:
        return ""
    return str(value).strip()


# ─── 字段比对降级（无 LLM 规则结果时使用） ──────────────────────


def _field_comparison(
    detail: dict[str, Any],
    document_type: str,
) -> list[dict[str, Any]]:
    """字段级比对降级方案。"""
    extracted = dict(detail.get("extracted_fields") or {})
    normalized = dict(detail.get("normalized_fields") or {})
    source = _source_validation_fields(detail)
    specs = _VALIDATION_FIELD_SPECS.get(document_type) or _VALIDATION_FIELD_SPECS[
        "business_license"
    ]

    fields: list[dict[str, Any]] = []
    for label, keys in specs:
        recognized = _recognized_value(extracted, normalized, keys)
        expected = _first_field_value(source, keys)

        # 非来源字段使用 normalized 作为兜底
        if expected is None and not _is_source_field(keys):
            expected = _first_field_value(normalized, keys)

        required = _is_required_field(document_type, keys)
        missing_rec = not _display_value(recognized)
        missing_exp = _is_source_field(keys) and not _display_value(expected)

        # 对已存数据中 "unknown" 字面值的防御（_normalize_document_type 旧有 fallback）
        if "document_type" in keys:
            recognized_str = _display_value(recognized)
            if recognized_str.lower() == "unknown":
                recognized = None
            from app.capabilities.document_type_mapping import match_document_type, SYSTEM_TO_DISPLAY

            raw_title = extracted.get("document_type_raw") or ""
            if raw_title:
                # 用原始标题 → 显示名
                recognized_display = match_document_type(raw_title) or "未知"
                # 数据库系统类型 → 显示名
                db_doc_type = detail.get("document_type") or document_type
                if db_doc_type and str(db_doc_type).strip().lower() == "unknown":
                    db_doc_type = document_type
                expected_display = SYSTEM_TO_DISPLAY.get(db_doc_type) or ""
                match = recognized_display == expected_display if expected_display else False
                recognized = recognized_display
                expected = expected_display or _display_value(expected)
            else:
                # 无原始标题 → 用系统值映射显示名
                db_doc_type = detail.get("document_type") or document_type
                if db_doc_type and str(db_doc_type).strip().lower() == "unknown":
                    db_doc_type = document_type
                expected_display = SYSTEM_TO_DISPLAY.get(db_doc_type) or ""
                recognized_display = SYSTEM_TO_DISPLAY.get(str(recognized).lower()) or ""
                if recognized_display and expected_display:
                    recognized = recognized_display
                    expected = expected_display
                    match = recognized_display == expected_display
                else:
                    match = str(recognized).lower() == str(expected).lower() if recognized and expected else False
        elif _is_date_key(keys):
            match = _normalize_date(recognized) == _normalize_date(expected) if recognized and expected else False
        elif _is_name_key(keys):
            match = _normalize_name(recognized) == _normalize_name(expected) if recognized and expected else False
        else:
            match = _display_value(recognized) == _display_value(expected)

        fields.append(
            {
                "field": label,
                "recognized": _display_value(recognized),
                "expected": _display_value(expected),
                "match": match,
                "risk": _field_risk(keys, recognized),
                "required": required,
                "missing_recognized": missing_rec,
                "missing_expected": missing_exp,
            }
        )
    return fields


def _source_validation_fields(detail: dict[str, Any]) -> dict[str, Any]:
    """从 source_evidence 提取来源系统字段。"""
    source_evidence = dict(detail.get("source_evidence") or {})
    source = {}
    if isinstance(source_evidence.get("source"), dict):
        source = source_evidence["source"]
    source_fields = {}
    if isinstance(source_evidence.get("source_fields"), dict):
        source_fields = source_evidence["source_fields"]
    supplier_name = source_evidence.get("supplier_name") or ""
    source_supplier_name = (
        source_fields.get("supplier_name")
        or source_fields.get("vendor_name")
        or source.get("vendor_name")
        or supplier_name
        or ""
    )
    credit_code = source_evidence.get("supplier_credit_code") or ""
    if not credit_code and isinstance(source.get("source_payload"), dict):
        payload = source["source_payload"]
        for key in ("creditCode", "credit_code", "unifiedSocialCreditCode", "num"):
            code = payload.get(key) or ""
            if _normalize_credit_code(code):
                credit_code = _normalize_credit_code(code)
                break
    return {
        "subject_name": supplier_name,
        "producer_name": source_supplier_name,
        "company_name": source_supplier_name,
        "entrusting_party": supplier_name,
        "manufacturer_name": supplier_name,
        "product_name": source_fields.get("sku_name") or source.get("sku_name"),
        "production_date": source_fields.get("production_date") or source.get("production_date"),
        "credit_code": credit_code,
    }


# ─── 辅助函数 ─────────────────────────────────────────────────────


def _display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_display_value(v) for v in value if _display_value(v))
    if isinstance(value, dict):
        return "、".join(_display_value(v) for v in value.values() if _display_value(v))
    return str(value).strip()


def _first_field_value(fields: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = fields.get(key)
        if _display_value(value):
            return value
    return None


def _recognized_value(
    extracted: dict[str, Any],
    normalized: dict[str, Any],
    keys: tuple[str, ...],
) -> Any:
    if _is_date_key(keys):
        nv = _first_field_value(normalized, keys)
        if nv is not None:
            return nv
    return _first_field_value(extracted, keys)


def _is_source_field(keys: tuple[str, ...]) -> bool:
    return any(k in _SOURCE_FIELD_KEYS for k in keys)


def _is_date_key(keys: tuple[str, ...]) -> bool:
    return any(k in _DATE_KEYS for k in keys)


def _is_name_key(keys: tuple[str, ...]) -> bool:
    return any(
        k in {"subject_name", "producer_name", "company_name", "entrusting_party", "manufacturer_name", "product_name"}
        for k in keys
    )


def _field_risk(keys: tuple[str, ...], recognized: Any) -> str:
    if "valid_to" in keys:
        status = _valid_to_status(recognized)
        if status in ("expired", "expiring_soon"):
            return status
    return ""


def _is_required_field(document_type: str, keys: tuple[str, ...]) -> bool:
    if document_type == "food_production_license":
        required = {
            "producer_name", "credit_code", "license_no",
            "production_address", "legal_person", "food_categories", "valid_to",
        }
        return any(k in required for k in keys)
    if document_type == "food_license":
        required = {
            "subject_name", "credit_code", "license_no",
            "business_address", "legal_person", "business_items", "valid_to",
        }
        return any(k in required for k in keys)
    if document_type == "product_report":
        required = {
            "report_no", "product_name", "sample_name",
            "entrusting_party", "manufacturer_name",
            "batch_no", "production_date", "issue_date",
            "approval_date", "valid_to", "inspection_conclusion",
        }
        return any(k in required for k in keys)
    if document_type == "batch_report":
        required = {"document_type", "product_name", "producer_name", "company_name", "production_date"}
        return any(k in required for k in keys)
    return False


def _fail_reason(field: dict[str, Any]) -> str:
    parts = []
    if field.get("missing_recognized"):
        parts.append("未识别到该字段")
    if field.get("missing_expected"):
        parts.append("来源系统无此字段")
    if not parts and not field.get("match"):
        parts.append("识别值与数据库不一致")
    return "；".join(parts) if parts else "校验不通过"


def _normalize_date(value: Any) -> str:
    text = _display_value(value)
    if not text:
        return ""
    n = text.strip()
    for suffix in ("日", "号"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    n = n.replace("年", "-").replace("月", "-").replace("/", "-").replace(".", "-")
    parts = [p for p in n.split("-") if p]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        y, m, d = parts
        if len(y) == 4:
            return f"{y}-{int(m):02d}-{int(d):02d}"
    return text


def _normalize_name(value: Any) -> str:
    text = _display_value(value)
    punct = set("()（）[]【】,，.。;；:：-—_·'\"“”‘’")
    return "".join(c for c in text if c not in punct)


def _normalize_credit_code(value: Any) -> str:
    text = "".join(str(value or "").split()).upper()
    return text if len(text) in (15, 18) else ""


def _valid_to_status(value: Any) -> str:
    normalized = _normalize_date(value)
    if not normalized:
        return "unknown"
    if "长期" in normalized:
        return "valid"
    try:
        d = date.fromisoformat(normalized)
    except ValueError:
        return "invalid"
    remaining = (d - date.today()).days
    if remaining < 0:
        return "expired"
    if remaining <= 30:
        return "expiring_soon"
    return "valid"


def _risk_to_match_ratio(risk_level: str) -> int:
    return {
        "HIGH": 45,
        "MEDIUM": 72,
        "LOW": 96,
    }.get(str(risk_level).strip().upper(), 96)


def _is_chinese(text: str) -> bool:
    """判断字符串是否包含中文字符"""
    if not text:
        return False
    return any('一' <= c <= '鿿' for c in text)
