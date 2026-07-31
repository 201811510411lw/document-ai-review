import zipfile

from fastapi.testclient import TestClient

from app.api.tobacco_license_sources import (
    get_tobacco_license_file_store,
    get_tobacco_license_starrocks_sql_client,
)
from app.main import app
from app.services.tobacco_license_files import TobaccoLicenseFileStore
from tests.business_license_helpers import business_license_auth_headers


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_fetch_tobacco_license_source_files_from_starrocks_extracts_file(tmp_path):
    nas_root = tmp_path / "data"
    source_zip = nas_root / "oaec" / "202607" / "J" / "file.zip"
    source_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("license.jpg", b"fake-license-image")

    class StubStarRocksClient:
        def fetch_all(self, sql):
            assert "B65230024" in sql
            return [
                {
                    "form_id": 3497,
                    "requestid": 2801287,
                    "store_name": "B65230024",
                    "store_code": "B65230024",
                    "tobacco_license_docids": "824576",
                    "valid_from": "2026-06-25",
                    "valid_to": "2029-06-01",
                    "workflow_id": 614,
                    "request_name": "香烟销售权限申请/香烟商品建档申请-徐飞-2026-07-09",
                    "created_date": "2026-07-09",
                    "created_time": "15:20:50",
                    "docid": 824576,
                    "doc_subject": "y",
                    "imagefile_id": 1409517,
                    "docimage_filename": "y.jpg",
                    "real_filename": "y.jpg",
                    "file_real_path": str(source_zip),
                    "is_zip": "1",
                    "is_encrypt": "0",
                    "is_aes_encrypt": 0,
                    "file_size": "253894",
                }
            ]

    app.dependency_overrides[get_tobacco_license_starrocks_sql_client] = (
        lambda: StubStarRocksClient()
    )
    app.dependency_overrides[get_tobacco_license_file_store] = lambda: TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=nas_root,
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/tobacco-license/source-files/from-starrocks",
        headers=business_license_auth_headers(client),
        json={"store_identifier": "B65230024"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["store_identifier"] == "B65230024"
    stored_file = payload["documents"][0]["files"][0]
    assert stored_file["file_name"] == "license.jpg"
    assert stored_file["relative_path"] == "B65230024/2801287_824576_1409517/license.jpg"
    assert stored_file["preview_url"].startswith(
        "/api/v1/tobacco-license/source-files/local/"
    )
    assert stored_file["download_url"].endswith("?download=1")

    preview_response = client.get(
        stored_file["preview_url"],
        headers=business_license_auth_headers(client),
    )
    assert preview_response.status_code == 200
    assert preview_response.content == b"fake-license-image"


def test_fetch_tobacco_license_source_files_from_starrocks_returns_not_found(tmp_path):
    class StubStarRocksClient:
        def fetch_all(self, sql):
            return []

    app.dependency_overrides[get_tobacco_license_starrocks_sql_client] = (
        lambda: StubStarRocksClient()
    )
    app.dependency_overrides[get_tobacco_license_file_store] = lambda: TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=tmp_path / "data",
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/tobacco-license/source-files/from-starrocks",
        headers=business_license_auth_headers(client),
        json={"store_identifier": "unknown"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TOBACCO_LICENSE_SOURCE_RECORD_NOT_FOUND"
