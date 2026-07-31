from pathlib import Path

import yaml

from app.core.config import SECRET_ENV_KEYS


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_documentation_index_links_current_reference_guides():
    docs_index = (REPO_ROOT / "docs/README.md").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for target in [
        "CAPABILITIES.md",
        "SPEC.md",
        "API.md",
        "INTEGRATIONS.md",
        "OPERATIONS.md",
        "PRD.md",
        "api/openapi-operations.md",
    ]:
        assert f"]({target})" in docs_index

    assert "[docs/README.md](docs/README.md)" in readme


def test_integration_and_operations_guides_cover_runtime_boundaries():
    integrations = (REPO_ROOT / "docs/INTEGRATIONS.md").read_text(encoding="utf-8")
    operations = (REPO_ROOT / "docs/OPERATIONS.md").read_text(encoding="utf-8")

    for term in ["SRM", "StarRocks", "OA", "企业微信", "OCR", "LLM", "影刀 RPA"]:
        assert term in integrations

    for term in [
        "app-config/app.yaml.example",
        "STARROCKS_HOST",
        "TOBACCO_CONSISTENCY_OA_BUSINESS_LICENSE_FIELD",
        "BUSINESS_LICENSE_VISION_PROVIDER",
        "RPA_VERIFICATION_YINDAO_ROBOT_UUID",
        "declared_document_type",
    ]:
        assert term in integrations

    for term in [
        "DOCUMENT_AI_REVIEW_CONFIG_FILE",
        "REVIEW_RESULT_MYSQL",
        "daily-review-scheduler",
        "WECOM_WORKER_TOKEN",
        "OpenAPI",
        "故障排查",
    ]:
        assert term in operations


def test_secret_example_only_contains_dotenv_keys_that_the_loader_accepts():
    example_keys = {
        line.split("=", 1)[0]
        for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    }

    assert example_keys == SECRET_ENV_KEYS


def test_yaml_example_uses_empty_strings_for_unconfirmed_oa_fields():
    config = yaml.safe_load(
        (REPO_ROOT / "app-config/app.yaml.example").read_text(encoding="utf-8")
    )

    tobacco = config["tobacco_consistency"]
    assert tobacco["oa_relationship_evidence_field"] == ""
    assert tobacco["oa_multi_address_evidence_field"] == ""


def test_ai_service_readme_describes_the_current_service():
    service_readme = (REPO_ROOT / "ai-service/README.md").read_text(encoding="utf-8")

    assert "only" not in service_readme.split("## Scope", 1)[1].split("##", 1)[0]
    assert "../docs/README.md" in service_readme
