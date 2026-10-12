# Realtime Multi-Agent Governance Plan

## Architecture Overview

本阶段在现有 Agent 治理平台上增加一条真实多 Agent 执行链路：

```text
Config/Registry
  -> Capability Analysis
  -> Team Matching
  -> Session Team Snapshot
  -> Background Worker Queue
  -> Agent Runtime Loop
  -> Tool/Skill Governance Gateway
  -> Event Store + SSE Stream
  -> Session Cockpit
```

核心变化：

- API 不再同步等待模型和工具执行；API 创建 Session/Run 后入队并快速返回。
- Worker 从队列取 Run 执行，并持续写入事件。
- 前端按 Session 订阅 SSE，实时展示状态、消息、工具调用、产物、审批和失败。
- Tool/Skill/Capability 成为可注册资源，Agent 通过能力绑定获得可治理的执行能力。
- Team 在执行前生成匹配报告，减少无效 Agent 参与和 token 浪费。
- 每次 Session 保存实际 Team 快照，历史复盘不受 Team 模板后续变更影响。

## Core Data Structures

### CapabilityDefinition

描述一个可注册能力单元，可以来自 Skill、Tool 或外部函数。

```python
class CapabilityDefinition:
    id: str
    name: str
    description: str
    category: str  # read/write/network/command/coordination/artifact/review
    input_schema: dict
    output_schema: dict
    risk_level: str  # low/medium/high
    required_tools: list[str]
    optional_tools: list[str]
    required_permissions: list[str]
    sandbox: str | None
    requires_approval: bool
    suitable_roles: list[str]
```

### SkillDefinition

描述 Agent 可以加载的技能说明，不直接绕过治理。

```python
class SkillDefinition:
    id: str
    name: str
    description: str
    prompt_body: str
    recommended_tools: list[str]
    output_artifacts: list[str]
    capability_ids: list[str]
    risk_level: str
```

### ToolDefinition

描述平台可执行工具。工具调用必须经过 Tool Gateway。

```python
class ToolDefinition:
    id: str
    name: str
    description: str
    category: str
    input_schema: dict
    output_schema: dict
    is_concurrency_safe: bool
    should_defer: bool
    risk_level: str
    sandbox: str | None
```

### TaskRequirement

从用户自然语言任务解析出的需求。

```python
class TaskRequirement:
    task_summary: str
    required_capabilities: list[str]
    required_roles: list[str]
    expected_artifacts: list[str]
    risk_hints: list[str]
    path_requirements: list[str]
    network_requirements: list[str]
```

### TeamMatchingReport

执行前能力匹配结果。

```python
class TeamMatchingReport:
    id: str
    session_id: str | None
    team_id: str | None
    score: float
    decision: str  # proceed/adjust/approval_required/block
    covered_capabilities: list[str]
    missing_capabilities: list[str]
    redundant_agents: list[str]
    suggested_agents: list[str]
    risk_items: list[dict]
    token_waste_warnings: list[str]
    checker: str  # rules/llm/rules+llm
    explanation: str
```

### TeamTemplate

可复用团队模板。

```python
class TeamTemplate:
    id: str
    name: str
    version: int
    leader_agent_id: str
    member_agent_ids: list[str]
    collaboration_strategy: str
    capability_ids: list[str]
    description: str
    status: str  # draft/active/archived
```

### SessionTeamSnapshot

某次 Session 实际使用的团队快照。

```python
class SessionTeamSnapshot:
    id: str
    session_id: str
    source_team_template_id: str | None
    leader_agent_id: str
    member_agent_ids: list[str]
    agent_capabilities: dict
    collaboration_strategy: str
    matching_report_id: str | None
    created_at: str
```

### RunQueueItem

后台执行队列项。

```python
class RunQueueItem:
    id: str
    run_id: str
    session_id: str
    status: str  # queued/leased/running/completed/failed/cancelled
    priority: int
    lease_owner: str | None
    available_at: str
    attempts: int
    last_error: str | None
```

### RealtimeEvent

SSE 输出事件，来自持久化 run_steps 或 agent_messages。

```python
class RealtimeEvent:
    id: str
    session_id: str
    run_id: str | None
    event_type: str
    actor_type: str
    actor_id: str
    status: str
    payload: dict
    created_at: str
```

### ArtifactRecord

产物记录。

```python
class ArtifactRecord:
    id: str
    session_id: str
    run_id: str
    created_by_agent_id: str
    artifact_type: str
    path: str
    summary: str
    metadata: dict
    created_at: str
```

## Module Design

### `agentgov.capabilities.registry`

**Responsibility:** 加载和查询 Tool、Skill、Capability 定义。

**Public Interface:**

