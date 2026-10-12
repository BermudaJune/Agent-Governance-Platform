# Agent Governance Platform Checklist

> 每一项都必须能通过运行命令、调用 API、查看 UI、检查数据库记录或读取生成物来验证。未通过的项不能算 MVP 完成。

## Implementation Completeness

- [ ] 项目能作为 Python 包启动，CLI 可用。
  Verification: run `python -m agentgov.cli --help`; expect commands for `config`, `db`, `api`, `worker`, and `qualification`.

- [ ] 配置系统能加载真实系统配置和测试 Harness 配置。
  Verification: run `python -m agentgov.cli config validate config/examples/local.openai.yaml` and `python -m agentgov.cli config validate config/examples/local.scripted.yaml`; expect both valid.

- [ ] 配置校验能发现错误引用和明文密钥。
  Verification: run config validation against an intentionally invalid config; expect missing provider/tool/team references and plain `api_key` fields to be rejected with clear error messages.

- [ ] 数据库初始化能创建核心治理表。
  Verification: run `python -m agentgov.cli db init --database sqlite+aiosqlite:///./data/test.db`; inspect tables and expect `sessions`, `runs`, `run_steps`, `model_calls`, `tool_calls`, `sandbox_actions`, `policy_decisions`, `approvals`, `budget_ledger`, `span_records`, `evidence_refs`, `agent_messages`, `collaboration_tasks`, `experience_candidates`, `run_queue`, and `run_leases`.

- [ ] Agent、Session、Run、RunStep 分层对象存在且职责不混淆。
  Verification: run unit tests for storage models and repositories; expect one Agent version can create multiple Sessions, one Session can create multiple Runs, and one Run can append multiple ordered RunSteps.

- [ ] Run 状态机只允许显式状态转移。
  Verification: run state machine unit tests; expect valid transitions such as `pending -> running -> completed` pass, invalid transitions raise controlled errors and create failure/audit evidence where applicable.

- [ ] EventStream 是 append-first，RunStep 在同一 Run 内单调递增。
  Verification: append three events to the same run; query by run and expect `seq = 1, 2, 3` with no overwrite behavior.

- [ ] ModelGateway 真实路径支持 OpenAI-compatible provider。
  Verification: with env key present, run OpenAI-compatible smoke test and expect a successful model call, usage parsing, `model_calls` row, `run_steps` event, `span_records` row, and budget ledger entries. Without env key, the smoke test must be skipped, not failed.

- [ ] ScriptedModelProvider 只用于 Test Harness 或 qualification config。
  Verification: inspect config validation and provider registry tests; expect production/default `local.openai.yaml` to use `openai` protocol and scripted providers to be accepted only in scripted/qualification configs.

- [ ] BudgetService 实现 preflight、reserve、settle、release。
  Verification: run budget unit tests; expect normal call writes reserve and settle entries, failed provider call writes release, budget exceeded writes deny/pause decision before provider call.

- [ ] PermissionService 支持 subject/action/resource 和 delegation chain。
  Verification: run permission tests; expect operator can create run, auditor can view audit but cannot approve, coordinator can delegate only to configured worker agents, denied delegation creates `PolicyDecision`.

- [ ] PolicyEngine 支持 allow、deny、require_approval、pause。
  Verification: run policy unit tests; expect tool access, sandbox boundary, budget, HITL, and audit-required policies produce persisted decisions.

- [ ] HITL 能创建审批、暂停运行、恢复或拒绝运行。
  Verification: trigger a write or high-risk action; expect run status `awaiting_approval`, an `approvals` row, `approval.requested` event, approve path resumes to `running/completed`, reject path ends as `rejected` with reason.

- [ ] ToolGateway 记录真实本地只读 repo 工具调用。
  Verification: call `repo_list`, `repo_search`, and `repo_read` through ToolGateway; expect `tool_calls` rows, trace spans, policy decisions, and run events.

- [ ] SandboxService 支持本地只读沙箱边界。
  Verification: run allowed `rg` command and expect success plus `sandbox_actions` event; run disallowed command or out-of-bound path and expect deny before execution plus policy decision.

- [ ] RunQueue 和 RunLease 是 DB-backed，不依赖纯内存。
  Verification: enqueue a run, claim it with worker A, restart worker process, recover or complete according to lease rules; expect `run_queue` and `run_leases` rows reflect lifecycle.

- [ ] TracePlane 能关联 Run、child Run、model/tool/sandbox/policy spans。
  Verification: create parent and child runs; query trace tree and expect shared trace context, parent-child relation, spans, evidence refs, and reasoning summaries.

