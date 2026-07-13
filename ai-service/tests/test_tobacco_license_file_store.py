import zipfile

from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile
from app.services.tobacco_license_files import (
    TobaccoLicenseFileStore,
    TobaccoLicenseFileStoreError,
)


def test_tobacco_license_file_store_extracts_zip_under_data_dir(tmp_path):
    nas_root = tmp_path / "data"
    source_zip = nas_root / "oaec" / "202607" / "J" / "file.zip"
    source_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("nested/license.jpg", b"fake-license-image")

    store = TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=nas_root,
    )

    document = store.store_source_file(
        TobaccoLicenseSourceFile(
            form_id=3497,
            requestid=2801287,
            store_name="B65230024",
            store_code="B65230024",
            docid=824576,
            imagefile_id=1409517,
            real_filename="license.jpg",
            file_real_path=str(source_zip),
            is_zip="1",
            is_encrypt="0",
            is_aes_encrypt=0,
        )
    )

    assert len(document.files) == 1
    stored_file = document.files[0]
    assert stored_file.file_name == "license.jpg"
    assert stored_file.relative_path == "B65230024/2801287_824576_1409517/license.jpg"
    assert stored_file.file_size == len(b"fake-license-image")
    assert stored_file.content_type == "image/jpeg"
    assert (tmp_path / "app-data" / "tobacco_license" / stored_file.relative_path).read_bytes() == b"fake-license-image"


def test_tobacco_license_file_store_uses_oa_filename_when_zip_member_has_no_suffix(
    tmp_path,
):
    nas_root = tmp_path / "data"
    source_zip = nas_root / "oaec" / "202607" / "J" / "file.zip"
    source_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("38982780-2512-4dd7-8e4d-feb27f5d44bf", b"fake-license-image")

    store = TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=nas_root,
    )

    document = store.store_source_file(
        TobaccoLicenseSourceFile(
            requestid=2801287,
            store_code="B65230024",
            docid=824576,
            imagefile_id=1409517,
            real_filename="y.jpg",
            file_real_path=str(source_zip),
            is_zip="1",
            is_encrypt="0",
            is_aes_encrypt=0,
        )
    )

    stored_file = document.files[0]
    assert stored_file.file_name == "y.jpg"
    assert stored_file.content_type == "image/jpeg"


def test_tobacco_license_file_store_rebuilds_same_output_dir_without_duplicates(
    tmp_path,
):
    nas_root = tmp_path / "data"
    source_zip = nas_root / "oaec" / "202607" / "J" / "file.zip"
    source_zip.parent.mkdir(parents=True)
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("raw-file", b"first")

    store = TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=nas_root,
    )
    source_file = TobaccoLicenseSourceFile(
        requestid=2801287,
        store_code="B65230024",
        docid=824576,
        imagefile_id=1409517,
        real_filename="y.jpg",
        file_real_path=str(source_zip),
        is_zip="1",
        is_encrypt="0",
        is_aes_encrypt=0,
    )

    first = store.store_source_file(source_file)
    second = store.store_source_file(source_file)

    assert first.files[0].relative_path == second.files[0].relative_path
    output_dir = tmp_path / "app-data" / "tobacco_license" / "B65230024" / "2801287_824576_1409517"
    assert [path.name for path in output_dir.iterdir()] == ["y.jpg"]


def test_tobacco_license_file_store_rejects_path_outside_nas_root(tmp_path):
    store = TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=tmp_path / "data",
    )

    try:
        store.resolve_nas_path(str(tmp_path / "other" / "file.zip"))
    except TobaccoLicenseFileStoreError as error:
        assert error.code == "TOBACCO_LICENSE_FILE_PATH_OUTSIDE_NAS"
    else:
        raise AssertionError("path outside NAS root should be rejected")


def test_tobacco_license_file_store_rejects_encrypted_attachment(tmp_path):
    nas_root = tmp_path / "data"
    source_zip = nas_root / "oaec" / "file.zip"
    source_zip.parent.mkdir(parents=True)
    source_zip.write_bytes(b"not-used")

    store = TobaccoLicenseFileStore(
        base_data_dir=tmp_path / "app-data" / "tobacco_license",
        nas_root=nas_root,
    )

    try:
        store.store_source_file(
            TobaccoLicenseSourceFile(
                file_real_path=str(source_zip),
                is_zip="1",
                is_encrypt="1",
                is_aes_encrypt=0,
            )
        )
    except TobaccoLicenseFileStoreError as error:
        assert error.code == "TOBACCO_LICENSE_FILE_ENCRYPTED"
    else:
        raise AssertionError("encrypted attachment should be rejected")
