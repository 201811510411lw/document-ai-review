from app.capabilities.business_license.extractor import extract_business_license_fields


def test_extract_business_license_required_fields_from_complete_text():
    document_text = """
    营业执照
    统一社会信用代码：91510100MA0000000X
    名称：成都示例商贸有限公司
    类型：有限责任公司
    住所：成都市高新区天府大道 1 号
    法定代表人：张三
    成立日期：2020年01月02日
    营业期限：2020年01月02日至2030年01月01日
    登记机关：成都市市场监督管理局
    发证日期：2020年01月02日
    """

    extracted, metadata = extract_business_license_fields(document_text)

    assert extracted.document_type == "business_license"
    assert extracted.subject_name == "成都示例商贸有限公司"
    assert extracted.credit_code == "91510100MA0000000X"
    assert extracted.business_address == "成都市高新区天府大道 1 号"
    assert extracted.legal_person == "张三"
    assert extracted.established_date == "2020-01-02"
    assert extracted.valid_from == "2020-01-02"
    assert extracted.valid_to == "2030-01-01"
    assert extracted.issue_authority == "成都市市场监督管理局"
    assert extracted.issue_date == "2020-01-02"
    assert metadata["missing_required_fields"] == []
    assert metadata["date_parse_errors"] == []


def test_extract_business_license_reports_missing_required_fields():
    extracted, metadata = extract_business_license_fields("营业执照\n名称：成都示例商贸有限公司")

    assert extracted.document_type == "business_license"
    assert metadata["missing_required_fields"] == ["credit_code", "valid_to"]


def test_extract_business_license_marks_non_business_license_text_unknown():
    extracted, metadata = extract_business_license_fields("产品检验报告\n检验结论：合格")

    assert extracted.document_type == "unknown"
    assert metadata["missing_required_fields"] == [
        "subject_name",
        "credit_code",
        "valid_to",
    ]


def test_extract_business_license_reports_unparseable_dates():
    extracted, metadata = extract_business_license_fields(
        """
        营业执照
        统一社会信用代码：91510100MA0000000X
        名称：成都示例商贸有限公司
        营业期限：二零二零年一月二日至二零三零年一月一日
        """
    )

    assert extracted.valid_to is None
    assert metadata["date_parse_errors"] == ["validity_period"]