- [ ] Multi-agent 协作使用 TeamBus 和 parent_run_id，而不是 Agent 互相直接函数调用。
  Verification: run collaboration tests; expect Coordinator parent run, Evidence/Execution/Policy Auditor/Reviewer child runs, `agent_messages` with `task.assigned` and `task.result`, and `collaboration_tasks` states.

- [ ] ExperienceCandidate 在 Run 完成后生成，但不会直接污染长期记忆。
  Verification: complete a run; expect pending/evaluating experience candidate with source run and evidence refs. Accept then commit; expect MemoryStore searchable. Reject or rollback; expect inactive/reverted state.

## Integration

- [ ] API 能创建 Session 并发起 Run。
  Verification: run API integration test using scripted config; call session create and run create endpoints; expect returned IDs, run status, persisted rows, and initial `run.started` event.

- [ ] RunService 执行路径贯穿 ModelGateway、ToolGateway、PolicyEngine、BudgetService、EventStream。
  Verification: run scripted single-agent scenario; expect events for run start, model call, policy decision, tool call, status change, run final, cost ledger, and spans.

- [ ] 审计事件、策略决策、审批记录和成本记录在服务重启后仍可查询。
  Verification: run scenario, stop process, start new process with same SQLite database, query run detail and audit endpoints; expect records remain available.

- [ ] 同一 Session 下并发写入不会破坏上下文顺序。
  Verification: run concurrency integration test with two context-writing runs for the same session; expect one obtains lock and the other waits/fails according to config, with explicit event/audit record.

- [ ] 失败路径能产生明确终态和审计证据。
  Verification: run `pytest tests/integration/test_failures.py`; expect model failure, tool failure, sandbox timeout, budget exceeded, approval rejected, and lease expired scenarios all pass and write queryable evidence.

- [ ] 大 payload、报告和快照能写入 ObjectStore。
  Verification: run qualification scenario; expect final report artifact exists in local object store and has an `EvidenceRef` or artifact reference in run detail.

- [ ] MemoryStore 的 MVP 搜索可用。
  Verification: commit an accepted experience; run memory search for a known phrase; expect returned MemoryItem includes source run and evidence refs.

- [ ] Dashboard backend 能聚合 overview、health、topology、audit query。
  Verification: seed or run qualification data; call dashboard endpoints and expect non-empty metrics, agent health snapshots, topology nodes/edges, and filtered audit rows.

- [ ] API 不直接暴露 ORM 对象。
  Verification: run API schema tests; expect responses are Pydantic/typed schemas without SQLAlchemy internal fields.

## Build And Test

- [ ] Backend unit tests pass.
  Verification: run `pytest tests/unit`; expect all tests pass.

- [ ] Backend integration tests pass with scripted config.
  Verification: run `pytest tests/integration`; expect all tests pass without real LLM credentials.

- [ ] End-to-end scripted runbook test passes.
  Verification: run `pytest tests/e2e/test_local_runbook.py`; expect DB init, API startup, worker startup, qualification run, and frontend build steps pass.

- [ ] Qualification scenario can run from CLI.
  Verification: run `python -m agentgov.cli qualification run --config config/examples/qualification.yaml`; expect completed parent run, child runs, report artifact, evidence refs, cost ledger, policy decisions, and experience candidate.

- [ ] Deterministic replay verifies key event order.
  Verification: run replay verification for qualification scenario twice; expect key state transitions and event types occur in the same order.

- [ ] Frontend installs and builds.
  Verification: run `npm install` and `npm run build` in `web`; expect successful build and type check.

- [ ] Frontend can connect to seeded backend.
  Verification: start API with scripted seed/qualification data, start frontend, open console pages; expect no blocking API errors in browser console.

## UI Acceptance

- [ ] Overview Dashboard shows system-level governance state.
  Verification: after seeded or qualification data exists, UI shows total agents, running/error/completed runs, pending approvals, cost, recent events, and critical alerts.

- [ ] Agent Directory supports card/table view and filtering.
  Verification: filter agents by status/type/team; expect Coordinator, Evidence, Execution, Policy Auditor, and Reviewer agents visible with health, active runs, budget, and last event.

- [ ] Run Detail shows audit timeline and linked details.
  Verification: open a completed run; expect timeline with model/tool/sandbox/policy/approval/status events, cost panel, policy panel, evidence refs, and experience candidate.

- [ ] Approval Panel can decide pending HITL actions.
  Verification: trigger HITL scenario; approve and reject separate runs from UI; expect run status and approval record update without manual DB editing.

