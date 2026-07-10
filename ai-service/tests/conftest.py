from datetime import date

import pytest


def pytest_configure():
    import os

    os.environ.setdefault("REVIEW_RESULT_MYSQL_HOST", "127.0.0.1")
    os.environ.setdefault("REVIEW_RESULT_MYSQL_PORT", "3306")
    os.environ.setdefault("REVIEW_RESULT_MYSQL_USER", "review")
    os.environ.setdefault("REVIEW_RESULT_MYSQL_PASSWORD", "secret")
    os.environ.setdefault("REVIEW_RESULT_MYSQL_DATABASE", "document_ai_review")


from app.models import RiskLevel, RuleResult
from app.tools.vision_adapter import FakeVisionAdapter
from app.workflows.business_license import nodes as business_license_nodes
from app.workflows.food_license import nodes as food_license_nodes
from app.workflows.food_production_license import nodes as food_production_license_nodes
from app.workflows.qc_document import workflow as qc_document_workflow


@pytest.fixture(autouse=True)
def use_fake_review_adapters(monkeypatch):
    adapter = DynamicSkillRuleReviewAdapter()
    monkeypatch.setattr(
        business_license_nodes,
        "business_license_vision_adapter",
        FakeVisionAdapter(),
    )
    monkeypatch.setattr(
        business_license_nodes,
        "business_license_skill_rule_review_adapter",
        adapter,
    )
    monkeypatch.setattr(
        food_license_nodes,
        "food_license_skill_rule_review_adapter",
        adapter,
    )
    monkeypatch.setattr(
        food_production_license_nodes,
        "food_production_license_skill_rule_review_adapter",
        adapter,
    )
    monkeypatch.setattr(
        qc_document_workflow,
        "qc_document_skill_rule_review_adapter",
        adapter,
    )


class DynamicSkillRuleReviewAdapter:
    def review(self, *, skill_name, skill_text, review_payload):
        if skill_name == "business-license-review":
            return _review_business(skill_name, review_payload)
        if skill_name == "food-license-review":
            return _review_food(skill_name, review_payload)
        if skill_name == "food-production-license-review":
            return _review_food_production(skill_name, review_payload)
        if skill_name == "qc-document-review":
            declared = (review_payload.get("declared_document_type") or "").strip().lower()
            if declared == "batch_report":
                return _review_batch_report(skill_name, review_payload)
            return _review_product_report(skill_name, review_payload)
        raise AssertionError(f"unexpected skill rule review call: {skill_name}")


def _review_business(skill_name, payload):
    fields = payload.get("extracted_fields") or {}
    source = payload.get("source_fields") or {}
    rules = [
        _rule("BUSINESS_LICENSE_TYPE_MATCH", "营业执照类型匹配", payload.get("document_type") == "business_license", RiskLevel.HIGH, {"expected": "business_license", "actual": payload.get("document_type")}),
        _rule("BUSINESS_LICENSE_SUBJECT_NAME_MATCH", "营业执照主体名称匹配", _same(fields.get("subject_name"), source.get("supplier_name")), RiskLevel.MEDIUM, {"field": "subject_name", "expected": source.get("supplier_name"), "actual": fields.get("subject_name")}),
        _rule("BUSINESS_LICENSE_CREDIT_CODE_MATCH", "统一社会信用代码匹配", _same_code(fields.get("credit_code"), source.get("supplier_credit_code")) and len(_text(fields.get("credit_code"))) in {15, 18}, RiskLevel.HIGH, {"field": "credit_code", "expected": source.get("supplier_credit_code"), "actual": fields.get("credit_code")}),
        _business_key_field_evidence(fields),
        _business_validity(fields.get("valid_to")),
    ]
    return _result(skill_name, rules, "营业执照规则校验通过", "营业执照存在需要人工复核的规则问题")


