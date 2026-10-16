from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml


MAX_SKILL_BYTES = 512 * 1024
DANGEROUS_PATTERNS = (
    (r"(?i)\b(subprocess|os\.system|child_process|Invoke-WebRequest|curl|wget)\b", "可能执行命令或联网"),
    (r"(?i)\b(os\.environ|process\.env|秘密|secret|api[_ -]?key|token)\b", "可能读取凭据或敏感环境变量"),
    (r"(?i)\b(rm\s+-rf|del\s+/s|format\s+[a-z]:|shutil\.rmtree)\b", "可能执行破坏性文件操作"),
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip(".-_").lower()
    return value or "skill"


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    stripped = text.lstrip("\ufeff")
    if not stripped.startswith("---"):
        return {}, text
    lines = stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    closing = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        return {}, text
    metadata = yaml.safe_load("\n".join(lines[1:closing])) or {}
    return (metadata if isinstance(metadata, dict) else {}), "\n".join(lines[closing + 1:]).lstrip("\n")


def _scan(text: str, metadata: dict[str, Any]) -> tuple[str, list[str]]:
    findings: list[str] = []
    for pattern, message in DANGEROUS_PATTERNS:
        if re.search(pattern, text):
            findings.append(message)
    for item in metadata.get("scan_exceptions", []) if isinstance(metadata.get("scan_exceptions"), list) else []:
        findings.append(f"metadata requested exception: {item}")
    if findings:
        return "review", sorted(set(findings))
    return "passed", []


def _candidate(
    *,
    metadata: dict[str, Any],
    prompt_body: str,
    source: str,
    source_url: str | None,
    source_ref: str | None,
    identity: str,
) -> dict[str, Any]:
    name = str(metadata.get("name") or identity.split(".")[-1])
    description = str(metadata.get("description") or "")
    scan_status, findings = _scan(prompt_body, metadata)
    declared_risk = str(metadata.get("risk_level") or "low")
    risk_level = "high" if scan_status == "review" else declared_risk
    return {
        "id": identity,
        "name": name,
        "description": description,
        "prompt_body": prompt_body,
        "recommended_tools": [str(item) for item in metadata.get("recommended_tools", []) if isinstance(item, (str, int))],
        "output_artifacts": [str(item) for item in metadata.get("output_artifacts", []) if isinstance(item, (str, int))],
        "capability_ids": [str(item) for item in metadata.get("capability_ids", []) if isinstance(item, (str, int))],
        "risk_level": risk_level,
        "source": source,
        "source_url": source_url,
        "source_ref": source_ref,
        "version": str(metadata.get("version") or (f"git-{source_ref[:12]}" if source_ref else "unversioned")),
        "trust_level": "unverified" if scan_status == "review" else str(metadata.get("trust_level") or "community"),
        "install_mode": "github_import" if source.startswith("github:") else "mewcode_import",
        "content_hash": _hash(prompt_body),
        "scan_status": scan_status,
        "scan_findings": findings,
        "license": metadata.get("license"),
        "category": str(metadata.get("category") or "general"),
        "tags": [str(item) for item in metadata.get("tags", []) if isinstance(item, (str, int))],
    }


def _skill_file_candidate(path: Path, source: str) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_SKILL_BYTES:
            return None
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    metadata, prompt_body = _parse_frontmatter(raw)
    if not metadata.get("name") or not metadata.get("description"):
        return None
    return _candidate(
        metadata=metadata,
        prompt_body=prompt_body,
        source=source,
        source_url=None,
        source_ref=str(path),
        identity=f"local.mewcode.{_slug(str(metadata['name']))}",
    )


def discover_local_skills(work_dir: str | Path = ".") -> list[dict[str, Any]]:
    root = Path(work_dir).resolve()
    directories = [
        root / ".agentgov" / "skills",
        root / ".mewcode" / "skills",
        Path.home() / ".agentgov" / "skills",
        Path.home() / ".mewcode" / "skills",
    ]
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            candidate: dict[str, Any] | None = None
            if path.name.lower() == "skill.md" or path.suffix.lower() == ".md":
                candidate = _skill_file_candidate(path, "local:mewcode")
            elif path.name.lower() == "skill.yaml":
                try:
                    metadata = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    prompt_path = path.parent / "prompt.md"
                    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
                    if isinstance(metadata, dict) and metadata.get("name") and metadata.get("description"):
                        candidate = _candidate(
                            metadata=metadata,
                            prompt_body=prompt,
                            source="local:mewcode",
                            source_url=None,
                            source_ref=str(path.parent),
                            identity=f"local.mewcode.{_slug(str(metadata['name']))}",
                        )
                except (OSError, UnicodeDecodeError, yaml.YAMLError):
                    candidate = None
            if candidate and candidate["id"] not in seen:
                seen.add(candidate["id"])
                results.append(candidate)
    return results


def _github_parts(url: str) -> tuple[str, str, str | None, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != "github.com":
        raise ValueError("仅支持 github.com 仓库地址")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub 地址必须包含 owner/repository")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = None
    subpath = None
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        ref = parts[3]
        subpath = "/".join(parts[4:]) or None
    return owner, repo, ref, subpath


def scan_github_skills(url: str, ref: str | None = None, subpath: str | None = None) -> dict[str, Any]:
    owner, repo, embedded_ref, embedded_path = _github_parts(url)
    requested_ref = ref or embedded_ref
    requested_path = subpath or embedded_path
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "agentgov-skill-importer"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = f"https://api.github.com/repos/{owner}/{repo}"
    # GitHub's recursive tree endpoint can be slow for monorepos. Keep imports
    # bounded so a scan is a fast discovery action rather than a long-running
    # request that blocks the API worker.
    with httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=True, headers=headers) as client:
        repo_info = client.get(base)
        repo_info.raise_for_status()
        branch = requested_ref or repo_info.json().get("default_branch") or "main"
        commit_response = client.get(f"{base}/commits/{branch}")
        commit_response.raise_for_status()
        commit_sha = str(commit_response.json().get("sha") or branch)
        tree_response = client.get(f"{base}/git/trees/{commit_sha}", params={"recursive": "1"})
        tree_response.raise_for_status()
        tree_payload = tree_response.json()
        tree = tree_payload.get("tree", [])
        paths = [str(item.get("path")) for item in tree if item.get("type") == "blob" and item.get("path")]
        if requested_path:
            prefix = requested_path.strip("/") + "/"
            paths = [path for path in paths if path == requested_path.strip("/") or path.startswith(prefix)]
        skill_paths = [path for path in paths if path.lower().endswith("/skill.md") or path.lower() == "skill.md"]
        yaml_paths = [path for path in paths if path.lower().endswith("/skill.yaml") or path.lower() == "skill.yaml"]
        candidates: list[dict[str, Any]] = []
        raw_base = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_sha}"
        for path in skill_paths[:30]:
            response = client.get(f"{raw_base}/{path}")
            response.raise_for_status()
            if len(response.content) > MAX_SKILL_BYTES:
                continue
            metadata, prompt = _parse_frontmatter(response.text)
            if not metadata.get("name") or not metadata.get("description"):
                continue
            candidates.append(_candidate(
                metadata=metadata,
                prompt_body=prompt,
                source=f"github:{owner}/{repo}",
                source_url=f"https://github.com/{owner}/{repo}/tree/{commit_sha}/{path.rsplit('/', 1)[0] if '/' in path else ''}".rstrip("/"),
                source_ref=commit_sha,
                identity=f"github.{_slug(owner)}.{_slug(repo)}.{_slug(str(metadata['name']))}",
            ))
        for path in yaml_paths[:max(0, 30 - len(skill_paths[:30]))]:
            prompt_path = f"{path.rsplit('/', 1)[0]}/prompt.md" if "/" in path else "prompt.md"
            if prompt_path not in paths:
                continue
            metadata_response = client.get(f"{raw_base}/{path}")
            prompt_response = client.get(f"{raw_base}/{prompt_path}")
            metadata_response.raise_for_status()
            prompt_response.raise_for_status()
            metadata = yaml.safe_load(metadata_response.text) or {}
            if not isinstance(metadata, dict) or not metadata.get("name") or not metadata.get("description"):
                continue
            candidates.append(_candidate(
                metadata=metadata,
                prompt_body=prompt_response.text,
                source=f"github:{owner}/{repo}",
                source_url=f"https://github.com/{owner}/{repo}/tree/{commit_sha}/{path.rsplit('/', 1)[0] if '/' in path else ''}".rstrip("/"),
                source_ref=commit_sha,
                identity=f"github.{_slug(owner)}.{_slug(repo)}.{_slug(str(metadata['name']))}",
            ))
    unique = {item["id"]: item for item in candidates}
    return {
        "repository": f"{owner}/{repo}",
        "ref": branch,
        "commit_sha": commit_sha,
        "truncated": bool(tree_payload.get("truncated")) or len(skill_paths) + len(yaml_paths) > 30,
        "candidates": list(unique.values()),
    }


