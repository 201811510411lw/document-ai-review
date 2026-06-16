from app.workflows.qc_document.product_report_extraction import (
    extract_product_report_fields,
)


def test_extract_product_report_required_fields_from_complete_text():
    document_text = """
    产品检验报告
    报告编号：BG-20260610-001
    样品名称：麻辣牛肉
    受检单位：成都示例食品有限公司
    生产单位：成都示例食品厂
    批号：20260601-A
    生产日期：2026年06月01日
    签发日期：2026年06月10日
    检验结论：经检验，所检项目符合要求。
    检验项目：
    1. 菌落总数 120 CFU/g
    2. 大肠菌群 未检出
    """

    extracted, metadata = extract_product_report_fields(document_text)

    assert extracted.document_type == "product_report"
    assert extracted.product_name == "麻辣牛肉"
    assert extracted.sample_name == "麻辣牛肉"
    assert extracted.vendor_name_extracted == "成都示例食品有限公司"
    assert extracted.entrusting_party == "成都示例食品有限公司"
    assert extracted.manufacturer_name == "成都示例食品厂"
    assert extracted.batch_no == "20260601-A"
    assert extracted.production_date == "2026-06-01"
    assert extracted.issue_date == "2026-06-10"
    assert extracted.sign_date == "2026-06-10"
    assert extracted.inspection_conclusion == "经检验，所检项目符合要求。"
    assert extracted.inspection_result == "经检验，所检项目符合要求。"
    assert extracted.inspection_items == [
        {"name": "菌落总数", "result": "120 CFU/g"},
        {"name": "大肠菌群", "result": "未检出"},
    ]
    assert metadata["missing_required_fields"] == []
    assert metadata["inspection_items_count"] == 2


def test_product_report_does_not_require_report_number():
    document_text = """
    产品检验报告
    样品名称：麻辣牛肉
    委托单位：成都示例食品有限公司
    批次号：BATCH-001
    签发日期：2026-06-10
    检验结论：合格
    """

    extracted, metadata = extract_product_report_fields(document_text)

    assert extracted.document_type == "product_report"
    assert extracted.product_name == "麻辣牛肉"
    assert extracted.vendor_name_extracted == "成都示例食品有限公司"
    assert extracted.batch_no == "BATCH-001"
    assert extracted.issue_date == "2026-06-10"
    assert extracted.inspection_conclusion == "合格"
    assert metadata["missing_required_fields"] == []


def test_product_report_extracts_simple_inspection_items():
    document_text = """
    产品检验报告
    样品名称：麻辣牛肉
    受检单位：成都示例食品有限公司
    批号：20260601-A
    检验项目：
    1. 菌落总数 120 CFU/g
    2. 大肠菌群 未检出
    """

    extracted, metadata = extract_product_report_fields(document_text)

    assert extracted.inspection_items == [
        {"name": "菌落总数", "result": "120 CFU/g"},
        {"name": "大肠菌群", "result": "未检出"},
    ]
    assert metadata["inspection_items_count"] == 2