def _review_food(skill_name, payload):
    fields = payload.get("extracted_fields") or {}
    source = payload.get("source_fields") or {}
    rules = [
        _rule("FOOD_LICENSE_RULE_ENGINE_STUB", "food_license Skill 规则审核接入占位规则", True, RiskLevel.LOW, {"document_type": payload.get("document_type")}),
        _rule("FOOD_LICENSE_TYPE_MATCH", "证照类型是否为食品经营许可证", payload.get("document_type") == "food_license", RiskLevel.HIGH, {"field": "document_type", "expected": "food_license", "actual": payload.get("document_type")}),
        _rule("FOOD_LICENSE_SUBJECT_NAME_MATCH", "主体名称是否匹配供应商名称", _same(fields.get("subject_name"), source.get("supplier_name")), RiskLevel.MEDIUM if fields.get("subject_name") else RiskLevel.NONE, {"field": "subject_name", "expected": source.get("supplier_name"), "actual": fields.get("subject_name")}),
        _rule("FOOD_LICENSE_CREDIT_CODE_MATCH", "统一社会信用代码是否匹配", _same_code(fields.get("credit_code"), source.get("supplier_credit_code")), RiskLevel.HIGH if fields.get("credit_code") else RiskLevel.NONE, {"field": "credit_code", "expected": source.get("supplier_credit_code"), "actual": fields.get("credit_code")}),
        _food_validity(fields.get("valid_to"), payload.get("current_date")),
    ]
    return _result(skill_name, rules, "食品经营许可证规则校验通过", "食品经营许可证存在需要人工复核的规则问题")


def _review_food_production(skill_name, payload):
    fields = payload.get("extracted_fields") or {}
    source = payload.get("source_fields") or {}
    rules = [
        _rule("FOOD_PRODUCTION_LICENSE_TYPE_MATCH", "证照类型是否为食品生产许可证", payload.get("document_type") == "food_production_license", RiskLevel.HIGH, {"field": "document_type", "expected": "food_production_license", "actual": payload.get("document_type")}),
        _rule("FOOD_PRODUCTION_LICENSE_PRODUCER_NAME_MATCH", "生产者名称是否匹配供应商名称", _same(fields.get("producer_name"), source.get("supplier_name")), RiskLevel.MEDIUM if fields.get("producer_name") else RiskLevel.NONE, {"field": "producer_name", "expected": source.get("supplier_name"), "actual": fields.get("producer_name")}),
        _rule("FOOD_PRODUCTION_LICENSE_CREDIT_CODE_MATCH", "统一社会信用代码是否匹配", _same_code(fields.get("credit_code"), source.get("supplier_credit_code")), RiskLevel.HIGH if fields.get("credit_code") else RiskLevel.NONE, {"field": "credit_code", "expected": source.get("supplier_credit_code"), "actual": fields.get("credit_code")}),
        _food_production_validity(fields.get("valid_to"), payload.get("current_date")),
    ]
    return _result(skill_name, rules, "食品生产许可证规则校验通过", "食品生产许可证存在需要人工复核的规则问题")


def _review_product_report(skill_name, payload):
    fields = payload.get("extracted_fields") or {}
    source = payload.get("source_fields") or {}
    vendor = fields.get("vendor_name_extracted") or fields.get("entrusting_party") or fields.get("manufacturer_name")
    product = fields.get("product_name") or fields.get("sample_name")
    conclusion = fields.get("inspection_conclusion") or fields.get("inspection_result")
    negative = any(token in _text(conclusion) for token in ("不合格", "不通过", "不符合"))
    positive = any(token in _text(conclusion) for token in ("合格", "通过", "符合")) and not negative
    rules = [
        _rule("PRODUCT_REPORT_TYPE_MATCH", "产品检验报告类型匹配", payload.get("declared_document_type") == "product_report", RiskLevel.HIGH, {"expected": "product_report", "actual": payload.get("declared_document_type")}),
        _rule("PRODUCT_REPORT_VENDOR_NAME_MATCH", "供应商名称匹配", bool(vendor) and _same(vendor, source.get("supplier_name")), RiskLevel.MEDIUM, {"field": "vendor_name", "expected": source.get("supplier_name"), "actual": vendor}),
        _rule("PRODUCT_REPORT_PRODUCT_NAME_PRESENT", "产品名存在", bool(product), RiskLevel.MEDIUM, {"field": "product_name", "actual": product}),
        _rule("PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT", "批次或生产日期存在", bool(fields.get("batch_no") or fields.get("production_date")), RiskLevel.MEDIUM, {"batch_number": fields.get("batch_no"), "production_date": fields.get("production_date")}),
        _product_report_validity(fields.get("valid_to")),
        _rule("PRODUCT_REPORT_CONCLUSION_PASS", "结论正向/负向/不明确", positive, RiskLevel.HIGH if negative else RiskLevel.MEDIUM, {"conclusion": conclusion}),
    ]
    return _result(skill_name, rules, "产品检验报告规则校验通过", "产品检验报告存在高风险规则问题" if negative else "产品检验报告存在需要人工复核的规则问题")