- [ ] Audit Log supports useful filters.
  Verification: filter by run, agent, event type, policy id, approval status, and time range; expect matching rows and expandable payload summaries.

- [ ] Topology View shows parent-child and delegation edges.
  Verification: after qualification scenario, UI graph shows Coordinator linked to Evidence, Execution, Policy Auditor, and Reviewer, with edge details for delegation/message counts.

- [ ] Task Scheduling Center shows queue and lease state.
  Verification: while runs are queued/running/completed/failed, UI shows queue status, worker lease, parent-child relation, and final outcome.

- [ ] Security Center shows roles, policies, delegation grants, and pending approvals.
  Verification: open security view; expect role matrix, policy bindings, delegation grants, and approval queue populated from backend data.

## End-To-End Scenarios

- [ ] Scenario 1: scripted single-agent run completes without real LLM.
  Verification: create session and run using `local.scripted.yaml`; expect final status `completed`, events include model/tool/policy/status/final, and no external model key is required.

- [ ] Scenario 2: budget exceeded blocks before provider call.
  Verification: configure low budget and run model task; expect run `awaiting_budget` or `failed` according to policy, budget deny ledger entry, policy decision, and no provider call record marked successful.

- [ ] Scenario 3: HITL approve resumes execution.
  Verification: trigger approval-required tool or sandbox action, approve it, and expect run continues to completion with `approval.requested`, `approval.decided`, and final events.

- [ ] Scenario 4: HITL reject creates explicit terminal state.
  Verification: trigger approval-required action, reject it with reason, and expect run status `rejected`, final event, approval reason, and no unauthorized tool execution.

- [ ] Scenario 5: sandbox denies unsafe execution.
  Verification: attempt disallowed command or write action in read-only sandbox; expect denial before execution, policy decision, sandbox action record, and visible audit log.

- [ ] Scenario 6: worker lease expiry is recoverable or explicitly failed.
  Verification: start a run, simulate worker heartbeat loss, wait for lease expiry, start another worker; expect reclaim or controlled failure with audit evidence.

- [ ] Scenario 7: multi-agent qualification task completes.
  Verification: run qualification CLI; expect parent Coordinator run, four child runs, TeamBus messages, policy decisions, sandbox actions, budget ledger, report artifact, reviewer conclusion, and experience candidate.

- [ ] Scenario 8: qualification report is traceable.
  Verification: inspect generated report; every key conclusion links to at least one event, tool result, sandbox action, policy decision, or evidence ref.

- [ ] Scenario 9: same scripted qualification scenario is reproducible.
  Verification: run qualification twice with same scripted config; expect key event types, state transitions, parent-child structure, and final checks to match.

- [ ] Scenario 10: real OpenAI-compatible smoke path works when credentials exist.
  Verification: set configured API key env var and run smoke command; expect one successful model call through ModelGateway with usage/cost/audit records. If env var is absent, expect the test to skip cleanly.

## Acceptance Criteria Coverage

| Spec AC | Checklist Coverage |
|---|---|
| AC1 config loading and errors | configuration checks, invalid config validation |
| AC2 create session/run with audit and final result | API integration, single-agent scenario |
| AC3 structured events | EventStream, RunService, Run Detail |
| AC4 budget before model call | BudgetService, budget exceeded scenario |
| AC5 HITL pause/resume/reject | HITL completeness, approval scenarios |
| AC6 console agent cards and statuses | Overview, Agent Directory |
| AC7 run detail timeline/cost/calls/policies | Run Detail UI |
| AC8 no-real-LLM test mode | scripted single-agent and integration tests |
| AC9 leader-worker multi-agent audit | collaboration checks, qualification scenario |
| AC10 sandbox action audit | SandboxService, unsafe execution scenario |
| AC11 experience candidate | ExperienceCandidate checks |
| AC12 concurrent session writes | SessionLock concurrency test |
| AC13 persistence after restart | restart persistence integration |
| AC14 extensible policy/audit point | PolicyEngine plugin/rule tests and no-main-flow rewrite review |
| AC15 clear project structure and names | project skeleton, file organization review |
| AC16 full multi-agent qualification task | qualification CLI, traceable report, replay |

## Final MVP Gate

- [ ] All unit, integration, e2e, qualification, replay, and frontend build checks above pass.
- [ ] Real system path and Test Harness path both work and share the same governance chain.
- [ ] No MVP acceptance criterion is satisfied only by static UI or hardcoded demo data.
- [ ] Any skipped real-model test is skipped only because credentials are absent, with scripted coverage still passing.
- [ ] README local runbook can be followed on a clean checkout.
