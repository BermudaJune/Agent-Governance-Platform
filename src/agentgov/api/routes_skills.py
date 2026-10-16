from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel

from agentgov.config.loader import load_config
from agentgov.config.schema import PlatformConfig, SkillConfig
from agentgov.skills.catalog import discover_local_skills, scan_github_skills, search_github_skill_repositories
from agentgov.skills.packs import built_in_skill_catalog
from agentgov.capabilities.requirements import RequirementAnalyzer


class RegisterSkillRequest(BaseModel):
    skill: SkillConfig
    approved: bool = False


class RegisterSkillBatchRequest(BaseModel):
    skills: list[SkillConfig]
    approved: bool = False


class GitHubSkillScanRequest(BaseModel):
    url: str
    ref: str | None = None
    subpath: str | None = None


class GitHubSkillSearchRequest(BaseModel):
    query: str = ""
    per_page: int = 20


def _skill_rows(cfg: PlatformConfig) -> list[dict[str, Any]]:
    return [skill.model_dump(mode="json") for skill in cfg.skills]


def _recommend_skills(cfg: PlatformConfig, task: str) -> dict[str, Any]:
    requirement = RequirementAnalyzer().analyze(task)
    task_words = {word for word in task.lower().replace("/", " ").replace("-", " ").split() if len(word) > 1}
    installed_ids = {skill.id for skill in cfg.skills}
    all_skills = list(cfg.skills)
    for item in CATALOG + built_in_skill_catalog():
        if item["id"] not in installed_ids:
            all_skills.append(SkillConfig.model_validate(item))
    rows = []
    for skill in all_skills:
        capabilities = set(skill.capability_ids)
        searchable = " ".join([skill.id, skill.name, skill.description, skill.category, *skill.tags, *skill.recommended_tools]).lower()
        keyword_hits = sum(1 for word in task_words if word in searchable)
        capability_hits = len(capabilities & set(requirement.required_capabilities))
        score = capability_hits * 5 + keyword_hits
        if score <= 0:
            continue
        rows.append({
            **skill.model_dump(mode="json"),
            "score": score,
            "matched_capabilities": sorted(capabilities & set(requirement.required_capabilities)),
            "missing_tools": [],
            "installed": skill.id in installed_ids,
        })
    rows.sort(key=lambda item: (-int(item["score"]), item["name"]))
    recommended_tools = sorted({tool for row in rows[:6] for tool in row.get("recommended_tools", [])})
    return {
        "task": task,
        "required_capabilities": requirement.required_capabilities,
        "required_roles": requirement.required_roles,
        "risk_hints": requirement.risk_hints,
        "expected_artifacts": requirement.expected_artifacts,
        "recommended_tools": recommended_tools,
        "skills": rows[:8],
    }


CATALOG: list[dict[str, Any]] = [
    {
        "id": "repo.research.pro",
        "name": "Repository Research Pro",
        "description": "先建立文件证据，再输出带引用的仓库分析。适合代码理解、影响面评估和审计准备。",
        "recommended_tools": ["repo_list", "repo_search", "repo_read"],
        "output_artifacts": ["research_notes", "evidence_report"],
        "capability_ids": ["repo.list", "repo.search", "repo.read"],
        "risk_level": "low",
        "source": "open-source-catalog",
        "source_url": None,
        "version": "1.0.0",
        "trust_level": "reviewed",
        "install_mode": "metadata_only",
    },
    {
        "id": "review.code-governance",
        "name": "Code Governance Review",
        "description": "从正确性、风险、权限和可回滚性检查代码变更，并形成审计友好的结论。",
        "recommended_tools": ["repo_search", "repo_read", "file_write"],
        "output_artifacts": ["review_report"],
        "capability_ids": ["repo.search", "repo.read", "review.policy", "file.write"],
        "risk_level": "medium",
        "source": "open-source-catalog",
        "source_url": None,
        "version": "1.0.0",
        "trust_level": "community",
        "install_mode": "metadata_only",
    },
    {
        "id": "knowledge.evidence-search",
        "name": "Knowledge Evidence Search",
        "description": "从项目知识库检索相关片段，要求输出来源、版本和证据引用。",
        "recommended_tools": ["repo_search", "repo_read"],
        "output_artifacts": ["citation_bundle"],
        "capability_ids": ["repo.search", "repo.read"],
        "risk_level": "low",
        "source": "platform-catalog",
        "source_url": None,
        "version": "0.1.0",
        "trust_level": "platform",
        "install_mode": "metadata_only",
    },
    {
        "id": "task.plan-and-delegate",
        "name": "Task Plan and Delegate",
        "description": "把用户任务拆成可观察的 DAG，并为每个节点声明 Agent、工具和产物契约。",
        "recommended_tools": ["repo_list", "repo_search"],
        "output_artifacts": ["task_plan"],
        "capability_ids": ["coordination.plan", "coordination.delegate"],
        "risk_level": "medium",
        "source": "platform-catalog",
        "source_url": None,
        "version": "0.1.0",
        "trust_level": "platform",
        "install_mode": "metadata_only",
    },
]


