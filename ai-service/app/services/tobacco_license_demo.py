from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile


DEMO_STORE_IDENTIFIER = "DEMO-STORE-001"


def is_demo_store(store_identifier: str) -> bool:
    return store_identifier.strip().upper() == DEMO_STORE_IDENTIFIER


def demo_pending_stores() -> list[dict[str, object]]:
    return [
        {
            "store_code": DEMO_STORE_IDENTIFIER,
            "store_name": "演示店中店门店",
            "requestid": 0,
            "submit_date": "2026-07-16",
            "source": "demo",
        }
    ]


def demo_source_files() -> list[TobaccoLicenseSourceFile]:
    return [
        TobaccoLicenseSourceFile(
            form_id=0,
            requestid=0,
            store_name="演示店中店门店",
            store_code=DEMO_STORE_IDENTIFIER,
            request_name="本地店中店比对演示",
            file_real_path="demo",
        )
    ]
