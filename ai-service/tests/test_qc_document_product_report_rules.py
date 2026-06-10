from app.workflows.qc_document.product_report_rules import (
    evaluate_product_report_rules,
)


def test_product_report_rules_return_stable_payload_when_all_checks_pass():
    result = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：合格",
        },
    )

    assert result["status"] == "REVIEWED"
    assert result["risk_level"] == "NONE"
    assert result["needs_manual_review"] is False
    assert result["summary"] == "产品检验报告规则校验通过"
    assert result["manual_review_reasons"] == []
    assert [item["rule_code"] for item in result["rule_results"]] == [
        "PRODUCT_REPORT_TYPE_MATCH",
        "PRODUCT_REPORT_VENDOR_NAME_MATCH",
        "PRODUCT_REPORT_PRODUCT_NAME_PRESENT",
        "PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT",
        "PRODUCT_REPORT_CONCLUSION_PASS",
    ]
    assert all(item["passed"] is True for item in result["rule_results"])


def test_product_report_rules_flag_type_mismatch():
    result = evaluate_product_report_rules(
        declared_document_type="food_license",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：合格",
        },
    )

    assert result["risk_level"] == "HIGH"
    assert result["needs_manual_review"] is True
    assert "文档类型不匹配" in result["manual_review_reasons"]
    assert _rule(result, "PRODUCT_REPORT_TYPE_MATCH")["passed"] is False


def test_product_report_rules_flag_vendor_name_mismatch():
    result = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都另一家食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：合格",
        },
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["needs_manual_review"] is True
    assert "供应商名称与来源信息不一致" in result["manual_review_reasons"]
    assert _rule(result, "PRODUCT_REPORT_VENDOR_NAME_MATCH")["passed"] is False


def test_product_report_rules_require_product_name():
    result = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：合格",
        },
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["needs_manual_review"] is True
    assert "产品名缺失" in result["manual_review_reasons"]
    assert _rule(result, "PRODUCT_REPORT_PRODUCT_NAME_PRESENT")["passed"] is False


def test_product_report_rules_require_batch_or_production_date():
    result = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "",
            "production_date": None,
            "conclusion": "检验结论：合格",
        },
    )

    assert result["risk_level"] == "MEDIUM"
    assert result["needs_manual_review"] is True
    assert "批次号或生产日期缺失" in result["manual_review_reasons"]
    assert (
        _rule(result, "PRODUCT_REPORT_BATCH_OR_PRODUCTION_DATE_PRESENT")["passed"]
        is False
    )


def test_product_report_rules_classify_conclusion_states():
    positive = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：合格",
        },
    )
    negative = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：不合格",
        },
    )
    unclear = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name="成都示例食品有限公司",
        extracted_fields={
            "vendor_name": "成都示例食品有限公司",
            "product_name": "香辣牛肉味豆干",
            "batch_number": "LOT-20260601",
            "production_date": "2026-06-01",
            "conclusion": "检验结论：见备注",
        },
    )

    assert positive["risk_level"] == "NONE"
    assert _rule(positive, "PRODUCT_REPORT_CONCLUSION_PASS")["passed"] is True

    assert negative["risk_level"] == "HIGH"
    assert "检验结论明确为不合格" in negative["manual_review_reasons"]
    assert _rule(negative, "PRODUCT_REPORT_CONCLUSION_PASS")["passed"] is False

    assert unclear["risk_level"] == "MEDIUM"
    assert "检验结论不明确" in unclear["manual_review_reasons"]
    assert _rule(unclear, "PRODUCT_REPORT_CONCLUSION_PASS")["passed"] is False


def _rule(result: dict, rule_code: str) -> dict:
    return next(
        item for item in result["rule_results"] if item["rule_code"] == rule_code
    )
