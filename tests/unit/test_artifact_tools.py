from agentgov.gateway.tool_registry import ToolExecutionContext, ToolRegistry, builtin_tool_specs
from agentgov.providers.local_repo_tools import LocalRepoTools
from agentgov.skills.packs import built_in_skill_catalog


def test_platform_skill_pack_covers_office_visual_and_data():
    rows = built_in_skill_catalog()
    categories = {row["category"] for row in rows}

    assert len(rows) >= 18
    assert {"office", "visual", "data"}.issubset(categories)
    assert any(row["id"] == "office.pptx-deck" for row in rows)


def test_artifact_tools_create_session_files(tmp_path):
    repo_tools = LocalRepoTools(str(tmp_path))
    registry = ToolRegistry(repo_tools=repo_tools)
    for spec in builtin_tool_specs():
        registry.register(spec)
    context = ToolExecutionContext("run-1", "session-1", "agent-1")

    workbook = registry.execute(registry.get("spreadsheet_write"), context, {
        "name": "report",
        "sheets": {"Summary": {"headers": ["Metric", "Value"], "rows": [["count", 2]]}},
    })
    chart = registry.execute(registry.get("matplotlib_chart"), context, {
        "name": "trend",
        "labels": ["A", "B"],
        "values": [1, 2],
    })

    assert workbook["status"] == "completed"
    assert chart["status"] == "completed"
    assert (tmp_path / "data" / "workspaces" / "session-1" / "artifacts" / "report.xlsx").is_file()
    assert (tmp_path / "data" / "workspaces" / "session-1" / "artifacts" / "trend.png").is_file()
