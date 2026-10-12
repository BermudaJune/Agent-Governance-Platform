# Agent Governance Platform Tasks

## File List

| Action | File | Responsibility |
|---|---|---|
| Create | `pyproject.toml` | Python project metadata, dependencies, dev commands |
| Create | `README.md` | Local setup, architecture summary, MVP runbook |
| Create | `config/examples/local.openai.yaml` | Real OpenAI-compatible local config |
| Create | `config/examples/local.scripted.yaml` | Deterministic test harness config |
| Create | `config/examples/qualification.yaml` | Multi-agent qualification scenario config |
| Create | `src/agentgov/app.py` | FastAPI app factory |
| Create | `src/agentgov/cli.py` | Local commands: init db, run worker, run qualification |
| Create | `src/agentgov/config/*` | YAML schema, loader, registry |
| Create | `src/agentgov/storage/*` | SQLAlchemy models, DB session, repositories |
| Create | `src/agentgov/infrastructure/*` | RelationalStore, EventBus, RateLimiter, ObjectStore, VectorStore adapters |
| Create | `src/agentgov/event_stream/*` | RunStep append/query/SSE |
| Create | `src/agentgov/control_plane/*` | Agent/team/session registry and locks |
| Create | `src/agentgov/runtime/*` | RunService, state machine, AgentLoop |
| Create | `src/agentgov/scheduler/*` | DB-backed RunQueue, RunLease, RunWorker |
| Create | `src/agentgov/permission/*` | IdentityContext, ResourceRef, DelegationGrant, permission checks |
| Create | `src/agentgov/policy/*` | PolicyEngine and built-in rules |
| Create | `src/agentgov/budget/*` | Budget snapshots, ledger, pricing, reserve/settle/release |
| Create | `src/agentgov/approval/service.py` | HITL request/decide/resume support |
| Create | `src/agentgov/trace/*` | TraceContext, SpanRecord, EvidenceRef, ReasoningTrace |
| Create | `src/agentgov/providers/*` | OpenAI-compatible provider, local repo tools, scripted test providers |
| Create | `src/agentgov/gateway/*` | ModelGateway, ToolGateway, MCP adapter boundary |
| Create | `src/agentgov/sandbox/*` | Local read-only sandbox, fault injection sandbox |
| Create | `src/agentgov/collaboration/*` | CollaborationService, TeamBus, LeaderWorkerStrategy |
| Create | `src/agentgov/memory/*` | MemoryStore, ExperienceService, versioning |
| Create | `src/agentgov/dashboard/*` | Backend aggregation for dashboard, topology, audit queries |
| Create | `src/agentgov/api/*` | FastAPI routes for agents, sessions, runs, approvals, dashboard |
| Create | `src/agentgov/testing/*` | Scripted model/tool, fault injection, replay, qualification runner |
| Create | `tests/unit/*` | Unit tests for state, policy, budget, queue, trace |
| Create | `tests/integration/*` | Integration tests for run flow, HITL, sandbox, multi-agent |
| Create | `tests/e2e/*` | Qualification scenario and smoke tests |
| Create | `web/package.json` | Frontend dependencies and scripts |
| Create | `web/src/*` | React governance console |

## T1: Project Skeleton And Tooling

**Files:** `pyproject.toml`, `README.md`, `src/agentgov/__init__.py`, `src/agentgov/app.py`, `src/agentgov/cli.py`

**Dependencies:** None

**Steps:**
1. Define Python package metadata and dependencies: FastAPI, SQLAlchemy async, Pydantic, Typer, httpx, aiosqlite, PyYAML, pytest.
2. Create minimal app factory and CLI entry point.
3. Document local setup, expected environment variables, and development commands.

**Validation:** Run `python -m agentgov.cli --help`; expect CLI help output. Run `pytest`; expect test discovery succeeds even before feature tests are added.

## T2: Configuration Schema And Registry

**Files:** `src/agentgov/config/schema.py`, `src/agentgov/config/loader.py`, `src/agentgov/config/registry.py`, `config/examples/local.openai.yaml`, `config/examples/local.scripted.yaml`, `config/examples/qualification.yaml`

**Dependencies:** T1

**Steps:**
1. Define config models for providers, tools, agents, teams, policies, permissions, sandboxes, infrastructure, budgets.
2. Implement YAML loading and validation with clear error messages.
3. Create real OpenAI-compatible config and separate scripted test harness config.
4. Ensure API keys use `api_key_env`, never plain config secrets.

