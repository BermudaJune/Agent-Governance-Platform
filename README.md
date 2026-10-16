# Agent Governance Platform

Agent Governance Platform is a Python-first MVP for learning and building agent governance: sessions, runs, append-only events, model gateway, tool gateway, budget ledger, policy decisions, HITL, sandbox actions, multi-agent coordination, trace, and experience candidates.

## Local Setup

```powershell
cd D:\A实习D\agent-governance-platform
python -m pip install -e .
python -m agentgov.cli --help
python -m agentgov.cli config validate config/examples/local.scripted.yaml
python -m agentgov.cli db init --database sqlite:///./data/agentgov.db
python -m agentgov.cli qualification run --config config/examples/qualification.yaml
```

For the real OpenAI-compatible provider, keep the key out of YAML and set the environment variable referenced by `config/examples/local.openai.yaml`.

```powershell
$env:XINGWAN_API_KEY="your-xingwan-key"
python -m agentgov.cli api --host 127.0.0.1 --port 8001 --config config/examples/local.openai.yaml
```

The current provider is `xingwan-gpt`, using `https://xingwan.store/v1` and model `gpt-5.5`. The web console reads provider status through `/config`, but never receives the secret. Restart the backend after changing provider or model settings.

## Skills and artifact tools

The resource center exposes platform skill packs for visual diagrams, charts, PowerPoint, Excel, Word, PDF, research, data analysis, engineering review, and governance. A Skill is a versioned workflow description; a Tool is the governed executor that can read data or write a Session artifact.

Local skills are discovered from `.agentgov/skills`, `.mewcode/skills`, `~/.agentgov/skills`, and `~/.mewcode/skills`. Public GitHub repositories can be scanned with `POST /skills/github/scan`; the importer pins a commit SHA, hashes the prompt, and marks suspicious content for review. It does not execute repository code.

Install the optional artifact libraries when you want actual Office/PDF output:

```powershell
python -m pip install -e ".[artifacts]"
```

The new executors are `mermaid_render`, `matplotlib_chart`, `spreadsheet_write`, `pptx_generate`, `document_generate`, `pdf_export`, `csv_analyze`, and `sqlite_query`. Generated files stay under `data/workspaces/<session_id>/artifacts` and are recorded as evidence and artifacts.

## Core Concepts

- `AgentSpec` defines capability.
- `SessionRecord` stores long-running context.
- `RunRecord` is one auditable execution.
- `RunStep` is append-only evidence.
- `PolicyDecision`, `Approval`, `BudgetLedgerEntry`, and `SandboxActionRecord` are governance records.

## MVP Rule

The scripted test harness may replace external model/tool behavior, but it must still pass through the same RunService, PolicyEngine, BudgetService, EventStream, ApprovalService, and SandboxService chain.