def _review_batch_report(skill_name, payload):
    fields = payload.get("extracted_fields") or {}
    source = payload.get("source_fields") or {}
    has_text = bool(fields.get("has_document_text"))
    producer = fields.get("producer_name") or fields.get("company_name")
    product = fields.get("product_name")
    production_date = fields.get("production_date")
    batch_no = fields.get("batch_no")
    source_supplier = source.get("supplier_name") or source.get("vendor_name")
    source_product = source.get("sku_name")
    source_production_date = _text(source.get("production_date"))[:10] if source.get("production_date") else ""
    declared_type = payload.get("declared_document_type")
    expired_time = source.get("expired_time")
    today = date.today().isoformat()

    # 生产日期匹配
    date_match = bool(production_date and source_production_date and production_date == source_production_date)
    if not date_match and batch_no and source_production_date:
        digits = "".join(c for c in _text(batch_no) if c.isdigit())
        date_digits = source_production_date.replace("-", "")
        date_match = bool(date_digits and date_digits in digits)

    # 名称匹配
    name_match = lambda a, b: bool(a and b and _text(a) == _text(b))
    product_match = name_match(product, source_product)
    producer_match = name_match(producer, source_supplier)

    # 关键字段完整性
    key_fields_present = sum(1 for f in [product, producer, production_date] if f)
    key_fields_ok = key_fields_present >= 2

    # 时效性检查（与 SKILL.md 规则一致）
    expiry_status = "skip"  # skip / ok / expiring / expired
    if expired_time:
        try:
            days = (date.fromisoformat(str(expired_time)[:10]) - date.today()).days
            if days > 30:
                expiry_status = "ok"       # 正常
            elif days > 0:
                expiry_status = "expiring" # 临期（≤30天）
            else:
                expiry_status = "expired"  # 已过期
        except ValueError:
            expiry_status = "skip"  # 非标准格式跳过

    rules = [
        _rule("BATCH_REPORT_TEXT_PRESENT", "批次报告文本可审核", has_text, RiskLevel.MEDIUM, {"has_document_text": has_text}),
        _rule("BATCH_REPORT_TYPE_MATCH", "批次报告类型匹配", declared_type == "batch_report", RiskLevel.HIGH, {"expected": "batch_report", "actual": declared_type}),
        _rule("BATCH_REPORT_PRODUCT_NAME_MATCH", "商品名称匹配", product_match, RiskLevel.MEDIUM, {"field": "product_name", "expected": source_product, "actual": product, "match_reason": "字段值一致" if product_match else "字段值不一致", "confidence": "HIGH"}),
        _rule("BATCH_REPORT_PRODUCER_NAME_MATCH", "生产者名称匹配", producer_match, RiskLevel.MEDIUM, {"field": "producer_name", "expected": source_supplier, "actual": producer, "match_reason": "字段值一致" if producer_match else "字段值不一致", "confidence": "HIGH"}),
        _rule("BATCH_REPORT_PRODUCTION_DATE_MATCH", "生产日期/批号匹配", date_match, RiskLevel.MEDIUM, {"field": "production_date", "expected": source_production_date, "actual": production_date, "match_reason": "日期一致" if date_match else "日期不一致", "confidence": "HIGH"}),
        _rule("BATCH_REPORT_EXPIRY_CHECK", "生产日期时效性", expiry_status in ("ok", "skip"), RiskLevel.HIGH if expiry_status == "expired" else RiskLevel.MEDIUM, {"expired_time": expired_time, "today": today, "match_reason": "有效期内" if expiry_status == "ok" else "已过期" if expiry_status == "expired" else "临期（30天内）" if expiry_status == "expiring" else "跳过（无到期时间）"}),
        _rule("BATCH_REPORT_KEY_FIELD_INTEGRITY", "关键字段完整性", key_fields_ok, RiskLevel.MEDIUM, {"fields_present": key_fields_present, "fields_required": 2}),
    ]
    return _result(skill_name, rules, "商品批次报告规则校验通过", "商品批次报告存在需要人工复核的规则问题")