**Validation:** Run `python -m agentgov.cli config validate config/examples/local.openai.yaml`; expect valid config. Run with a missing provider reference; expect a clear validation error.

## T3: SQLAlchemy Models And Repositories

**Files:** `src/agentgov/storage/db.py`, `src/agentgov/storage/models.py`, `src/agentgov/storage/repositories.py`

**Dependencies:** T1, T2

**Steps:**
1. Implement tables from `plan.md`: sessions, runs, run_steps, model_calls, tool_calls, sandbox_actions, policy_decisions, approvals, budget_ledger, budget_snapshots, delegation_grants, span_records, evidence_refs, reasoning_traces, agent_messages, collaboration_tasks, run_queue, run_leases, memory_items, experience_candidates, agent_health_snapshots, agent_dependency_edges.
2. Add indexes for run trace, approval status, queue claims, trace lookup, audit query.
3. Implement repository methods for create/get/list/update on core tables.
4. Provide database initialization command.

**Validation:** Run `python -m agentgov.cli db init --database sqlite+aiosqlite:///./data/test.db`; expect tables created. Run repository smoke test; expect create/read of Session, Run, RunStep works after process restart.

## T4: Infrastructure Adapters

**Files:** `src/agentgov/infrastructure/relational.py`, `event_bus.py`, `rate_limiter.py`, `object_store.py`, `vector_store.py`

**Dependencies:** T3

**Steps:**
1. Implement `SqliteRelationalStore`.
2. Implement DB-backed rate limiter counters with in-memory cache.
3. Implement DB-backed event notification source plus in-memory pubsub for live SSE.
4. Implement `LocalObjectStore` for reports, snapshots, large event payloads.
5. Implement SQLite FTS or keyword index for memory search.

**Validation:** Run infrastructure unit tests; expect rate limit persists across service instances, local object store can write/read a report, and memory search finds committed text.

## T5: Event Stream And Audit Append

**Files:** `src/agentgov/event_stream/events.py`, `src/agentgov/event_stream/stream.py`, `src/agentgov/event_stream/sse.py`

**Dependencies:** T3, T4

**Steps:**
1. Define `EventType`, `ActorType`, `StepStatus`, event create schemas.
2. Implement append-only `RunStep` creation with monotonic `seq` per run.
3. Implement query by run, session, type, and time range.
4. Implement SSE/stream interface backed by DB event history and live notification.

**Validation:** Append three events to a run; expect seq `1,2,3`. Restart process and query events; expect all events retained. SSE test should receive newly appended event.

## T6: Control Plane: Agents, Teams, Sessions, Locks

**Files:** `src/agentgov/control_plane/agents.py`, `teams.py`, `sessions.py`, `locks.py`

**Dependencies:** T2, T3, T4

**Steps:**
1. Implement `AgentRegistry` from config and create `AgentVersion` snapshots.
2. Implement `TeamRegistry`.
3. Implement `SessionService` create/get/status.
4. Implement DB-backed `SessionLock` with timeout semantics.

**Validation:** Load qualification config; expect coordinator/evidence/execution/policy_auditor/reviewer resolvable. Attempt two write locks for same session; expect second fails or waits according to configured behavior.

## T7: Trace Plane

**Files:** `src/agentgov/trace/context.py`, `spans.py`, `evidence.py`, `reasoning.py`, `service.py`

**Dependencies:** T3, T5

**Steps:**
1. Implement `TraceContext` creation for runs and child runs.
2. Implement span start/finish for model/tool/sandbox/policy.
3. Implement evidence refs for files, run steps, tool results, reports.
4. Implement `ReasoningTrace` as auditable decision summary, not chain-of-thought storage.
5. Implement trace tree query.

**Validation:** Create parent and child runs; expect same trace tree with parent/child span relation. Record evidence ref and reasoning trace; expect run detail query can retrieve both.

## T8: Permission And Delegation

**Files:** `src/agentgov/permission/identity.py`, `resources.py`, `delegation.py`, `service.py`

**Dependencies:** T2, T3, T5, T7

**Steps:**
1. Implement `IdentityContext`, `ResourceRef`, `PermissionCheck`.
2. Implement role-based checks from config.
3. Implement delegation grants for coordinator-to-worker flow.
4. Record all allow/deny decisions as `PolicyDecision`.

**Validation:** Operator can create run but auditor cannot approve action. Coordinator can delegate to Evidence Agent only if config allows. Denied delegation must emit policy decision.

## T9: Policy Engine

