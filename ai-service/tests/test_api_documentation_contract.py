from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_checked_in_api_operation_inventory_matches_openapi():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "ai-service/scripts/generate_api_operation_inventory.py"),
            "--check",
        ],
        cwd=REPO_ROOT / "ai-service",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_api_guides_only_advertise_current_review_routes():
    api_contract = (REPO_ROOT / "docs/API.md").read_text(encoding="utf-8")
    oa_guide = (
        REPO_ROOT / "docs/api/oa-tobacco-consistency-auto-review.md"
    ).read_text(encoding="utf-8")

    stale_contracts = [
        "GET /api/v1/food-license/reviews/{task_id}",
        "POST /api/v1/food-license/reviews/{task_id}/manual-review",
        "POST /api/v1/food-license/reviews:upload",
        "GET /api/v1/tobacco-license-consistency/reviews/{task_id}/details",
    ]
    combined_guides = api_contract + oa_guide
    for contract in stale_contracts:
        assert contract not in combined_guides

    current_rpa_contracts = [
        "GET /api/v1/tobacco-license/rpa-verify-capability",
        "POST /api/v1/tobacco-license/rpa-verify",
        "POST /api/v1/tobacco-license/rpa-verify-callback",
        "GET /api/v1/tobacco-license/rpa-verify/{task_id}",
    ]
    for contract in current_rpa_contracts:
        assert contract in api_contract