```python
class CapabilityRegistry:
    def list_capabilities(self) -> list[CapabilityDefinition]: ...
    def get_capability(self, capability_id: str) -> CapabilityDefinition | None: ...
    def list_agent_capabilities(self, agent_id: str) -> list[CapabilityDefinition]: ...
```

**Dependencies:** config loader, storage repository.

### `agentgov.capabilities.requirements`

**Responsibility:** 从用户任务输入解析 TaskRequirement。

**Public Interface:**

```python
class RequirementAnalyzer:
    def analyze(self, task_input: str, *, use_llm: bool = False) -> TaskRequirement: ...
```

**Dependencies:** capability registry, optional model gateway.

### `agentgov.teams.matching`

**Responsibility:** 生成 TeamMatchingReport。

**Public Interface:**

```python
class TeamMatcher:
    def match_team(
        self,
        requirement: TaskRequirement,
        agent_ids: list[str],
        *,
        team_id: str | None = None,
        use_llm: bool = False,
    ) -> TeamMatchingReport: ...
```

**Dependencies:** capability registry, policy engine, optional model gateway.

### `agentgov.teams.snapshots`

**Responsibility:** 保存 Session Team Snapshot、Team Template 和 Team Run History。

**Public Interface:**

```python
class TeamSnapshotService:
    def create_snapshot(self, session_id: str, team: TeamTemplate | None, agent_ids: list[str], report_id: str | None) -> SessionTeamSnapshot: ...
    def save_template_from_session(self, session_id: str, name: str, description: str) -> TeamTemplate: ...
```

**Dependencies:** repository.

### `agentgov.scheduler.queue`

**Responsibility:** 入队、租约、重试、取消 Run。

**Public Interface:**

```python
class RunQueue:
    def enqueue(self, run_id: str, session_id: str, priority: int = 100) -> RunQueueItem: ...
    def lease_next(self, worker_id: str) -> RunQueueItem | None: ...
    def complete(self, item_id: str) -> None: ...
    def fail(self, item_id: str, error: str, retryable: bool) -> None: ...
    def cancel_session(self, session_id: str) -> int: ...
```

**Dependencies:** repository.

### `agentgov.scheduler.worker`

**Responsibility:** 后台执行队列中的 Run，并把执行过程写入事件流。

**Public Interface:**

```python
class RunWorker:
    def tick(self) -> int: ...
    def run_forever(self) -> None: ...
```

**Dependencies:** RunQueue, RunService, EventStream.

### `agentgov.event_stream.sse`

**Responsibility:** 按 Session 输出 SSE。

**Public Interface:**

```python
def session_event_stream(session_id: str, after_id: str | None = None) -> Iterator[str]: ...
```

**Dependencies:** repository, event stream.

### `agentgov.gateway.skill`

**Responsibility:** Skill 调用治理入口。Skill 只提供能力说明和调用上下文，具体执行仍通过 Tool Gateway 或 Model Gateway。

**Public Interface:**

```python
class SkillGateway:
    def load_skill(self, run_id: str, session_id: str, agent_id: str, skill_id: str) -> dict: ...
```

**Dependencies:** capability registry, event stream, policy engine.

### `agentgov.gateway.tool`

**Responsibility:** 继续作为所有工具执行入口，新增 ToolDefinition metadata、path policy、artifact registration。

**Public Interface Changes:**

```python
class ToolGateway:
    def call(self, run_id: str, session_id: str, agent_id: str, tool_name: str, args: dict) -> dict: ...
```

**Dependencies:** capability registry, policy engine, sandbox, artifact service.

### `agentgov.runtime.collaboration`

**Responsibility:** 执行真实多 Agent 协作协议。

**Public Interface:**

```python
class CollaborationRuntime:
    def create_plan(self, session_id: str, leader_run_id: str) -> dict: ...
    def assign_task(self, session_id: str, from_agent: str, to_agent: str, instruction: str) -> dict: ...
    def submit_result(self, session_id: str, run_id: str, result: dict) -> dict: ...
```

**Dependencies:** repository, event stream, run queue.

### `agentgov.api.routes_events`

**Responsibility:** SSE 订阅接口。

**Endpoints:**

```text
GET /events/sessions/{session_id}
```

### `agentgov.api.routes_teams`

**Responsibility:** Team 模板、匹配、保存复用。

**Endpoints:**

```text
POST /teams/match
POST /teams/templates
GET /teams/templates
GET /teams/templates/{team_id}
POST /teams/templates/from-session/{session_id}
GET /teams/history
```

### `agentgov.api.routes_tasks`

**Responsibility:** 创建 Session 时先执行能力分析、匹配、快照，再入队。

**Endpoint Changes:**

```text
POST /tasks/dispatch
POST /tasks/dispatch-team
POST /tasks/dispatch-ad-hoc-team
```

新增请求参数：

```python
execute_mode: "enqueue" | "manual" | "sync"
use_llm_matching: bool
force: bool
```

