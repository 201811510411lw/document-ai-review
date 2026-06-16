from pathlib import Path


def test_agent_skill_description_files_exist():
    repo_root = Path(__file__).resolve().parents[2]

    for skill_name in [
        "business-license-review",
        "food-license-review",
        "qc-document-review",
    ]:
        skill_doc = repo_root / ".agents" / "skills" / skill_name / "SKILL.md"
        content = skill_doc.read_text(encoding="utf-8")

        assert skill_doc.exists()
        assert f"name: {skill_name}" in content
        assert "## 能力边界" in content
        assert "审核规则" in content