**Files:** `src/agentgov/policy/context.py`, `decisions.py`, `rules.py`, `engine.py`

**Dependencies:** T8

**Steps:**
1. Implement `PolicyContext` and `PolicyDecisionResult`.
2. Implement built-in policies: identity, tool access, sandbox boundary, HITL, audit-required.
3. Ensure policy results can be `allow`, `deny`, `require_approval`, `pause`.
4. Append policy decision records consistently.

**Validation:** Tool write action in read-only sandbox returns `deny` or `require_approval` according to config. Every policy evaluation produces a queryable decision.

## T10: Budget Service

**Files:** `src/agentgov/budget/pricing.py`, `ledger.py`, `snapshot.py`, `service.py`

**Dependencies:** T2, T3, T5, T9

**Steps:**
1. Implement provider/model price table.
2. Implement budget subject resolution for global, team, agent, run, model.
3. Implement preflight estimate, reserve, settle, release.
4. Record budget ledger entries and policy decisions.
5. Handle model failure by releasing reservation.

**Validation:** Run budget unit tests for normal call, budget exceeded, provider failure release, actual cost greater than estimate. Expect ledger entries match each scenario.

## T11: Approval Service And HITL Resume

**Files:** `src/agentgov/approval/service.py`, `src/agentgov/api/routes_approvals.py`

**Dependencies:** T5, T9, T10

**Steps:**
1. Implement approval request creation from policy decisions.
2. Implement approval decide API for approve/reject.
3. On approve, allow run resume.
4. On reject, mark run rejected and append final event.

**Validation:** Trigger a write action requiring approval; expect run status `awaiting_approval`. Approve and resume; expect status returns to running. Reject; expect rejected final state and queryable reason.

## T12: Scheduler: DB-Backed Queue, Lease, Worker

**Files:** `src/agentgov/scheduler/queue.py`, `lease.py`, `worker.py`

**Dependencies:** T3, T4, T5

**Steps:**
1. Implement enqueue to `run_queue`.
2. Implement worker claim with `RunLease`.
3. Implement heartbeat, complete, fail.
4. Implement expired lease recovery.
5. Ensure run execution can be started by worker, not only API process.

**Validation:** Enqueue run, claim with worker, heartbeat, complete; expect queue status complete. Simulate lease expiry; expect another worker can reclaim or run marked failed according to policy.

## T13: Model Provider And Model Gateway

**Files:** `src/agentgov/providers/openai_compatible.py`, `src/agentgov/providers/scripted_model.py`, `src/agentgov/gateway/model.py`

**Dependencies:** T5, T7, T9, T10

**Steps:**
1. Implement OpenAI-compatible chat completion provider with usage parsing.
2. Implement scripted provider for Test Harness only.
3. Implement ModelGateway lifecycle: trace span, permission, policy, budget preflight, provider call, settle/release, model call record, events.
4. Add timeout and error handling.

**Validation:** Scripted model call passes through real gateway and produces model call event, budget ledger, span. OpenAI-compatible smoke test is skipped unless env key exists; if key exists, expect successful model call.

## T14: Tool Gateway And Local Repo Tools

**Files:** `src/agentgov/providers/local_repo_tools.py`, `local_command_tools.py`, `scripted_tools.py`, `mcp_tools.py`, `src/agentgov/gateway/tool.py`

**Dependencies:** T5, T7, T9, T11

**Steps:**
1. Implement `repo_search`, `repo_read`, `repo_list` as real local read-only tools.
2. Implement local command tool wrapper that delegates execution to SandboxService.
3. Implement scripted tools for Test Harness.
4. Implement ToolGateway lifecycle: trace span, permission, policy, possible approval, tool call record, event append.

**Validation:** Search current repo for known string; expect result summary and ToolCallRecord. Attempt forbidden tool action; expect deny or approval event.

## T15: Sandbox Service

**Files:** `src/agentgov/sandbox/base.py`, `local_readonly.py`, `fault_injection.py`, `service.py`

**Dependencies:** T5, T7, T9

**Steps:**
1. Implement `LocalReadOnlySandboxRuntime` with command allowlist, working directory boundary, timeout, env filtering, output truncation.
2. Implement fault injection sandbox for tests.
3. Implement SandboxService lifecycle: policy check, span, action record, event append.

**Validation:** Allowed `rg` command succeeds and is audited. Disallowed command fails before execution and creates policy decision. Timeout command records timeout result.

## T16: Runtime State Machine And RunService

**Files:** `src/agentgov/runtime/state_machine.py`, `run_service.py`, `agent_loop.py`, `errors.py`

