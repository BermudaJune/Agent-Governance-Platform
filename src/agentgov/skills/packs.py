from __future__ import annotations

from typing import Any


def built_in_skill_catalog() -> list[dict[str, Any]]:
    """Return discoverable workflows that are safe to register as metadata."""
    rows = [
        ("visual.flowchart", "Flowchart Builder", "Turn a task plan into a Mermaid flowchart and a reviewable diagram artifact.", ["mermaid_render"], ["visual.diagram"], "visual", ["diagram", "mermaid"]),
        ("visual.architecture", "Architecture Diagram", "Create an architecture view with services, data stores, boundaries and evidence links.", ["mermaid_render"], ["visual.diagram"], "visual", ["architecture", "topology"]),
        ("visual.data-chart", "Data Chart", "Convert structured data into a PNG chart with a caption and source metadata.", ["matplotlib_chart"], ["visual.chart", "data.analysis"], "visual", ["chart", "png"]),
        ("visual.image-brief", "Image Brief", "Prepare a structured image-generation brief with dimensions, style, subject and safety constraints.", ["file_write"], ["visual.image_brief"], "visual", ["image", "brief"]),
        ("office.pptx-deck", "Presentation Deck", "Plan and generate a slide deck with title, agenda, evidence slides and speaker notes.", ["pptx_generate", "pptx_validate"], ["office.presentation"], "office", ["pptx", "slides"]),
        ("office.excel-report", "Excel Report", "Build a workbook with typed columns, summary sheets, formulas and validation notes.", ["spreadsheet_write", "spreadsheet_validate"], ["office.spreadsheet", "data.analysis"], "office", ["excel", "xlsx"]),
        ("office.word-brief", "Word Brief", "Create a structured Word brief with headings, tables, references and an executive summary.", ["document_generate"], ["office.document"], "office", ["word", "docx"]),
        ("office.pdf-report", "PDF Report", "Export a traceable report with source citations, findings and an appendix.", ["pdf_export", "pdf_validate"], ["office.pdf"], "office", ["pdf", "report"]),
        ("research.web-evidence", "Web Evidence Research", "Collect web evidence, preserve URLs and produce a cited research memo.", ["http_get", "file_write"], ["research.web", "research.citations"], "research", ["web", "evidence"]),
        ("research.github-research", "GitHub Repository Research", "Inspect a GitHub repository and produce a commit-pinned technical brief.", ["http_get", "repo_search", "file_write"], ["research.web", "research.citations"], "research", ["github", "repository"]),
        ("research.citation-audit", "Citation Audit", "Check claims against source references and flag unsupported conclusions.", ["file_read", "file_write"], ["research.citations", "governance.trace"], "research", ["citations", "audit"]),
        ("data.csv-analysis", "CSV Analysis", "Inspect a CSV, calculate descriptive statistics and write an auditable summary.", ["csv_analyze", "spreadsheet_write"], ["data.analysis", "office.spreadsheet"], "data", ["csv", "statistics"]),
        ("data.sqlite-analysis", "SQLite Analysis", "Query a Session knowledge database and return a reproducible result table.", ["sqlite_query", "spreadsheet_write"], ["data.analysis"], "data", ["sqlite", "query"]),
        ("engineering.api-design", "API Design Review", "Review an API contract for consistency, errors, authorization and observability.", ["repo_search", "repo_read", "file_write"], ["review.policy", "governance.trace"], "engineering", ["api", "design"]),
        ("engineering.test-analysis", "Test Analysis", "Map changed behavior to tests, identify gaps and produce a prioritized test plan.", ["repo_search", "repo_read", "file_write"], ["review.content", "governance.trace"], "engineering", ["tests", "quality"]),
        ("engineering.dependency-audit", "Dependency Audit", "Inventory dependencies, licenses and upgrade risks with evidence.", ["repo_search", "file_write"], ["review.policy", "research.citations"], "engineering", ["dependencies", "license"]),
        ("governance.trace-review", "Trace Review", "Summarize a Session trace by decision, tool, artifact, approval and exception.", ["file_write"], ["governance.trace"], "governance", ["trace", "audit"]),
        ("governance.incident-review", "Incident Review", "Turn failed or blocked Runs into a timeline, root-cause candidates and follow-up actions.", ["file_read", "file_write"], ["governance.trace", "review.policy"], "governance", ["incident", "postmortem"]),
        ("coordination.team-brief", "Team Brief", "Give a leader a concise Session brief with assignments, handoffs, risks and acceptance criteria.", ["file_write"], ["coordination.plan", "coordination.delegate"], "coordination", ["team", "leader"]),
    ]
    return [
        {
            "id": skill_id,
            "name": name,
            "description": description,
            "recommended_tools": tools,
            "output_artifacts": ["session_artifact"],
            "capability_ids": capabilities,
            "risk_level": "medium" if category in {"office", "visual"} else "low",
            "source": "platform-pack",
            "source_url": None,
            "version": "1.0.0",
            "trust_level": "platform",
            "install_mode": "metadata_only",
            "category": category,
            "tags": tags,
        }
        for skill_id, name, description, tools, capabilities, category, tags in rows
    ]
