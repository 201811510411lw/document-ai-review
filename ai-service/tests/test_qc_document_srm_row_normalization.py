from app.integrations.srm.document_records import (
    UnsupportedSrmDocumentTypeError,
    map_srm_certification_row,
)


def test_srm_product_report_row_maps_to_document_record():
    row = {
        "tenant": "8560",
        "uuid": "cert-001",
        "refId": "cert-001",
        "category": "vendor",
        "typeCode": "PRODUCT_REPORT",
        "typeName": "产品报告",
        "number": "CERT-NO-001",
        "num": "BUS-NUM-001",
        "vendorId": "VENDOR-001",
        "vendorName": "成都示例食品有限公司",
        "expiredBegin": "2026-01-01",
        "expiredEnd": "2027-01-01",
        "attachmentName": "product-report.pdf",
        "storeId": "srm/cert/product-report.pdf",
        "url": "https://files.example.test/product-report.pdf",
        "deleted": False,
        "removed": False,
    }

    record = map_srm_certification_row(row)

    assert record.source_system == "srm"
    assert record.tenant == "8560"
    assert record.record_id == "cert-001"
    assert record.attachment_ref_id == "cert-001"
    assert record.document_category == "vendor"
    assert record.declared_document_type == "product_report"
    assert record.document_type_code == "PRODUCT_REPORT"
    assert record.business_number == "CERT-NO-001"
    assert record.business_num == "BUS-NUM-001"
    assert record.vendor_id == "VENDOR-001"
    assert record.vendor_name == "成都示例食品有限公司"
    assert record.source_expired_begin == "2026-01-01"
    assert record.source_expired_end == "2027-01-01"
    assert record.file_name == "product-report.pdf"
    assert record.file_store_key == "srm/cert/product-report.pdf"
    assert record.file_url == "https://files.example.test/product-report.pdf"
    assert record.business_deleted is False
    assert record.attachment_deleted is False
    assert record.is_deleted is False
    assert record.source_payload == row


def test_srm_business_license_row_maps_to_document_record():
    row = {
        "tenant": "8560",
        "uuid": "cert-business-001",
        "refId": "attach-business-001",
        "category": "vendor",
        "typeCode": "BUSINESS_LICENSE",
        "typeName": "营业执照",
        "number": "91510100MA0000000X",
        "num": "BL-NUM-001",
        "vendorId": "VENDOR-001",
        "vendorName": "成都示例商贸有限公司",
        "expiredBegin": "2020-01-01",
        "expiredEnd": "2030-01-01",
        "attachmentName": "business-license.pdf",
        "storeId": "srm/cert/business-license.pdf",
        "url": "https://files.example.test/business-license.pdf",
        "deleted": False,
        "removed": False,
    }

    record = map_srm_certification_row(row)

    assert record.declared_document_type == "business_license"
    assert record.record_id == "cert-business-001"
    assert record.attachment_ref_id == "attach-business-001"
    assert record.business_number == "91510100MA0000000X"
    assert record.vendor_name == "成都示例商贸有限公司"
    assert record.file_name == "business-license.pdf"
    assert record.file_url == "https://files.example.test/business-license.pdf"
    assert record.source_payload == row


def test_srm_product_report_row_allows_missing_optional_fields():
    record = map_srm_certification_row(
        {
            "tenant": "8560",
            "uuid": "cert-002",
            "category": "vendor",
            "typeName": "产品报告",
            "vendorName": "成都示例食品有限公司",
            "attachmentName": "product-report.png",
            "url": "https://files.example.test/product-report.png",
        }
    )

    assert record.declared_document_type == "product_report"
    assert record.record_id == "cert-002"
    assert record.attachment_ref_id is None
    assert record.document_type_code is None
    assert record.business_deleted is False
    assert record.attachment_deleted is False


def test_srm_row_normalizes_deleted_flags():
    record = map_srm_certification_row(
        {
            "uuid": "cert-deleted",
            "typeName": "产品报告",
            "deleted": "1",
            "removed": "true",
        }
    )

    assert record.business_deleted is True
    assert record.attachment_deleted is True
    assert record.is_deleted is True


def test_unknown_srm_type_name_is_rejected_explicitly():
    row = {"uuid": "cert-unknown", "typeName": "烟草证"}

    try:
        map_srm_certification_row(row)
    except UnsupportedSrmDocumentTypeError as error:
        assert error.type_name == "烟草证"
    else:
        raise AssertionError("unknown SRM typeName should not map silently")
