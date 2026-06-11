import os
from pathlib import Path

from dotenv import dotenv_values
from app.core.config import load_local_env


def test_load_local_env_uses_project_env_instead_of_shell_env(monkeypatch):
    project_root = Path(__file__).resolve().parents[2]
    project_env = dotenv_values(project_root / ".env")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.example/v1")
    monkeypatch.setenv("BUSINESS_LICENSE_VISION_MODEL", "stale-model")

    load_local_env()

    assert os.environ["OPENAI_BASE_URL"] == project_env["OPENAI_BASE_URL"]
    assert (
        os.environ["BUSINESS_LICENSE_VISION_MODEL"]
        == project_env["BUSINESS_LICENSE_VISION_MODEL"]
    )
