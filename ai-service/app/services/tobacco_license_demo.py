from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile


DEMO_STORE_IDENTIFIER = "DEMO-STORE-001"
DEMO_STORE_IDENTIFIERS = {
    "DEMO-STORE-001",
    "DEMO-STORE-002",
    "DEMO-STORE-003",
    "DEMO-STORE-004",
}


def is_demo_store(store_identifier: str) -> bool:
    return store_identifier.strip().upper() in DEMO_STORE_IDENTIFIERS


def demo_pending_stores() -> list[dict[str, object]]:
    return [
        {
            "store_code": DEMO_STORE_IDENTIFIER,
            "store_name": "演示店中店门店（通过）",
            "requestid": 10001,
            "submit_date": "2026-07-16",
            "request_name": "烟草商品建档申请 - 演示店中店门店",
            "summary_title": "店中店烟草销售申请",
            "content_summary": "持证主体与加盟方材料齐全，申请开通烟草商品销售。",
            "source": "demo",
        },
        {
            "store_code": "DEMO-STORE-002",
            "store_name": "演示标准门店（不通过）",
            "requestid": 10002,
            "submit_date": "2026-07-16",
            "request_name": "烟草商品建档申请 - 演示标准门店",
            "summary_title": "标准门店烟草销售申请",
            "content_summary": "提交营业执照和烟草专卖零售许可证，待系统核对。",
            "source": "demo",
        },
        {
            "store_code": "DEMO-STORE-003",
            "store_name": "演示店中店门店（待复核）",
            "requestid": 10003,
            "submit_date": "2026-07-15",
            "request_name": "烟草商品建档申请 - 待复核门店",
            "summary_title": "店中店补充材料申请",
            "content_summary": "存在店中店经营场景，待核对加盟关系及场地授权材料。",
            "source": "demo",
        },
        {
            "store_code": "DEMO-STORE-004",
            "store_name": "演示标准门店（通过）",
            "requestid": 10004,
            "submit_date": "2026-07-15",
            "request_name": "烟草商品建档申请 - 演示通过门店",
            "summary_title": "标准门店续期申请",
            "content_summary": "门店证照材料齐全，申请更新烟草商品销售资质。",
            "source": "demo",
        },
    ]


def demo_source_files(store_identifier: str = DEMO_STORE_IDENTIFIER) -> list[TobaccoLicenseSourceFile]:
    identifier = store_identifier.strip().upper()
    store = next(
        (item for item in demo_pending_stores() if item["store_code"] == identifier),
        demo_pending_stores()[0],
    )
    common = {
        "form_id": 0,
        "requestid": int(store["requestid"]),
        "store_name": str(store["store_name"]),
        "store_code": identifier,
        "request_name": "本地烟草证一致性演示",
        "summary_title": str(store["summary_title"]),
        "content_summary": str(store["content_summary"]),
        "workflow_id": 614,
        "created_date": str(store["submit_date"]),
        "created_time": "10:00:00",
        "request_status": "待处理",
        "file_real_path": "demo",
    }
    return [
        TobaccoLicenseSourceFile(
            **common,
            docid=1001,
            real_filename="持证主体营业执照.pdf",
            document_role="business_license",
        ),
        TobaccoLicenseSourceFile(
            **common,
            docid=1002,
            real_filename="烟草专卖零售许可证.pdf",
            document_role="tobacco_license",
        ),
        TobaccoLicenseSourceFile(
            **common,
            docid=1003,
            real_filename="加盟及场地授权协议.pdf",
            document_role="selected_attachment",
        ),
    ]


def demo_consistency_payload(store_identifier: str) -> dict[str, object]:
    """Return deterministic demo inputs so batch actions cover all outcomes."""
    identifier = store_identifier.strip().upper()
    business = {
        "document_type": "business_license",
        "subject_name": "乙便利店",
        "business_address": "成都市高新区天府大道 1 号",
        "legal_person": "张三",
    }
    tobacco = {
        "document_type": "tobacco_license",
        "subject_name": "乙便利店",
        "business_address": "成都市高新区天府大道 1 号",
        "legal_person": "张三",
        "valid_to": "2099-12-31",
    }
    if identifier == "DEMO-STORE-002":
        return {
            "review_mode": "standard",
            "business_license_fields": business,
            "tobacco_license_fields": {
                **tobacco,
                "subject_name": "其他烟草商行",
                "valid_to": "2000-01-01",
            },
        }
    if identifier == "DEMO-STORE-003":
        return {
            "review_mode": "store_in_store",
            "business_license_fields": business,
            "tobacco_license_fields": tobacco,
            "store_in_store": {},
        }
    if identifier == "DEMO-STORE-004":
        return {
            "review_mode": "standard",
            "business_license_fields": business,
            "tobacco_license_fields": tobacco,
        }
    return {
        "review_mode": "store_in_store",
        "business_license_fields": {
            **business,
            "business_address": "成都市锦江区总店",
        },
        "tobacco_license_fields": tobacco,
        "store_in_store": {
            "relationship_evidence": {
                "document_id": "demo-agreement.pdf",
                "franchisee_name": "甲加盟商",
                "holder_name": "乙便利店",
                "address": "成都市高新区天府大道 1 号",
            },
            "multi_address_evidence": {
                "holder_name": "乙便利店",
                "addresses": ["成都市高新区天府大道 1 号"],
            },
        },
    }