**Dependencies:** T5, T6, T7, T10, T11, T12, T13, T14, T15

**Steps:**
1. Implement Run status transitions with explicit allowed transitions.
2. Implement create_run, execute, resume_run, finalize, mark_failed.
3. Implement AgentLoop against ModelGateway and tool intents.
4. Persist all status changes as events.
5. Ensure session write lock is respected.

**Validation:** Run scripted single-agent scenario; expect full event timeline, completed status, cost ledger, trace spans. Invalid status transition should raise controlled error and append failure event.

## T17: Collaboration, TeamBus, LeaderWorker Strategy

**Files:** `src/agentgov/collaboration/service.py`, `team_bus.py`, `strategies.py`, `leader_worker.py`

**Dependencies:** T8, T12, T16

**Steps:**
1. Implement AgentMessage persistence and query.
2. Implement CollaborationTask.
3. Implement LeaderWorkerStrategy for coordinator delegating to Evidence, Execution, Policy Auditor, Reviewer.
4. Create child runs with `parent_run_id` and shared trace context.
5. Collect child results and append collaboration result events.

**Validation:** Run a scripted leader-worker task; expect parent run, four child runs, task.assigned/task.result messages, trace tree, and final merged result.

## T18: Memory And Experience

**Files:** `src/agentgov/memory/store.py`, `experience.py`, `versioning.py`

**Dependencies:** T4, T5, T7, T16

**Steps:**
1. Implement MemoryItem persistence and SQLite FTS/keyword search.
2. Implement ExperienceService generation from RunStep, EvidenceRef, ReasoningTrace.
3. Implement evaluate, accept, reject, commit, rollback states.
4. Ensure committed memory keeps source run and evidence refs.

**Validation:** Completed run creates experience candidate. Accept and commit candidate; MemoryStore search finds it. Rollback marks memory inactive or reverted.

## T19: Dashboard Backend

**Files:** `src/agentgov/dashboard/service.py`, `health.py`, `topology.py`, `audit_query.py`

**Dependencies:** T3, T5, T7, T17

**Steps:**
1. Implement overview metrics: agent counts, running/error, success rate, latency, cost, approvals.
2. Implement Agent health snapshots from runs/events.
3. Implement topology edges from parent-child runs, delegation grants, agent messages.
4. Implement audit query filters by run, agent, event type, policy, approval status, time range.

**Validation:** Seed qualification run data; dashboard overview returns non-empty metrics, topology returns nodes/edges, audit query filters correctly.

## T20: API Routes

**Files:** `src/agentgov/api/routes_agents.py`, `routes_sessions.py`, `routes_runs.py`, `routes_approvals.py`, `routes_dashboard.py`, `src/agentgov/app.py`

**Dependencies:** T6, T11, T16, T19

**Steps:**
1. Implement health, agents, sessions, runs, events, stream, approvals, dashboard endpoints.
2. Wire app factory and config loading.
3. Add request/response schemas.
4. Ensure API never exposes ORM objects directly.

**Validation:** Run API integration tests with `TestClient` or async client. Create session/run through API; query run detail; decide approval; query dashboard.

## T21: Qualification Scenario Runner

**Files:** `src/agentgov/testing/qualification_scenario.py`, `replay.py`, `fixtures.py`, `config/examples/qualification.yaml`

**Dependencies:** T16, T17, T18, T19

**Steps:**
1. Implement deterministic multi-agent scenario: Coordinator, Evidence, Execution, Policy Auditor, Reviewer.
2. Simulate repo governance analysis with real repo read/search tools and scripted model outputs.
3. Generate final report artifact in ObjectStore.
4. Generate machine-readable qualification result.
5. Implement replay verification for key event order.

**Validation:** Run `python -m agentgov.cli qualification run --config config/examples/qualification.yaml`; expect completed parent run, child runs, report artifact, experience candidate, and passing qualification checks.

## T22: Failure Scenario Test Harness

**Files:** `src/agentgov/testing/scripted_model.py`, `scripted_tools.py`, `fault_injection.py`, `tests/integration/test_failures.py`

**Dependencies:** T13, T14, T15, T16

**Steps:**
1. Add model failure, tool failure, sandbox timeout, budget exceeded, approval rejected, lease expired scenarios.
2. Ensure every failure path records RunStep and final status.
3. Ensure budget reservations release on failed model call.

**Validation:** Run `pytest tests/integration/test_failures.py`; expect all failure cases pass and produce queryable audit evidence.

