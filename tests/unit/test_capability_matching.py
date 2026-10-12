from __future__ import annotations

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.capabilities.requirements import RequirementAnalyzer
from agentgov.config.loader import load_config
from agentgov.teams.matching import TeamMatcher


def test_requirement_analyzer_detects_non_programming_capabilities():
    requirement = RequirementAnalyzer().analyze("查询杭州天气，写一首诗到 D:\\agent_outputs\\poem.md，再让另一个 Agent 鉴赏")

    assert "external.weather" in requirement.required_capabilities
    assert "text.create" in requirement.required_capabilities
    assert "file.write" in requirement.required_capabilities
    assert "review.content" in requirement.required_capabilities
    assert "D:\\agent_outputs\\poem.md" in requirement.path_requirements


def test_team_matching_reports_missing_weather_capability():
    cfg = load_config("config/examples/local.scripted.yaml")
    registry = CapabilityRegistry(cfg)
    requirement = RequirementAnalyzer().analyze("查询天气，写一首诗到文件，再让另一个 Agent 鉴赏")
    report = TeamMatcher(registry).match_team(requirement, ["story_writer", "story_reviewer"], team_id="story_team")

    assert report.score < 1
    assert "external.weather" in report.missing_capabilities
    assert report.decision in {"adjust", "approval_required", "block"}


def test_team_matching_covers_story_capabilities():
    cfg = load_config("config/examples/local.scripted.yaml")
    registry = CapabilityRegistry(cfg)
    requirement = RequirementAnalyzer().analyze("写一首诗到文件，再让另一个 Agent 鉴赏")
    report = TeamMatcher(registry).match_team(requirement, ["story_writer", "story_reviewer"], team_id="story_team")

    assert report.score == 1
    assert not report.missing_capabilities
    assert "file.write" in report.covered_capabilities
    assert "review.content" in report.covered_capabilities
