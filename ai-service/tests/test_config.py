import os
from pathlib import Path

import pytest

from app.core.config import (
    CONFIG_FILE_ENV_KEY,
    PROJECT_ENV_KEYS,
    load_local_env,
    load_yaml_config_values,
)


def test_load_local_env_reads_yaml_config_and_dotenv_secrets(tmp_path, monkeypatch):
    project_root = tmp_path
    config_dir = project_root / "app-config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        """
runtime:
  debug: true
openai:
  base_url: https://config.example/v1
  max_attempts: 2
business_license:
  qwen_ocr:
    model: qwen-config
    max_pages: 7
    stop_after_first_license: true
aliyun_ocr:
  body_options:
    prob: true
    table: false
  rotation_order:
    - 270
    - 0
srm_mysql:
  host: 127.0.0.1
  port: 3306
  database: srm
starrocks:
  host: starrocks.example.test
  port: 9030
  database: work_temp
wecom:
  reviewer_user_ids:
    - zhangsan
    - lisi
""",
        encoding="utf-8",
    )
    (project_root / ".env").write_text(
        "OPENAI_API_KEY=secret-key\n"
        "SRM_MYSQL_PASSWORD=secret-password\n"
        "STARROCKS_USER=starrocks-user\n"
        "STARROCKS_PASSWORD=starrocks-password\n",
        encoding="utf-8",
    )
    _clear_project_env(monkeypatch)

    load_local_env(project_root)

    assert os.environ["OPENAI_BASE_URL"] == "https://config.example/v1"
    assert os.environ["BUSINESS_LICENSE_QWEN_OCR_MODEL"] == "qwen-config"
    assert os.environ["BUSINESS_LICENSE_QWEN_OCR_MAX_PAGES"] == "7"
    assert os.environ["BUSINESS_LICENSE_QWEN_OCR_STOP_AFTER_FIRST_LICENSE"] == "true"
    assert os.environ["ALIYUN_OCR_BODY_JSON"] == '{"prob":true,"table":false}'
    assert os.environ["ALIYUN_OCR_ROTATION_ORDER"] == "270,0"
    assert os.environ["WECOM_REVIEWER_USER_IDS"] == "zhangsan,lisi"
    assert os.environ["STARROCKS_HOST"] == "starrocks.example.test"
    assert os.environ["STARROCKS_PORT"] == "9030"
    assert os.environ["STARROCKS_DATABASE"] == "work_temp"
    assert os.environ["STARROCKS_USER"] == "starrocks-user"
    assert os.environ["STARROCKS_PASSWORD"] == "starrocks-password"
    assert os.environ["OPENAI_API_KEY"] == "secret-key"
    assert os.environ["SRM_MYSQL_PASSWORD"] == "secret-password"


def test_load_local_env_keeps_explicit_shell_env(tmp_path, monkeypatch):
    project_root = tmp_path
    config_dir = project_root / "app-config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        """
openai:
  base_url: https://config.example/v1
business_license:
  qwen_ocr:
    model: qwen-config
""",
        encoding="utf-8",
    )
    _clear_project_env(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.example/v1")

    load_local_env(project_root)

    assert os.environ["OPENAI_BASE_URL"] == "https://stale.example/v1"
    assert os.environ["BUSINESS_LICENSE_QWEN_OCR_MODEL"] == "qwen-config"


def test_load_local_env_ignores_non_secret_values_in_dotenv(tmp_path, monkeypatch):
    project_root = tmp_path
    config_dir = project_root / "app-config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        """
openai:
  base_url: https://config.example/v1
""",
        encoding="utf-8",
    )
    (project_root / ".env").write_text(
        "OPENAI_BASE_URL=https://dotenv.example/v1\nOPENAI_API_KEY=secret-key\n",
        encoding="utf-8",
    )
    _clear_project_env(monkeypatch)

    load_local_env(project_root)

    assert os.environ["OPENAI_BASE_URL"] == "https://config.example/v1"
    assert os.environ["OPENAI_API_KEY"] == "secret-key"


def test_load_local_env_supports_config_file_env(tmp_path, monkeypatch):
    project_root = tmp_path
    config_dir = project_root / "config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        """
openai:
  base_url: https://local.example/v1
""",
        encoding="utf-8",
    )
    mounted_config = tmp_path / "mounted-app.yaml"
    mounted_config.write_text(
        """
openai:
  base_url: https://mounted.example/v1
""",
        encoding="utf-8",
    )
    _clear_project_env(monkeypatch)
    monkeypatch.setenv(CONFIG_FILE_ENV_KEY, str(mounted_config))

    load_local_env(project_root)

    assert os.environ["OPENAI_BASE_URL"] == "https://mounted.example/v1"


def test_load_yaml_config_values_rejects_non_mapping(tmp_path):
    config_path = tmp_path / "app.yaml"
    config_path.write_text("- invalid\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_yaml_config_values(config_path)


def _clear_project_env(monkeypatch):
    for key in PROJECT_ENV_KEYS | {CONFIG_FILE_ENV_KEY}:
        monkeypatch.delenv(key, raising=False)