def _food_validity(valid_to, current_date):
    if not valid_to:
        return _rule("FOOD_LICENSE_VALIDITY_PERIOD", "有效期是否过期或三十天内临期", True, RiskLevel.HIGH, {"field": "valid_to", "actual": valid_to, "assumed_long_term": True})
    try:
        days = (date.fromisoformat(str(valid_to)) - date.fromisoformat(str(current_date))).days
    except ValueError:
        return _rule("FOOD_LICENSE_VALIDITY_PERIOD", "有效期是否过期或三十天内临期", False, RiskLevel.MEDIUM, {"field": "valid_to", "actual": valid_to})
    return _rule("FOOD_LICENSE_VALIDITY_PERIOD", "有效期是否过期或三十天内临期", days > 30, RiskLevel.HIGH if days < 0 else RiskLevel.MEDIUM, {"field": "valid_to", "actual": valid_to, "days_until_expiry": days})


def _product_report_validity(valid_to):
    if not valid_to:
        return _rule(
            "PRODUCT_REPORT_VALIDITY_PERIOD",
            "产品报告有效期是否过期或三十天内临期",
            False,
            RiskLevel.MEDIUM,
            {"field": "valid_to", "valid_to": valid_to},
        )
    try:
        days = (date.fromisoformat(str(valid_to)) - date(2026, 6, 29)).days
    except ValueError:
        return _rule(
            "PRODUCT_REPORT_VALIDITY_PERIOD",
            "产品报告有效期是否过期或三十天内临期",
            False,
            RiskLevel.MEDIUM,
            {"field": "valid_to", "valid_to": valid_to},
        )
    return _rule(
        "PRODUCT_REPORT_VALIDITY_PERIOD",
        "产品报告有效期是否过期或三十天内临期",
        days > 30,
        RiskLevel.HIGH if days < 0 else RiskLevel.MEDIUM,
        {"field": "valid_to", "valid_to": valid_to, "days_until_expiry": days},
    )


def _food_production_validity(valid_to, current_date):
    if not valid_to:
        return _rule("FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD", "有效期是否过期或三十天内临期", True, RiskLevel.HIGH, {"field": "valid_to", "actual": valid_to, "assumed_long_term": True})
    try:
        days = (date.fromisoformat(str(valid_to)) - date.fromisoformat(str(current_date))).days
    except ValueError:
        return _rule("FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD", "有效期是否过期或三十天内临期", False, RiskLevel.MEDIUM, {"field": "valid_to", "actual": valid_to})
    return _rule("FOOD_PRODUCTION_LICENSE_VALIDITY_PERIOD", "有效期是否过期或三十天内临期", days > 30, RiskLevel.HIGH if days <= 0 else RiskLevel.MEDIUM, {"field": "valid_to", "actual": valid_to, "days_until_expiry": days})


def _business_validity(valid_to):
    if not valid_to or valid_to == "长期":
        return _rule("BUSINESS_LICENSE_VALIDITY_PERIOD", "营业期限是否有效", True, RiskLevel.HIGH, {"field": "valid_to", "actual": valid_to, "assumed_long_term": not valid_to})
    try:
        days = (date.fromisoformat(str(valid_to)) - date.today()).days
    except ValueError:
        return _rule("BUSINESS_LICENSE_VALIDITY_PERIOD", "营业期限是否有效", False, RiskLevel.MEDIUM, {"field": "valid_to", "actual": valid_to})
    return _rule("BUSINESS_LICENSE_VALIDITY_PERIOD", "营业期限是否有效", days > 30, RiskLevel.HIGH if days < 0 else RiskLevel.MEDIUM, {"field": "valid_to", "actual": valid_to, "days_until_expiry": days})


def _business_key_field_evidence(fields):
    missing = []
    if fields.get("subject_name") and not _text(fields.get("subject_name_evidence")):
        missing.append("subject_name_evidence")
    if fields.get("credit_code") and not _text(fields.get("credit_code_evidence")):
        missing.append("credit_code_evidence")
    return _rule(
        "BUSINESS_LICENSE_KEY_FIELD_EVIDENCE_PRESENT",
        "关键字段识别依据完整性",
        not missing,
        RiskLevel.MEDIUM,
        {
            "required_evidence_fields": [
                "subject_name_evidence",
                "credit_code_evidence",
            ],
            "missing_evidence_fields": missing,
        },
    )


