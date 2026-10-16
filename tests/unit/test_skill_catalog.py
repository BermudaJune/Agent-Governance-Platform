from __future__ import annotations

from agentgov.skills.catalog import discover_local_skills


def test_discover_mewcode_skill_md_and_scan_risk(tmp_path):
    skill_dir = tmp_path / ".mewcode" / "skills" / "web-research"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: web-research\ndescription: Research with citations\nversion: 2.1.0\n---\nUse curl only after approval.\n",
        encoding="utf-8",
    )

    rows = discover_local_skills(tmp_path)

    assert len(rows) == 1
    assert rows[0]["id"] == "local.mewcode.web-research"
    assert rows[0]["version"] == "2.1.0"
    assert rows[0]["scan_status"] == "review"
    assert rows[0]["scan_findings"]


def test_discover_skill_yaml_prompt_pair(tmp_path):
    skill_dir = tmp_path / ".agentgov" / "skills" / "slides"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.yaml").write_text(
        "name: slide-builder\ndescription: Build slides\nrisk_level: medium\n",
        encoding="utf-8",
    )
    (skill_dir / "prompt.md").write_text("Create a slide outline and validate overflow.", encoding="utf-8")

    rows = discover_local_skills(tmp_path)

    assert rows[0]["name"] == "slide-builder"
    assert rows[0]["prompt_body"].startswith("Create a slide")
    assert rows[0]["scan_status"] == "passed"
