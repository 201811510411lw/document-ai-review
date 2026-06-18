from datetime import datetime

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
        "expiredBegin": datetime(2020, 1, 1, 0, 0, 0),
        "expiredEnd": datetime(2030, 1, 1, 23, 59, 59),
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
    assert record.source_expired_begin == "2020-01-01T00:00:00"
    assert record.source_expired_end == "2030-01-01T23:59:59"
    assert record.file_name == "business-license.pdf"
    assert record.file_url == "https://files.example.test/business-license.pdf"
    assert record.source_payload == row


def test_srm_food_license_row_maps_to_document_record():
    row = {
        "tenant": "8560",
        "uuid": "cert-food-001",
        "refId": "attach-food-001",
        "category": "vendor",
        "typeCode": "FOOD_LICENSE",
        "typeName": "食品经营许可证",
        "number": "JY15101000000000",
        "num": "91510100MA00000000",
        "vendorId": "VENDOR-001",
        "vendorName": "成都示例食品有限公司",
        "attachmentName": "food-license.pdf",
        "storeId": "srm/cert/food-license.pdf",
        "url": "https://files.example.test/food-license.pdf",
    }

    record = map_srm_certification_row(row)

    assert record.declared_document_type == "food_license"
    assert record.record_id == "cert-food-001"
    assert record.attachment_ref_id == "attach-food-001"
    assert record.business_number == "JY15101000000000"
    assert record.business_num == "91510100MA00000000"
    assert record.vendor_name == "成都示例食品有限公司"
    assert record.file_name == "food-license.pdf"
    assert record.file_url == "https://files.example.test/food-license.pdf"


def test_srm_food_production_license_row_maps_to_document_record():
    row = {
        "tenant": "8560",
        "uuid": "cert-food-production-001",
        "refId": "attach-food-production-001",
        "category": "vendor",
        "typeCode": "FOOD_PRODUCTION_LICENSE",
        "typeName": "食品生产许可证",
        "number": "SC10151010000000",
        "num": "91510100MA00000000",
        "vendorId": "VENDOR-001",
        "vendorName": "成都示例食品生产有限公司",
        "attachmentName": "food-production-license.pdf",
        "storeId": "srm/cert/food-production-license.pdf",
        "url": "https://files.example.test/food-production-license.pdf",
    }

    record = map_srm_certification_row(row)

    assert record.declared_document_type == "food_production_license"
    assert record.record_id == "cert-food-production-001"
    assert record.attachment_ref_id == "attach-food-production-001"
    assert record.business_number == "SC10151010000000"
    assert record.business_num == "91510100MA00000000"
    assert record.vendor_name == "成都示例食品生产有限公司"
    assert record.file_name == "food-production-license.pdf"
    assert record.file_url == "https://files.example.test/food-production-license.pdf"


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


def test_srm_attachment_row_maps_lowercase_join_columns():
    row = {
        "tenant": "8560",
        "uuid": "cert-business-001",
        "refid": "attach-business-001",
        "category": "vendor",
        "typeCode": "BUSINESS_LICENSE",
        "typeName": "营业执照",
        "num": "91510100MA0000000X",
        "vendorName": "成都示例商贸有限公司",
        "attachmentname": "business-license.pdf",
        "storeid": "srm/cert/business-license.pdf",
        "url": "https://files.example.test/business-license.pdf",
        "deleted": "0",
        "removed": "0",
    }

    record = map_srm_certification_row(row)

    assert record.attachment_ref_id == "attach-business-001"
    assert record.file_name == "business-license.pdf"
    assert record.file_store_key == "srm/cert/business-license.pdf"


def test_unknown_srm_type_name_is_rejected_explicitly():
    row = {"uuid": "cert-unknown", "typeName": "烟草证"}

    try:
        map_srm_certification_row(row)
    except UnsupportedSrmDocumentTypeError as error:
        assert error.type_name == "烟草证"
    else:
        raise AssertionError("unknown SRM typeName should not map silently")
