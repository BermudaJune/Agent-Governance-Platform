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

For a real model smoke test, set the key referenced by `config/examples/local.openai.yaml`.

```powershell
$env:XINGWAN_API_KEY="..."
```

## Core Concepts

- `AgentSpec` defines capability.
- `SessionRecord` stores long-running context.
- `RunRecord` is one auditable execution.
- `RunStep` is append-only evidence.
- `PolicyDecision`, `Approval`, `BudgetLedgerEntry`, and `SandboxActionRecord` are governance records.

## MVP Rule

The scripted test harness may replace external model/tool behavior, but it must still pass through the same RunService, PolicyEngine, BudgetService, EventStream, ApprovalService, and SandboxService chain.
