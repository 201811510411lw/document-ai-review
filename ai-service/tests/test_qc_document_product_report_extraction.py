import re

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
    assert extracted.report_no == "BG-20260610-001"
    assert extracted.product_name == "麻辣牛肉"
    assert extracted.sample_name == "麻辣牛肉"
    assert extracted.vendor_name_extracted == "成都示例食品有限公司"
    assert extracted.entrusting_party == "成都示例食品有限公司"
    assert extracted.manufacturer_name == "成都示例食品厂"
    assert extracted.batch_no == "20260601-A"
    assert extracted.production_date == "2026-06-01"
    assert extracted.issue_date == "2026-06-10"
    assert extracted.sign_date == "2026-06-10"
    assert extracted.approval_date is None
    assert extracted.valid_to == "2026-12-07"
    assert extracted.inspection_conclusion == "经检验，所检项目符合要求。"
    assert extracted.inspection_result == "经检验，所检项目符合要求。"
    assert extracted.inspection_items == [
        {"name": "菌落总数", "result": "120 CFU/g"},
        {"name": "大肠菌群", "result": "未检出"},
    ]
    assert metadata["missing_required_fields"] == []
    assert metadata["inspection_items_count"] == 2


def test_product_report_requires_report_number():
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
    assert metadata["missing_required_fields"] == ["report_no"]


def test_product_report_uses_approval_date_for_valid_to_when_issue_date_missing():
    document_text = """
    第三方检验报告
    报告编号：A2260511467101001C
    样品名称：鲜切蛋糕(蓝莓风味)
    委托单位：广东乃一口食品有限公司
    批号：TS10970001
    批准日期：2026年06月29日
    检验结论：所检项目符合相关食品安全标准要求
    """

    extracted, metadata = extract_product_report_fields(document_text)

    assert extracted.report_no == "A2260511467101001C"
    assert extracted.issue_date is None
    assert extracted.sign_date is None
    assert extracted.approval_date == "2026-06-29"
    assert extracted.valid_to == "2026-12-26"
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


def test_product_report_extracts_cti_table_style_report_text():
    document_text = """
    检 测 报 告
    样品名称：  鲜切蛋糕(蓝莓风味)
    委托单位：  广东乃一口食品有限公司
    报告编号：A2260511467101001C

    样
    品
    信
    息
    样品名称 鲜切蛋糕(蓝莓风味) CTI 样品编号 TS10970001
    样品批号 / 样品规格 /
    生产日期 2026/6/20 样品状态 完好
    生产商 广东乃一口食品有限公司
    委托单位 广东乃一口食品有限公司

    检
    测
    结
    论
    经检测，所检项目符合 GB 29921-2021《食品安全国家标准 预包装食品中致病菌限量》 ，
    GB/T 20977-2024《糕点质量通则》要求。
    批准日期：2026 年 06 月 29 日

    检测结果：
    序号 检测项目 单位 检测结果 检出限 标准要求 结论 检测方法
    1 色泽 / 具有该品种应有的色泽 / 具有该品种应有的色泽 符合 GB/T 20977-2024
    18 菌落总数 CFU/g 1#：<10 / n=5,c=2,m=10⁴ CFU/g,M=10⁵ CFU/g 符合 GB 4789.2-2022

    声明：
    1.报告无批准人签字、检验检测专用章及报告骑缝章均视作无效。
    6.扫描报告首页二维码，即可查询报告真伪。
    """

    extracted, metadata = extract_product_report_fields(document_text)

    assert extracted.report_no == "A2260511467101001C"
    assert extracted.product_name == "鲜切蛋糕(蓝莓风味)"
    assert extracted.vendor_name_extracted == "广东乃一口食品有限公司"
    assert extracted.manufacturer_name == "广东乃一口食品有限公司"
    assert extracted.batch_no is None
    assert extracted.production_date == "2026-06-20"
    assert extracted.approval_date == "2026-06-29"
    assert extracted.valid_to == "2026-12-26"
    assert extracted.inspection_conclusion.startswith("经检测，所检项目符合")
    assert metadata["missing_required_fields"] == []
    assert {"name": "色泽", "result": "具有该品种应有的色泽"} in extracted.inspection_items
    assert {"name": "菌落总数", "result": "1#：<10"} in extracted.inspection_items
    assert all("报告无批准人签字" not in item["name"] for item in extracted.inspection_items)


def test_product_report_extracts_cti_standard_index_conclusion():
    document_text = """
    报告编号：A2250602969109001C
    样品名称：猴头菇山药吐司面包
    委托单位：多麦（福建）食品有限公司
    生产日期 2025.8.28 批号 /
    生产商 卡洛斯（福建）食品有限公司
    检
    测
    结
    论
    经检测，有标准指标的项目符合 GB 29921-2021《食品安全国家标准 预包装食品
    中致病菌限量》，GB/T 20981-2021《面包质量通则》要求。无标准指标的项
    目仅提供检测数据。
    批准日期：2025 年 09 月 11 日

    检测结果：
    序号 检测项目 单位 检测结果 检出限 标准要求 结论 检测方法
    29 霉菌 CFU/g <10 / ≤150 符合 GB 4789.15-2016

    备注：
    1. *1 表示该项目/方法不在 CNAS 认可范围内。
    2. 采样方案系数：
    声明：
    1. 报告无批准人签字、检验检测专用章及报告骑缝章均视作无效。
    """

    extracted, metadata = extract_product_report_fields(document_text)

    assert extracted.report_no == "A2250602969109001C"
    assert extracted.production_date == "2025-08-28"
    assert extracted.approval_date == "2025-09-11"
    assert extracted.valid_to == "2026-03-10"
    assert extracted.inspection_conclusion.startswith("经检测，有标准指标的项目符合")
    compact_conclusion = re.sub(r"\s+", "", extracted.inspection_conclusion)
    assert "无标准指标的项目仅提供检测数据" in compact_conclusion
    assert metadata["missing_required_fields"] == []
    assert {"name": "霉菌", "result": "<10"} in extracted.inspection_items
    assert all("报告无批准人签字" not in item["result"] for item in extracted.inspection_items)