## T23: Frontend Project And API Client

**Files:** `web/package.json`, `web/src/api.ts`, `web/src/App.tsx`

**Dependencies:** T20

**Steps:**
1. Create React + TypeScript + Vite app.
2. Add TanStack Query, table virtualization, chart/topology libraries.
3. Implement API client for dashboard, agents, runs, approvals, audit logs.
4. Create base navigation layout.

**Validation:** Run `npm install` and `npm run build` in `web`; expect successful build. API client type checks.

## T24: Frontend Overview And Agent Directory

**Files:** `web/src/pages/Dashboard.tsx`, `AgentDirectory.tsx`, `web/src/components/MetricCards.tsx`, `AgentCard.tsx`, `AgentTable.tsx`

**Dependencies:** T19, T23

**Steps:**
1. Implement overview metric cards and recent critical events.
2. Implement Agent search/filter/table/card switch.
3. Show status, health score, active runs, budget, last event.

**Validation:** Run frontend against seeded backend; expect dashboard shows non-empty metrics and Agent directory can filter by status.

## T25: Frontend Run Detail, Approval, Audit Log

**Files:** `web/src/pages/RunDetail.tsx`, `AuditLog.tsx`, `web/src/components/EventTimeline.tsx`, `CostPanel.tsx`, `PolicyPanel.tsx`, `ApprovalPanel.tsx`, `AuditTable.tsx`

**Dependencies:** T20, T23

**Steps:**
1. Implement Run event timeline with model/tool/sandbox/policy/approval events.
2. Implement cost ledger display.
3. Implement policy decisions and evidence refs display.
4. Implement approval approve/reject actions.
5. Implement audit log filters and expandable details.

**Validation:** Trigger HITL scenario; expect pending approval visible and actionable. After approve/reject, run detail updates. Audit filters return expected rows.

## T26: Frontend Topology, Task Scheduling, Security Center

**Files:** `web/src/pages/Topology.tsx`, `TaskScheduling.tsx`, `SecurityCenter.tsx`, `web/src/components/TopologyGraph.tsx`, `TaskQueue.tsx`

**Dependencies:** T19, T23

**Steps:**
1. Implement topology graph for parent-child runs, delegation edges, agent dependency edges.
2. Implement task queue view: queued/running/completed/failed, worker lease state.
3. Implement security view: roles, policy bindings, delegation grants, pending approvals.

**Validation:** Run qualification scenario; expect topology shows Coordinator and child agents, task scheduling shows parent/child runs, security center shows delegation grants.

## T27: End-To-End Local Runbook

**Files:** `README.md`, `tests/e2e/test_local_runbook.py`

**Dependencies:** T1-T26

**Steps:**
1. Document setup: install backend, initialize DB, run API, run worker, run frontend.
2. Document running qualification scenario.
3. Add e2e test that follows the runbook with scripted config.

**Validation:** On a clean checkout, follow README commands; expect API starts, worker starts, qualification scenario completes, frontend builds.

## T28: Acceptance Checklist Preparation

**Files:** `checklist.md`

**Dependencies:** T1-T27

**Steps:**
1. Convert spec acceptance criteria into observable checklist items.
2. Include command-based verification for backend tests, frontend build, API smoke, qualification scenario, and failure scenarios.
3. Include manual UI checks for dashboard, run detail, approval, audit log, topology.

**Validation:** `checklist.md` contains every AC from `spec.md` and at least one verification method per item.

## Execution Order

```text
T1 -> T2 -> T3 -> T4 -> T5 -> T6 -> T7 -> T8 -> T9 -> T10
   -> T11 -> T12 -> T13 -> T14 -> T15 -> T16
   -> T17 -> T18 -> T19 -> T20 -> T21 -> T22
   -> T23 -> T24 -> T25 -> T26 -> T27 -> T28
```

## MVP Definition Of Done

The MVP is not complete until all of the following are true:

- A real OpenAI-compatible provider path exists and is used by `local.openai.yaml`.
- Scripted providers exist only under Test Harness and qualification configs.
- A run survives process restart because core state is persisted in SQLite.
- Budget reserve/settle/release produces queryable ledger rows.
- HITL approval can pause and resume a run.
- The multi-agent qualification scenario produces parent run, child runs, TeamBus messages, report artifact, evidence refs, and an experience candidate.
- Failure scenarios produce explicit final states and audit evidence.
- Frontend can inspect overview, agents, run detail, approvals, audit logs, topology, task queue, and security/delegation data.
