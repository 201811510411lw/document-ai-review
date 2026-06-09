from app.skills.food_license.extractor import extract_food_license_fields


def test_regex_extractor_handles_food_license_sample_with_chinese_date():
    fields, metadata = extract_food_license_fields(
        "食品经营许可证\n"
        "经营者名称：成都示例食品有限公司\n"
        "统一社会信用代码：91510100MA00000000\n"
        "许可证编号：JY15101000000000\n"
        "经营场所：四川省成都市锦江区示例路1号\n"
        "经营项目：预包装食品销售、散装食品销售\n"
        "有效期至：2028年06月05日",
        llm_adapter=None,
    )

    assert fields.subject_name == "成都示例食品有限公司"
    assert fields.credit_code == "91510100MA00000000"
    assert fields.license_no == "JY15101000000000"
    assert fields.business_address == "四川省成都市锦江区示例路1号"
    assert fields.business_items == ["预包装食品销售", "散装食品销售"]
    assert fields.valid_from is None
    assert fields.valid_to == "2028-06-05"
    assert metadata["llm_used"] is False


def test_regex_extractor_handles_dash_date_range_and_business_item_separators():
    fields, metadata = extract_food_license_fields(
        "食品经营许可证\n"
        "名称 成都测试商贸有限公司\n"
        "社会信用代码 91510100MA11111111\n"
        "编号 JY15101001111111\n"
        "经营项目 预包装食品销售；保健食品销售\n"
        "有效期限：2023-06-01 至 2028-05-31",
        llm_adapter=None,
    )

    assert fields.subject_name == "成都测试商贸有限公司"
    assert fields.credit_code == "91510100MA11111111"
    assert fields.license_no == "JY15101001111111"
    assert fields.business_items == ["预包装食品销售", "保健食品销售"]
    assert fields.valid_from == "2023-06-01"
    assert fields.valid_to == "2028-05-31"
    assert metadata["llm_used"] is False


def test_regex_extractor_returns_stable_empty_fields_for_unknown_text():
    fields, metadata = extract_food_license_fields(
        "这是一段无法识别为食品经营许可证的文本",
        llm_adapter=None,
    )

    assert fields.subject_name is None
    assert fields.credit_code is None
    assert fields.license_no is None
    assert fields.business_items == []
    assert fields.valid_from is None
    assert fields.valid_to is None
    assert metadata["llm_used"] is False