def search_github_skill_repositories(query: str = "", per_page: int = 20) -> list[dict[str, Any]]:
    """Find public repositories containing SKILL.md without downloading or executing them."""
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "agentgov-skill-search"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    search_query = f"{query.strip()} filename:SKILL.md".strip()
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=headers) as client:
        if token:
            response = client.get("https://api.github.com/search/code", params={"q": search_query, "per_page": max(1, min(per_page, 50))})
        else:
            response = client.get("https://api.github.com/search/repositories", params={"q": f"{query.strip()} skills".strip(), "per_page": max(1, min(per_page, 50)), "sort": "stars"})
        if response.status_code in {401, 403} and token:
            response = client.get("https://api.github.com/search/repositories", params={"q": f"{query.strip()} skills".strip(), "per_page": max(1, min(per_page, 50)), "sort": "stars"})
        response.raise_for_status()
        items = response.json().get("items", [])
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        repository = item.get("repository") or item
        full_name = str(repository.get("full_name") or "")
        if not full_name or full_name in seen:
            continue
        seen.add(full_name)
        results.append({
            "repository": full_name,
            "path": item.get("path"),
            "url": f"https://github.com/{full_name}",
            "default_branch": repository.get("default_branch") or "main",
            "description": repository.get("description") or "",
            "stars": repository.get("stargazers_count", 0),
        })
    return results
