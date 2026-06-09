from pathlib import Path


def test_agent_skill_description_files_exist():
    repo_root = Path(__file__).resolve().parents[2]

    for skill_name in [
        "qc_document_review",
        "tobacco_license_consistency_review",
        "contract_review",
    ]:
        skill_doc = repo_root / ".agents" / "skills" / skill_name / "SKILL.md"
        content = skill_doc.read_text(encoding="utf-8")

        assert skill_doc.exists()
        assert "## 能力边界" in content
        assert "## 与 Python Runtime 的关系" in content
        assert "不在 `SKILL.md` 中编写" in content