### `web/src/App.tsx`

**Responsibility:** 增加 Session 驾驶舱、Team Matching Report、实时事件订阅、Team 保存入口。

## Module Interactions

### Create Ad-Hoc Multi-Agent Session

```text
User selects agents and task
  -> API receives dispatch-ad-hoc-team
  -> RequirementAnalyzer analyzes task
  -> TeamMatcher evaluates selected agents
  -> if low score and not force: return report without enqueue
  -> create Session
  -> create SessionTeamSnapshot
  -> create leader Run and member Runs
  -> enqueue initial Runs or leave pending
  -> return Session + MatchingReport
  -> frontend opens Session Cockpit
  -> frontend subscribes SSE
```

### Worker Execution

```text
RunWorker leases RunQueueItem
  -> RunService moves Run to running
  -> AgentLoop streams model events
  -> model tool/function request emitted
  -> ToolGateway checks capability/policy/sandbox
  -> ToolGateway records tool call and artifact
  -> AgentLoop records output
  -> CollaborationRuntime records messages/results
  -> RunService marks Run completed/failed/paused
  -> RunQueue marks item completed/failed
  -> SSE emits events continuously
```

### Pause/Cancel

```text
User clicks pause/cancel
  -> API updates Run/Session status
  -> Queue cancels queued items
  -> EventStream records control action
  -> Worker checks state before finalizing returned calls
  -> SSE emits paused/cancelled event
```

### Save Team Template

```text
User opens completed Session
  -> Click save as Team Template
  -> TeamSnapshotService reads SessionTeamSnapshot and matching report
  -> creates TeamTemplate version 1
  -> future tasks can select this TeamTemplate
```

## File Organization

```text
src/agentgov/
├── capabilities/
│   ├── __init__.py
│   ├── models.py              - Capability/Skill/Tool/TaskRequirement data models
│   ├── registry.py            - capability and skill registry
│   └── requirements.py        - task requirement analysis
├── teams/
│   ├── __init__.py
│   ├── matching.py            - rule/LLM team matching
│   ├── snapshots.py           - team snapshots/templates/history
│   └── models.py              - team template and matching models
├── scheduler/
│   ├── queue.py               - extend current queue with run leasing/cancel/retry
│   └── worker.py              - background worker loop
├── event_stream/
│   ├── events.py              - event type constants
│   ├── stream.py              - append/query events
│   └── sse.py                 - session SSE stream
├── gateway/
│   ├── tool.py                - tool governance and artifact registration
│   └── skill.py               - skill governance gateway
├── runtime/
│   ├── agent_loop.py          - emit streaming model/tool events
│   ├── run_service.py         - enqueue/manual/sync execution modes
│   └── collaboration.py       - task assignment and result protocol
├── api/
│   ├── routes_events.py       - SSE endpoints
│   ├── routes_teams.py        - matching/templates/history endpoints
│   ├── routes_tasks.py        - dispatch with matching/snapshot/enqueue
│   └── routes_runs.py         - run controls and retry
└── storage/
    ├── db.py                  - schema migrations for queue/events/capabilities/teams/artifacts
    └── repositories.py        - repository helpers

web/src/
├── App.tsx                    - route wiring and pages
├── api.ts                     - SSE and team API helpers
└── styles.css                 - cockpit/matching/team UI

tests/
├── unit/
│   ├── test_capability_matching.py
│   ├── test_team_snapshots.py
│   └── test_run_queue.py
├── integration/
│   ├── test_worker_sse_flow.py
│   └── test_skill_tool_governance.py
└── e2e/
    └── test_custom_team_task.py
```

## Technical Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Execution mode | Add `manual`, `enqueue`, `sync` | Keeps current flows working while enabling real background execution. |
| Queue backend | Start with DB-backed queue, keep Redis boundary | Local dev works now; Redis can replace queue later. |
| Realtime transport | SSE | Simpler than WebSocket for append-only event streams and fits audit timeline. |
| Matching | Rules first, optional LLM | Rules save token; LLM helps with natural language capability descriptions. |
| Team persistence | Template + Session Snapshot + History | Template supports reuse; snapshot preserves historical truth; history supports optimization. |
| Skill execution | Skill is guidance, Tool is execution | Prevents Skill from bypassing policy/sandbox governance. |
| Tool schema | Pydantic/JSON Schema style | Compatible with OpenAI function calling, MCP-style tools, and validation. |
| Artifacts | Explicit `ArtifactRecord` | Files become traceable outputs rather than invisible disk side effects. |
| Pause semantics | Cooperative | Remote LLM calls cannot always be killed; platform records pause/cancel and prevents stale completion from silently winning. |
| Test strategy | Scripted model + fake tools + DB queue | Verifies governance without spending LLM tokens. |