def router(config_path: str) -> APIRouter:
    r = APIRouter(prefix="/skills", tags=["skills"])
    path = Path(config_path)

    @r.get("")
    def list_skills():
        cfg = load_config(path)
        installed = {skill.id for skill in cfg.skills}
        rows = []
        for skill in cfg.skills:
            rows.append({**skill.model_dump(mode="json"), "installed": True, "available": True})
        catalog = CATALOG + built_in_skill_catalog()
        for item in catalog:
            if item["id"] not in installed:
                rows.append({**item, "installed": False, "available": True})
        for item in discover_local_skills(Path.cwd()):
            if item["id"] not in installed and not any(row["id"] == item["id"] for row in rows):
                rows.append({**item, "installed": False, "available": True})
        return rows

    @r.get("/recommend")
    def recommend_skills(task: str = ""):
        cfg = load_config(path)
        return _recommend_skills(cfg, task.strip()) if task.strip() else {
            "task": "", "required_capabilities": [], "required_roles": [], "risk_hints": [],
            "expected_artifacts": [], "recommended_tools": [], "skills": [],
        }

    @r.post("/github/scan")
    def scan_github(req: GitHubSkillScanRequest):
        try:
            result = scan_github_skills(req.url, req.ref, req.subpath)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"GitHub Skill 扫描失败：{exc}") from exc
        return result

    @r.post("/github/search")
    def search_github(req: GitHubSkillSearchRequest):
        try:
            return {"results": search_github_skill_repositories(req.query, req.per_page)}
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"GitHub Skill search failed: {exc}") from exc

    @r.post("/register")
    def register_skill(req: RegisterSkillRequest):
        if req.skill.scan_status == "review" and not req.approved:
            raise HTTPException(status_code=409, detail="skill has scan findings; review and set approved=true to register")
        return _register(path, [req.skill])

    @r.post("/register-batch")
    def register_skill_batch(req: RegisterSkillBatchRequest):
        reviewed = [skill.id for skill in req.skills if skill.scan_status == "review"]
        if reviewed and not req.approved:
            raise HTTPException(status_code=409, detail={"message": "some skills have scan findings", "skill_ids": reviewed})
        return _register(path, req.skills)

    return r


def _register(path: Path, incoming: list[SkillConfig]) -> dict[str, Any]:
        cfg = load_config(path)
        incoming_by_id = {skill.id: skill for skill in incoming}
        skills = [skill for skill in cfg.skills if skill.id not in incoming_by_id]
        skills.extend(incoming)
        data = cfg.model_dump(mode="json")
        data["skills"] = [skill.model_dump(mode="json") for skill in skills]
        next_cfg = PlatformConfig.model_validate(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(next_cfg.model_dump(mode="json"), allow_unicode=True, sort_keys=False), encoding="utf-8")
        return {"registered": True, "count": len(incoming), "skills": [skill.model_dump(mode="json") for skill in incoming], "restart_required": False}
