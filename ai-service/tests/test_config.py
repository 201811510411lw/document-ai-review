import os
from pathlib import Path

from dotenv import dotenv_values
from app.core.config import load_local_env


def test_load_local_env_keeps_explicit_shell_env(monkeypatch):
    project_root = Path(__file__).resolve().parents[2]
    project_env = dotenv_values(project_root / ".env")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.example/v1")
    monkeypatch.delenv("BUSINESS_LICENSE_VISION_MODEL", raising=False)

    load_local_env()

    assert os.environ["OPENAI_BASE_URL"] == "https://stale.example/v1"
    assert (
        os.environ["BUSINESS_LICENSE_VISION_MODEL"]
        == project_env["BUSINESS_LICENSE_VISION_MODEL"]
    )