def _result(skill_name, rules, pass_summary, fail_summary):
    failed = [rule for rule in rules if not rule.passed]
    risk = RiskLevel.HIGH if any(rule.risk_level_on_failure == RiskLevel.HIGH for rule in failed) else RiskLevel.MEDIUM if any(rule.risk_level_on_failure == RiskLevel.MEDIUM for rule in failed) else RiskLevel.NONE
    status = "PENDING_MANUAL_REVIEW" if failed else "REVIEWED"
    return {
        "status": status,
        "status_label": "待人工复核" if failed else "已审核",
        "risk_level": risk,
        "risk_level_label": _risk_label(risk),
        "needs_manual_review": bool(failed),
        "summary": fail_summary if failed else pass_summary,
        "manual_review_reasons": [_reason(rule) for rule in failed],
        "rule_results": rules,
        "metadata": {"implementation_status": "fake", "skill_name": skill_name},
    }


def _rule(code, name, passed, risk, details):
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=passed,
        risk_level_on_failure=risk,
        message=name,
        details=details,
    )


def _reason(rule):
    actual = rule.details.get("actual")
    if rule.rule_code == "BATCH_REPORT_TEXT_PRESENT":
        return "批次报告附件未获取到可审核文本，需要人工复核。"
    if rule.rule_code == "BATCH_REPORT_TYPE_MATCH":
        return "批次报告类型不匹配。"
    if rule.rule_code == "BATCH_REPORT_PRODUCT_NAME_MATCH":
        return "商品名称缺失" if not actual else "商品名称与来源信息不一致"
    if rule.rule_code == "BATCH_REPORT_PRODUCER_NAME_MATCH":
        return "生产者名称缺失" if not actual else "生产者名称与来源信息不一致"
    if rule.rule_code == "BATCH_REPORT_PRODUCTION_DATE_MATCH":
        return "生产日期/批号缺失或与来源批次明细不一致"
    if rule.rule_code == "BATCH_REPORT_EXPIRY_CHECK":
        return "生产日期已过期或临期，需人工复核"
    if rule.rule_code == "BATCH_REPORT_KEY_FIELD_INTEGRITY":
        return "关键字段缺失严重，需人工复核"
    if rule.rule_code.endswith("SUBJECT_NAME_MATCH"):
        return "主体名称缺失" if not actual and rule.rule_code.startswith("BUSINESS") else "证照主体名称缺失，需要人工复核。" if not actual else "主体名称与来源信息不一致"
    if rule.rule_code == "FOOD_PRODUCTION_LICENSE_PRODUCER_NAME_MATCH":
        return "证照生产者名称缺失，需要人工复核。" if not actual else "生产者名称与来源信息不一致"
    if rule.rule_code.endswith("CREDIT_CODE_MATCH"):
        if not actual:
            return "统一社会信用代码缺失" if rule.rule_code.startswith("BUSINESS") else "证照统一社会信用代码缺失，需要人工复核。"
        return "统一社会信用代码格式异常" if rule.rule_code.startswith("BUSINESS") and len(_text(actual)) not in {15, 18} else "证照统一社会信用代码与供应商信用代码不一致。"
    if rule.rule_code == "BUSINESS_LICENSE_VALIDITY_PERIOD":
        return "有效期无法判断"
    if rule.rule_code == "PRODUCT_REPORT_VENDOR_NAME_MATCH":
        return "供应商名称缺失" if not actual else "供应商名称与来源信息不一致"
    if rule.rule_code == "PRODUCT_REPORT_PRODUCT_NAME_PRESENT":
        return "产品名缺失"
    if rule.rule_code == "PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT":
        return "批次号或生产日期缺失"
    if rule.rule_code == "PRODUCT_REPORT_CONCLUSION_PASS":
        return "检验结论明确为不合格" if "不" in _text(rule.details.get("conclusion")) else "检验结论不明确"
    return rule.message


def _same(left, right):
    return bool(left and right and _text(left) == _text(right))


def _same_code(left, right):
    return bool(left and right and _text(left).upper() == _text(right).upper())


def _text(value):
    return "" if value is None else "".join(str(value).split()).strip()


def _risk_label(risk):
    return {
        RiskLevel.NONE: "无风险",
        RiskLevel.LOW: "低风险",
        RiskLevel.MEDIUM: "中风险",
        RiskLevel.HIGH: "高风险",
    }[risk]
