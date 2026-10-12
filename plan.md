# Agent Governance Platform Plan

## Architecture Overview

MVP 采用 Python-first 单仓结构：后端负责 Agent 治理主链路，前端实现可用的治理控制台。设计重点不是做花哨 UI，而是把 Agent、Session、Run、Event、Policy、Approval、Sandbox、Memory 这些治理对象和它们的可视化闭环固定下来。

核心分层：

```text
Control Plane
  AgentSpec / TeamSpec / SessionRecord / ConfigRegistry

Runtime Plane
  RunService / AgentLoop / CollaborationStrategy / EventStream / RunQueue

Governance Plane
  PolicyEngine / PermissionService / BudgetService / ApprovalService / AuditService

Gateway Plane
  ModelGateway / ToolGateway / SandboxRuntime

Memory Plane
  MemoryStore / ExperienceService / AgentVersion

Infrastructure Plane
  RelationalStore / EventBus / ObjectStore / VectorStore / RateLimiter

Trace Plane
  TraceContext / SpanRecord / ReasoningTrace / EvidenceRef

Presentation Plane
  FastAPI routes / Governance Console UI
```

一次运行的主链路：

```text
Create Session
  -> Create RunRecord
  -> RunService starts AgentLoop
  -> PolicyEngine pre-check
  -> ModelGateway call
  -> ToolGateway or SandboxRuntime action
  -> PolicyEngine may require Approval
  -> EventStream append RunStep
  -> BudgetService reserves and settles cost
  -> RunService finalizes RunRecord
  -> ExperienceService creates ExperienceCandidate
```

多 Agent 基准任务链路：

```text
Coordinator Run
  -> LeaderWorkerStrategy creates child runs
  -> Evidence Agent reads/searches files through ToolGateway
  -> Execution Agent runs read-only commands through SandboxRuntime
  -> Policy Auditor records PolicyDecision events
  -> Reviewer validates evidence traceability
  -> Coordinator merges report
  -> ExperienceService proposes experience candidates
```

## MVP Completeness Bar

这里的 MVP 不是“只搭接口壳子”。MVP 可以在外部基础设施上简化，但核心治理链路必须真实可用、可运行、可查询、可复现。

MVP 分成两条线，不能混用：

```text
System MVP: 平台真实能力，默认运行路径，必须可用于真实 Agent 治理。
Test Harness: 测试与演示环境，用 scripted model/tool、故障注入、脚本化任务验证系统。
```

测试环境可以模拟 LLM 和工具，但系统主路径不能依赖 simulated/scripted provider 才能跑通。

### Must Be Real In MVP

以下能力必须实现为可工作的版本，不能只有空接口：

- Config loading: 能读取 YAML，注册 provider、agent、team、policy、sandbox、budget，并报告配置错误。
- Database persistence: `SessionRecord / RunRecord / RunStep / PolicyDecision / Approval / BudgetLedgerEntry / ExperienceCandidate` 必须真实落库。
- Event stream: `RunStep` 必须按序追加，支持 run detail 查询和 SSE/轮询读取。
- Run state machine: `pending/running/awaiting_approval/completed/failed/rejected/cancelled` 必须真实流转。
- Model gateway: 必须实现 `OpenAICompatibleProvider` 作为系统主路径；`ScriptedModelProvider` 只属于 Test Harness。
- Budget governance: 至少实现 global、team、agent、per-run、per-model 预算检查、预留、结算、释放和 ledger。
- Permission governance: 至少实现 role-based permission、agent delegation、tool/sandbox action permission check。
- HITL: 工具或沙箱动作触发审批后，Run 必须进入等待状态；审批通过可恢复；拒绝进入终态。
- Tool gateway: 必须实现 repo search/read tool 和 local command tool wrapper；scripted tool 只属于 Test Harness。
- Sandbox: 必须实现本地只读沙箱，支持 allowlist commands、working directory boundary、timeout、环境变量过滤、输出截断和动作审计。
- Multi-agent: `Coordinator -> Evidence -> Execution -> Policy Auditor -> Reviewer` 基准任务必须能跑通，且每个子 Agent 有独立 child run。
- TeamBus: Agent 协作消息必须真实记录，至少支持 `task.assigned/task.result/review.completed`。
- Trace: `TraceContext / SpanRecord / EvidenceRef / ReasoningTrace` 必须写入并能在 Run Detail 中查询。
- Experience: Run 完成后必须生成至少一个经验候选，记录来源 run、来源 evidence、状态和置信度。
- Console: 至少实现 Overview Dashboard、Agent Directory、Run Detail、Approval Panel、Audit Log 的可用版本。
- Audit query: 必须支持按 run、agent、event_type、policy_id、approval_status、time range 查询。
- Report artifact: 多 Agent 基准任务必须生成可下载/可查看报告，并把报告存入 ObjectStore。
- Failure handling: 必须能覆盖模型失败、工具失败、沙箱超时、预算不足、审批拒绝、worker lease 过期。

### Simplified But Not Fake

以下能力 MVP 可以使用轻量实现，但必须有真实行为：

- Relational DB: 默认 SQLite，但所有 repository 通过 `RelationalStore`，后续可换 PostgreSQL。
- Event bus: DB 是事实源；内存 event bus 只负责本进程实时通知，不能作为唯一存储。
- RunQueue: 使用 DB-backed queue 和 lease，不使用纯内存队列作为主实现。
- Object store: 默认本地文件系统，用于报告、快照、大 payload 外溢。
- Vector store: MVP 先用 SQLite FTS/关键词检索承载长期记忆检索，不使用只能测试的空向量假实现作为主路径。
- Frontend topology: MVP 可先展示基础节点边，不要求复杂热力图，但必须能看 parent-child run 和 agent dependency。
- Security Center: MVP 可先展示角色、策略绑定和委托关系，不要求完整企业 IAM。

### Test Harness Required In MVP

测试环境必须单独存在，不能混在系统主路径里。它用于省算力、复现异常、验证治理链路。

必须提供：

- Scripted model provider: 根据脚本返回稳定的模型响应、工具意图、token usage 和错误。
- Scripted tools: 模拟 repo_search、repo_read、危险写入请求、工具失败和慢调用。
- Sandbox fault injection: 模拟 timeout、permission denied、large output、disallowed command。
- Budget scenarios: 正常预算、预算不足、预留后失败释放、实际成本超过预估。
- HITL scenarios: 审批通过、审批拒绝、审批超时。
- Multi-agent qualification runner: 一条命令运行基准任务并生成验收报告。
- Deterministic replay: 能用固定脚本重复运行同一场景，关键事件顺序一致。

测试环境可以模拟 LLM，但必须经过真实 `RunService / PolicyEngine / BudgetService / EventStream / ApprovalService / SandboxService`。

### Explicitly Later

以下能力可以作为后续增强，不阻塞 MVP 合格：

- Redis Streams 多副本事件总线。
- Redis 分布式限流和分布式锁。
- MinIO/S3 生产对象存储。
- Qdrant/Milvus 真实向量库。
- Docker/Kubernetes 强隔离沙箱。
- 完整 OPA/Cedar 策略语言。
- 高级拓扑热力图、智能告警聚合、复杂批量运维操作。

## Core Data Structures

### AgentSpec

Agent 的能力定义，不承载一次运行状态。

```python
class AgentSpec:
    id: str
    name: str
    description: str | None
    provider: str
    model: str
    tools: list[str]
    sandbox: str | None
    memory_profile: str | None
    policies: list[str]
    system_prompt: str
    metadata: dict[str, Any]
```

### AgentVersion

Agent 成长和回滚边界。AgentSpec 可以演进，但每次运行绑定具体版本。

```python
class AgentVersion:
    id: UUID
    agent_id: str
    version: int
    spec_snapshot: dict[str, Any]
    memory_version: int
    created_at: datetime
    reason: str | None
```

### TeamSpec

多 Agent 协作定义。

```python
class TeamSpec:
    id: str
    name: str
    leader: str
    members: list[str]
    collaboration_strategy: str
    policies: list[str]
```

### SessionRecord

长期上下文容器。一个 Session 可包含多个 Run，也可包含多个 Agent 的协作。

```python
class SessionRecord:
    id: UUID
    title: str
    owner_id: str
    root_agent_id: str | None
    team_id: str | None
    status: SessionStatus
    context_summary: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
```

`SessionStatus`：

```text
idle
running
awaiting_approval
awaiting_external_result
failed
closed
```

### RunRecord

一次可审计、可计费、可恢复的执行实例。

```python
class RunRecord:
    id: UUID
    session_id: UUID
    parent_run_id: UUID | None
    agent_id: str
    agent_version_id: UUID
    run_type: RunType
    status: RunStatus
    input_summary: str
    output_summary: str | None
    error: str | None
    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    started_at: datetime | None
    completed_at: datetime | None
    metadata: dict[str, Any]
```

`RunStatus`：

```text
pending
running
awaiting_approval
awaiting_budget
completed
failed
rejected
cancelled
timeout
```

### RunStep

运行事实明细。对应 agent-platform 的 `RunStep`，也承担 OpenHands `EventStream` 的事实流角色。

```python
class RunStep:
    id: UUID
    run_id: UUID
    session_id: UUID
    parent_step_id: UUID | None
    seq: int
    event_type: EventType
    actor_type: ActorType
    actor_id: str
    status: StepStatus
    payload: dict[str, Any]
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None
    created_at: datetime
```

`EventType`：

```text
run.started
run.status_changed
model.call.started
model.call.finished
model.call.failed
tool.call.started
tool.call.finished
tool.call.failed
sandbox.action.started
sandbox.action.finished
policy.decision
approval.requested
approval.decided
collaboration.delegated
collaboration.result
memory.experience_candidate_created
run.final
```

### ModelCallRecord

模型调用专用明细，方便成本、供应商、失败分析。

```python
class ModelCallRecord:
    id: UUID
    run_id: UUID
    step_id: UUID
    provider: str
    model: str
    request_summary: str
    response_summary: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal
    actual_cost_usd: Decimal
    status: CallStatus
    error: str | None
    created_at: datetime
```

### ToolCallRecord

工具调用专用明细。

```python
class ToolCallRecord:
    id: UUID
    run_id: UUID
    step_id: UUID
    tool_name: str
    caller_agent_id: str
    args_summary: dict[str, Any]
    result_summary: dict[str, Any] | None
    status: CallStatus
    approval_id: UUID | None
    duration_ms: int | None
    error: str | None
```

### SandboxActionRecord

沙箱动作专用明细。

```python
class SandboxActionRecord:
    id: UUID
    run_id: UUID
    step_id: UUID
    sandbox_id: str
    action_type: str
    command_summary: str | None
    filesystem_policy: str
    network_policy: str
    status: CallStatus
    output_summary: str | None
    error: str | None
    duration_ms: int | None
```

### PolicyDecision

所有治理判断的证据对象。

```python
class PolicyDecision:
    id: UUID
    run_id: UUID
    step_id: UUID | None
    policy_id: str
    policy_type: PolicyType
    subject: str
    action: str
    resource: str
    decision: Decision
    reason: str
    metadata: dict[str, Any]
    created_at: datetime
```

`Decision`：

```text
allow
deny
require_approval
pause
```

### Approval

人工审批记录。

```python
class Approval:
    id: UUID
    run_id: UUID
    step_id: UUID
    requested_by: str
    approver_id: str | None
    status: ApprovalStatus
    action_summary: dict[str, Any]
    reason: str | None
    decided_at: datetime | None
    created_at: datetime
```

`ApprovalStatus`：

```text
pending
approved
rejected
expired
cancelled
```

### BudgetLedgerEntry

预算预估、预留、结算和退款记录。预算逻辑参考 LiteLLM：检查不是单一余额字段，而是按 key、user、team、project、agent、provider、model、run 等多个 scope 分层判断；调用前预估和预留，调用后按实际 usage 结算，失败或拒绝时释放预留。

```python
class BudgetLedgerEntry:
    id: UUID
    run_id: UUID
    step_id: UUID | None
    scope_type: BudgetScope
    scope_id: str
    entry_type: BudgetEntryType
    amount_usd: Decimal
    estimated_input_tokens: int | None
    estimated_output_tokens: int | None
    actual_input_tokens: int | None
    actual_output_tokens: int | None
    provider: str | None
    model: str | None
    reason: str
    created_at: datetime
```

`BudgetScope`：

```text
api_key
user
team
project
agent
session
run
provider
model
global
```

`BudgetEntryType`：

```text
estimate
reserve
settle
release
refund
adjustment
deny
```

### BudgetPolicySnapshot

运行时携带的预算快照，避免每次策略判断都直接查多张表，也保证审计可复现。

```python
class BudgetPolicySnapshot:
    id: UUID
    run_id: UUID
    api_key_id: str | None
    user_id: str | None
    team_id: str | None
    project_id: str | None
    agent_id: str | None
    max_budget_usd: Decimal | None
    current_spend_usd: Decimal
    reserved_spend_usd: Decimal
    model_max_budget: dict[str, Decimal]
    tpm_limit: int | None
    rpm_limit: int | None
    reset_at: datetime | None
    created_at: datetime
```

### AgentHealthSnapshot

前端治理控制台的核心聚合对象，用于展示几十到上百个 Agent 的系统健康状态。

```python
class AgentHealthSnapshot:
    agent_id: str
    version: str
    status: AgentRuntimeStatus
    health_score: int
    active_runs: int
    queued_runs: int
    success_rate: float
    avg_latency_ms: int
    error_count: int
    budget_used_usd: Decimal
    budget_limit_usd: Decimal | None
    last_event_type: str | None
    last_event_at: datetime | None
```

### AgentDependencyEdge

拓扑关系视图的数据基础。

```python
class AgentDependencyEdge:
    source_agent_id: str
    target_agent_id: str
    relation_type: str
    call_count: int
    avg_latency_ms: int
    failure_rate: float
    last_call_at: datetime | None
```

### IdentityContext

权限与审计的身份上下文。用于回答“谁在代表谁操作什么资源”。

```python
class IdentityContext:
    user_id: str | None
    api_key_id: str | None
    agent_id: str | None
    team_id: str | None
    session_id: UUID | None
    run_id: UUID | None
    roles: list[str]
    delegated_by: str | None
    delegation_chain: list[str]
    metadata: dict[str, Any]
```

### ResourceRef

权限系统的资源引用。所有权限判断都转换成 `subject/action/resource`。

```python
class ResourceRef:
    resource_type: str
    resource_id: str
    owner_id: str | None
    team_id: str | None
    environment: str | None
    labels: dict[str, str]
```

### PermissionCheck

权限判断请求。

```python
class PermissionCheck:
    identity: IdentityContext
    action: str
    resource: ResourceRef
    risk_level: str
    attributes: dict[str, Any]
```

### DelegationGrant

多 Agent 委托授权。用于追踪 `user -> coordinator -> worker -> tool` 的委托链。

```python
class DelegationGrant:
    id: UUID
    parent_run_id: UUID
    grantee_agent_id: str
    granted_by: str
    allowed_actions: list[str]
    allowed_resources: list[ResourceRef]
    expires_at: datetime | None
    status: str
    created_at: datetime
```

### TraceContext

黑箱外部可观测的统一追踪上下文。

```python
class TraceContext:
    trace_id: UUID
    session_id: UUID
    run_id: UUID
    parent_run_id: UUID | None
    step_id: UUID | None
    span_id: UUID | None
    parent_span_id: UUID | None
    correlation_id: str | None
```

### SpanRecord

一次模型调用、工具调用、沙箱动作或策略判断的局部 span。

```python
class SpanRecord:
    id: UUID
    trace_id: UUID
    run_id: UUID
    parent_span_id: UUID | None
    span_type: str
    name: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    attributes: dict[str, Any]
```

### EvidenceRef

结论引用的证据。用于让报告、复核和经验候选可以追溯。

```python
class EvidenceRef:
    ref_type: str
    ref_id: str
    run_id: UUID
    step_id: UUID | None
    path: str | None
    line_start: int | None
    line_end: int | None
    summary: str
```

### ReasoningTrace

可审计推理摘要。它不是模型完整 chain-of-thought，而是外部可验证的决策说明。

```python
class ReasoningTrace:
    id: UUID
    run_id: UUID
    step_id: UUID
    agent_id: str
    decision_summary: str
    evidence_refs: list[EvidenceRef]
    alternatives_considered: list[str]
    confidence: float
    risk_flags: list[str]
    created_at: datetime
```

### AgentMessage

多 Agent 协作消息。Agent 之间不直接互调函数，而是通过 TeamBus 传递可审计消息。

```python
class AgentMessage:
    id: UUID
    trace_id: UUID
    session_id: UUID
    parent_run_id: UUID | None
    source_agent_id: str
    target_agent_id: str
    message_type: str
    payload: dict[str, Any]
    status: str
    created_at: datetime
```

常用 `message_type`：

```text
task.assigned
task.progress
task.result
task.failed
review.requested
review.completed
handoff.requested
```

### CollaborationTask

协作任务状态。

```python
class CollaborationTask:
    id: UUID
    parent_run_id: UUID
    assigned_agent_id: str
    task_type: str
    instruction: str
    status: str
    result_summary: str | None
    created_at: datetime
    completed_at: datetime | None
```

`CollaborationTask.status`：

```text
planned
dispatched
running
waiting
completed
failed
cancelled
```

### RunQueueItem

运行调度队列项。

```python
class RunQueueItem:
    id: UUID
    run_id: UUID
    session_id: UUID
    priority: int
    status: str
    available_at: datetime
    attempts: int
    created_at: datetime
```

### RunLease

Worker 执行租约。避免多副本重复执行同一个 Run。

```python
class RunLease:
    id: UUID
    run_id: UUID
    worker_id: str
    lease_until: datetime
    heartbeat_at: datetime
    status: str
```

### ExperienceCandidate

运行结束后的经验候选，不直接污染长期记忆。

```python
class ExperienceCandidate:
    id: UUID
    source_run_id: UUID
    source_step_ids: list[UUID]
    agent_id: str
    candidate_type: ExperienceType
    content: str
    confidence: float
    status: ExperienceStatus
    evaluator: str
    created_at: datetime
```

`ExperienceStatus`：

```text
pending_review
accepted
rejected
committed
rolled_back
```

## Core Interfaces

### ModelProvider

```python
class ModelProvider(Protocol):
    async def estimate(self, request: ModelRequest) -> CostEstimate: ...
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
```

默认实现：

- `OpenAICompatibleProvider`: 兼容 OpenAI 协议的系统主路径 provider。
- `ScriptedModelProvider`: Test Harness 使用，不作为系统默认 provider。

### ToolProvider

```python
class ToolProvider(Protocol):
    async def list_tools(self) -> list[ToolSpec]: ...
    async def call(self, request: ToolCallRequest) -> ToolCallResult: ...
```

默认实现：

- `LocalRepoToolProvider`: repo search/read/list 等真实本地只读工具。
- `LocalCommandToolProvider`: 通过 SandboxRuntime 执行 allowlist command。
- `MCPToolProvider`
- `ScriptedToolProvider`: Test Harness 使用，不作为系统默认工具。

### SandboxRuntime

```python
class SandboxRuntime(Protocol):
    async def prepare(self, context: SandboxContext) -> SandboxHandle: ...
    async def execute(self, action: SandboxAction) -> SandboxResult: ...
    async def close(self, handle: SandboxHandle) -> None: ...
```

默认实现：

- `LocalReadOnlySandboxRuntime`: MVP 只读命令沙箱。
- `DockerSandboxRuntime`: 预留容器隔离后端。
- `FaultInjectionSandboxRuntime`: Test Harness 使用，用于模拟超时、拒绝和错误。

### PolicyRule

```python
class PolicyRule(Protocol):
    async def evaluate(self, context: PolicyContext) -> PolicyDecisionResult: ...
```

内置规则：

- `IdentityPolicy`
- `BudgetPolicy`
- `ToolAccessPolicy`
- `HITLPolicy`
- `SandboxPolicy`
- `AuditRequiredPolicy`

### CollaborationStrategy

```python
class CollaborationStrategy(Protocol):
    async def plan(self, request: CollaborationRequest) -> CollaborationPlan: ...
    async def dispatch(self, plan: CollaborationPlan) -> CollaborationResult: ...
```

默认实现：

- `SingleAgentStrategy`
- `LeaderWorkerStrategy`

### AuditSink

```python
class AuditSink(Protocol):
    async def append(self, event: RunStepCreate) -> RunStep: ...
```

默认实现：

- `DatabaseAuditSink`
- `InMemoryAuditSink` for tests

## Module Design

### `agentgov.config`

**Responsibility:** 加载 YAML 配置，校验 provider、mcp server、agent、team、policy、sandbox 定义。

**Public Interface:**

```python
load_config(path: Path) -> PlatformConfig
validate_config(config: PlatformConfig) -> ConfigValidationResult
```

**Dependencies:** 无业务依赖，只依赖 schema。

### `agentgov.control_plane`

**Responsibility:** 管理 AgentSpec、AgentVersion、TeamSpec、SessionRecord。

**Public Interface:**

```python
AgentRegistry.get(agent_id: str) -> AgentSpec
TeamRegistry.get(team_id: str) -> TeamSpec
SessionService.create(...) -> SessionRecord
SessionService.get_status(session_id: UUID) -> SessionStatus
SessionLock.acquire(session_id: UUID) -> AsyncContextManager
```

**Dependencies:** storage、config。

### `agentgov.runtime`

**Responsibility:** 执行一次 Run，维护状态机，协调模型、工具、策略、审批、事件和经验生成。

**Public Interface:**

```python
RunService.create_run(...) -> RunRecord
RunService.execute(run_id: UUID) -> AsyncIterator[RunStep]
RunService.resume_run(run_id: UUID, approval_id: UUID) -> AsyncIterator[RunStep]
RunService.get_trace(run_id: UUID) -> list[RunStep]
```

**Dependencies:** control_plane、event_stream、policy、budget、gateway、approval、experience。

### `agentgov.runtime.agent_loop`

**Responsibility:** Agent 推理循环。它只负责“根据上下文产生下一步意图”，不直接执行工具或命令。

**Public Interface:**

```python
AgentLoop.events(run: RunRecord) -> AsyncIterator[AgentEvent]
```

**Dependencies:** ModelGateway、MemoryContextBuilder。

### `agentgov.event_stream`

**Responsibility:** 追加 RunStep，生成可查询事件时间线，支持 SSE 和重放。

**Public Interface:**

```python
EventStream.append(run_id: UUID, event: EventCreate) -> RunStep
EventStream.list(run_id: UUID) -> list[RunStep]
EventStream.stream(run_id: UUID) -> AsyncIterator[RunStep]
```

**Dependencies:** storage。

### `agentgov.policy`

**Responsibility:** 策略横切层。所有模型调用、工具调用、沙箱动作、记忆写入前后都经过 PolicyEngine。

**Public Interface:**

```python
PolicyEngine.evaluate(context: PolicyContext) -> list[PolicyDecisionResult]
PolicyEngine.enforce(context: PolicyContext) -> EnforcementResult
```

**Dependencies:** budget、approval、storage。

### `agentgov.permission`

**Responsibility:** 权限主体模型和委托链治理。把所有操作统一转成 `subject/action/resource` 判断，并记录委托关系。

**Public Interface:**

```python
PermissionService.check(check: PermissionCheck) -> PermissionDecision
PermissionService.create_delegation(parent_run_id: UUID, grantee_agent_id: str, scope: DelegationScope) -> DelegationGrant
PermissionService.validate_delegation(identity: IdentityContext, action: str, resource: ResourceRef) -> PermissionDecision
```

**Dependencies:** policy、storage、event_stream。

权限判断顺序：

```text
build IdentityContext
  -> resolve ResourceRef
  -> check direct role permissions
  -> check delegation chain
  -> check ABAC attributes
  -> append PolicyDecision
```

### `agentgov.budget`

**Responsibility:** 预算预估、预留、结算、退款、成本汇总。设计参考 LiteLLM 的治理方式：一个请求进入模型网关前，先把身份上下文转换成预算主体集合，然后同时检查 key/user/team/project/agent/model/global 等预算；成功后写 spend ledger，失败或中断也写可追踪记录。

**Public Interface:**

```python
BudgetService.preflight(run_id: UUID, estimate: CostEstimate) -> BudgetDecision
BudgetService.reserve(run_id: UUID, amount: Decimal) -> BudgetReservation
BudgetService.settle(run_id: UUID, actual: CostUsage) -> BudgetSettlement
BudgetService.summary(run_id: UUID) -> CostSummary
BudgetService.release(reservation_id: UUID, reason: str) -> BudgetRelease
BudgetService.snapshot(context: BudgetContext) -> BudgetPolicySnapshot
```

**Dependencies:** storage、provider pricing。

预算检查顺序：

```text
request context
  -> resolve budget subjects: key/user/team/project/agent/provider/model/global
  -> read cached BudgetPolicySnapshot when valid
  -> estimate max possible cost
  -> reject if any hard budget exceeded
  -> reserve estimated cost
  -> model call
  -> settle actual cost
  -> release unused reservation
  -> append BudgetLedgerEntry and PolicyDecision
```

MVP 先实现：

- global budget
- agent budget
- team budget
- per-run budget
- per-model price table
- scripted token usage settlement in Test Harness; real provider usage settlement in System MVP

预留扩展：

- API key budget
- user/project/end-user budget
- TPM/RPM 限流
- Redis 原子计数器
- provider/model fallback budget check

### `agentgov.approval`

**Responsibility:** 创建审批、记录审批决定、触发恢复。

**Public Interface:**

```python
ApprovalService.request(run_id: UUID, step_id: UUID, action: dict) -> Approval
ApprovalService.decide(approval_id: UUID, approver_id: str, decision: ApprovalDecision) -> Approval
```

**Dependencies:** storage、event_stream、runtime。

### `agentgov.gateway.model`

**Responsibility:** 模型网关。系统主路径使用 OpenAI-compatible provider；测试环境可切换 scripted provider。所有模型调用都必须记录事件和成本。

**Public Interface:**

```python
ModelGateway.complete(run_id: UUID, request: ModelRequest) -> ModelResponse
```

**Dependencies:** policy、budget、event_stream、providers。

### `agentgov.gateway.tool`

**Responsibility:** 工具网关。系统主路径使用本地 repo 工具、sandbox command wrapper 和 MCP 工具；测试环境可切换 scripted tools。所有工具调用都必须产生审计事件。

**Public Interface:**

```python
ToolGateway.call(run_id: UUID, request: ToolCallRequest) -> ToolCallResult
```

**Dependencies:** policy、approval、event_stream、tool providers。

### `agentgov.sandbox`

**Responsibility:** 手脑分离的执行边界。Agent 只能提交动作意图，具体执行由 SandboxRuntime 完成。

**Public Interface:**

```python
SandboxService.execute(run_id: UUID, action: SandboxAction) -> SandboxResult
```

**Dependencies:** policy、event_stream、runtime implementations。

### `agentgov.collaboration`

**Responsibility:** 多 Agent 协作。MVP 支持 leader-worker。

**Public Interface:**

```python
CollaborationService.delegate(parent_run_id: UUID, target_agent_id: str, task: str) -> RunRecord
CollaborationService.collect(parent_run_id: UUID) -> CollaborationResult
```

**Dependencies:** runtime、event_stream、control_plane。

### `agentgov.collaboration.team_bus`

**Responsibility:** 多 Agent 消息总线。Agent 之间不直接互调，所有任务分配、进度、结果和复核请求都通过可审计消息传递。

**Public Interface:**

```python
TeamBus.publish(message: AgentMessage) -> AgentMessage
TeamBus.list_messages(trace_id: UUID) -> list[AgentMessage]
TeamBus.subscribe(session_id: UUID) -> AsyncIterator[AgentMessage]
```

**Dependencies:** event_stream、infrastructure.event_bus、storage。

### `agentgov.scheduler`

**Responsibility:** Run 调度、队列、Worker 租约和崩溃恢复。MVP 使用 DB-backed queue 和 lease，保证进程重启后任务状态仍可恢复；后续可替换为 Redis Streams 或专用任务队列。

**Public Interface:**

```python
RunQueue.enqueue(run_id: UUID, priority: int = 0) -> RunQueueItem
RunQueue.claim(worker_id: str) -> RunLease | None
RunQueue.heartbeat(lease_id: UUID) -> RunLease
RunQueue.complete(lease_id: UUID) -> None
RunQueue.fail(lease_id: UUID, error: str) -> None
RunWorker.run_forever() -> None
```

**Dependencies:** runtime、storage、infrastructure.event_bus、infrastructure.rate_limiter。

MVP 行为要求：

```text
enqueue writes RunQueueItem to database
claim creates RunLease with lease_until
worker heartbeat extends lease
completed run marks queue item completed
expired lease can be reclaimed or marked failed
```

### `agentgov.trace`

**Responsibility:** 黑箱外部可观测。提供 trace/span/evidence/reasoning summary，让 Agent 决策、报告结论和经验候选都能追溯证据。

**Public Interface:**

```python
TraceService.start_trace(session_id: UUID, run_id: UUID) -> TraceContext
TraceService.start_span(context: TraceContext, span_type: str, name: str) -> SpanRecord
TraceService.finish_span(span_id: UUID, status: str, attributes: dict) -> SpanRecord
TraceService.record_evidence(run_id: UUID, evidence: EvidenceRef) -> EvidenceRef
TraceService.record_reasoning(trace: ReasoningTrace) -> ReasoningTrace
TraceService.get_trace_tree(trace_id: UUID) -> TraceTree
```

**Dependencies:** event_stream、storage、object_store。

### `agentgov.memory`

**Responsibility:** 长期记忆与经验候选。Session 上下文和 Agent 长期成长分开。

**Public Interface:**

```python
MemoryStore.search(agent_id: str, query: str) -> list[MemoryItem]
MemoryStore.commit(candidate_id: UUID) -> MemoryItem
ExperienceService.generate(run_id: UUID) -> list[ExperienceCandidate]
ExperienceService.evaluate(candidate_id: UUID) -> ExperienceCandidate
```

**Dependencies:** event_stream、storage、policy。

### `agentgov.storage`

**Responsibility:** 数据库存储。MVP 用 SQLite 作为本地默认数据库，但抽象层按 PostgreSQL 设计，保证后续迁移到 PostgreSQL 存储 Run / Key / Spend / Audit 时不重构上层业务。

**Public Interface:**

```python
Repository classes for AgentVersion, SessionRecord, RunRecord, RunStep,
ModelCallRecord, ToolCallRecord, SandboxActionRecord, PolicyDecision,
Approval, BudgetLedgerEntry, BudgetPolicySnapshot, ExperienceCandidate.
```

**Dependencies:** SQLAlchemy。

### `agentgov.infrastructure`

**Responsibility:** 外部基础设施适配层。MVP 使用本地或内存实现，但接口直接兼容 PostgreSQL、Redis、MinIO/S3、Qdrant/Milvus。

**Public Interface:**

```python
RelationalStore.session() -> AsyncSession
EventBus.publish(topic: str, event: dict) -> None
EventBus.subscribe(topic: str) -> AsyncIterator[dict]
RateLimiter.check(key: str, limit: RateLimitSpec) -> RateLimitDecision
ObjectStore.put(key: str, data: bytes, metadata: dict) -> ObjectRef
ObjectStore.get(key: str) -> bytes
VectorStore.upsert(items: list[VectorItem]) -> None
VectorStore.search(query: VectorQuery) -> list[VectorSearchResult]
```

MVP implementations:

```text
SqliteRelationalStore
InMemoryEventBus
DbBackedRateLimiter
LocalObjectStore
SqliteFtsVectorStore
```

Production-compatible implementations reserved:

```text
PostgresRelationalStore
RedisEventBus
RedisRateLimiter
S3ObjectStore / MinioObjectStore
QdrantVectorStore / MilvusVectorStore
```

### `agentgov.api`

**Responsibility:** FastAPI HTTP/SSE API。

**Public Routes:**

```text
GET  /health
GET  /agents
GET  /agents/{agent_id}
POST /sessions
GET  /sessions/{session_id}
POST /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/events
GET  /runs/{run_id}/stream
POST /approvals/{approval_id}/decide
GET  /dashboard/agents
GET  /dashboard/runs/{run_id}
GET  /dashboard/overview
GET  /dashboard/topology
GET  /dashboard/tasks
GET  /dashboard/audit-logs
GET  /dashboard/security
```

### `web`

**Responsibility:** 大规模 Agent 治理控制台。不是只追踪单个任务，而是支持几十到上百个 Agent 的系统级治理观察、检索、拓扑、任务调度、权限和审计。

**Views:**

```text
Overview Dashboard:
  total agents, running agents, error agents, success rate, average latency,
  cost today, pending approvals, recent critical events.

Agent Directory:
  searchable/filterable table and card views, grouped by type/project/environment/status.

Agent Detail:
  identity, version, config snapshot, health metrics, dependency edges,
  recent runs, event timeline, budget usage, policy bindings.

Topology View:
  dependency graph, data-flow graph, call-frequency heat graph,
  edge details with latency/failure/call count.

Task Scheduling Center:
  run list, queue view, live running view, priority, assigned agent/team,
  parent-child run relation for multi-agent tasks.

Security And Policy Center:
  role matrix, agent permission matrix, policy bindings, pending approvals.

Audit Log:
  filter by time/operator/agent/action/result; expandable detail and before/after config diff.

Run Detail:
  event timeline, model calls, tool calls, sandbox actions, policy decisions,
  approvals, cost ledger, experience candidates.
```

## Module Interactions

### Single-Agent Run

```text
API POST /runs
  -> RunService.create_run()
  -> TraceService.start_trace()
  -> EventStream.append(run.started)
  -> RunQueue.enqueue()
  -> RunWorker.claim()
  -> SessionLock.acquire(session_id)
  -> RunService.execute()
  -> AgentLoop.events()
  -> ModelGateway.complete()
     -> TraceService.start_span(model.call)
     -> BudgetService.preflight()
     -> PermissionService.check(model.call)
     -> PolicyEngine.enforce(model.call)
     -> ModelProvider.complete()
     -> BudgetService.settle()
     -> TraceService.finish_span()
     -> EventStream.append(model.call.finished)
  -> ToolGateway.call() when tool intent appears
     -> TraceService.start_span(tool.call)
     -> PermissionService.check(tool.call)
     -> PolicyEngine.enforce(tool.call)
     -> ApprovalService.request() if needed
     -> ToolProvider.call() if allowed
     -> TraceService.finish_span()
     -> EventStream.append(tool.call.finished)
  -> RunService.finalize()
  -> ExperienceService.generate()
```

### HITL Resume

```text
ApprovalService.decide(approved)
  -> EventStream.append(approval.decided)
  -> RunService.resume_run()
  -> RunRecord.status = running
  -> continue AgentLoop from persisted context
```

拒绝审批：

```text
ApprovalService.decide(rejected)
  -> EventStream.append(approval.decided)
  -> RunRecord.status = rejected
  -> EventStream.append(run.final)
```

### Multi-Agent Qualification Scenario

```text
Coordinator Run
  -> CollaborationService.delegate(Evidence Agent)
     -> PermissionService.create_delegation()
     -> TeamBus.publish(task.assigned)
     -> child RunRecord(parent_run_id=coordinator_run_id)
     -> Evidence uses ToolGateway search/read
     -> TeamBus.publish(task.result)
  -> CollaborationService.delegate(Execution Agent)
     -> PermissionService.create_delegation()
     -> TeamBus.publish(task.assigned)
     -> child RunRecord(parent_run_id=coordinator_run_id)
     -> Execution uses SandboxService
     -> TeamBus.publish(task.result)
  -> CollaborationService.delegate(Policy Auditor Agent)
     -> child RunRecord records policy review
  -> CollaborationService.delegate(Reviewer Agent)
     -> child RunRecord records evidence review
  -> Coordinator merges child outputs
  -> final report
  -> ExperienceService.generate()
```

### Event Ordering And Concurrency

同一 `session_id` 默认一次只允许一个写上下文的 Run 持有锁。子 Run 可以并发执行，但写回主 Session 时必须通过 Coordinator 合并。

```text
SessionLock
  read-only child runs may run concurrently
  context-writing run must acquire write lock
  event append uses monotonic seq per run
```

## File Organization

```text
agent-governance-platform/
├── spec.md
├── plan.md
├── task.md
├── checklist.md
├── README.md
├── pyproject.toml
├── config/
│   ├── examples/
│   │   ├── local.openai.yaml        - OpenAI-compatible provider example
│   │   ├── local.scripted.yaml      - deterministic test harness config
│   │   └── qualification.yaml       - multi-agent qualification scenario config
│   └── schemas/
│       └── platform.schema.json     - config schema export
├── src/
│   └── agentgov/
│       ├── __init__.py
│       ├── app.py                   - FastAPI app factory
│       ├── cli.py                   - local dev commands
│       ├── config/
│       │   ├── loader.py
│       │   ├── schema.py
│       │   └── registry.py
│       ├── control_plane/
│       │   ├── agents.py
│       │   ├── teams.py
│       │   ├── sessions.py
│       │   └── locks.py
│       ├── runtime/
│       │   ├── run_service.py
│       │   ├── agent_loop.py
│       │   ├── state_machine.py
│       │   └── errors.py
│       ├── event_stream/
│       │   ├── events.py
│       │   ├── stream.py
│       │   └── sse.py
│       ├── policy/
│       │   ├── engine.py
│       │   ├── context.py
│       │   ├── rules.py
│       │   └── decisions.py
│       ├── permission/
│       │   ├── service.py
│       │   ├── identity.py
│       │   ├── resources.py
│       │   └── delegation.py
│       ├── budget/
│       │   ├── service.py
│       │   ├── pricing.py
│       │   ├── ledger.py
│       │   └── snapshot.py
│       ├── approval/
│       │   └── service.py
│       ├── gateway/
│       │   ├── model.py
│       │   ├── tool.py
│       │   └── mcp.py
│       ├── providers/
│       │   ├── scripted_model.py
│       │   ├── openai_compatible.py
│       │   ├── local_repo_tools.py
│       │   ├── local_command_tools.py
│       │   ├── scripted_tools.py
│       │   └── mcp_tools.py
│       ├── sandbox/
│       │   ├── service.py
│       │   ├── base.py
│       │   ├── local_readonly.py
│       │   ├── fault_injection.py
│       │   └── docker_runtime.py
│       ├── collaboration/
│       │   ├── service.py
│       │   ├── strategies.py
│       │   ├── leader_worker.py
│       │   └── team_bus.py
│       ├── scheduler/
│       │   ├── queue.py
│       │   ├── lease.py
│       │   └── worker.py
│       ├── trace/
│       │   ├── context.py
│       │   ├── spans.py
│       │   ├── evidence.py
│       │   ├── reasoning.py
│       │   └── service.py
│       ├── memory/
│       │   ├── store.py
│       │   ├── experience.py
│       │   └── versioning.py
│       ├── storage/
│       │   ├── db.py
│       │   ├── models.py
│       │   ├── repositories.py
│       │   └── migrations/
│       ├── infrastructure/
│       │   ├── relational.py
│       │   ├── event_bus.py
│       │   ├── rate_limiter.py
│       │   ├── object_store.py
│       │   └── vector_store.py
│       ├── dashboard/
│       │   ├── service.py
│       │   ├── health.py
│       │   ├── topology.py
│       │   └── audit_query.py
│       ├── api/
│       │   ├── routes_agents.py
│       │   ├── routes_sessions.py
│       │   ├── routes_runs.py
│       │   ├── routes_approvals.py
│       │   └── routes_dashboard.py
│       └── testing/
│           ├── scripted_model.py
│           ├── scripted_tools.py
│           ├── fault_injection.py
│           ├── fixtures.py
│           ├── replay.py
│           └── qualification_scenario.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── web/
    ├── package.json
    ├── src/
    │   ├── App.tsx
    │   ├── api.ts
    │   ├── pages/
    │   │   ├── Dashboard.tsx
    │   │   ├── AgentDirectory.tsx
    │   │   ├── AgentDetail.tsx
    │   │   ├── Topology.tsx
    │   │   ├── TaskScheduling.tsx
    │   │   ├── SecurityCenter.tsx
    │   │   ├── AuditLog.tsx
    │   │   └── RunDetail.tsx
    │   └── components/
    │       ├── AgentCard.tsx
    │       ├── AgentTable.tsx
    │       ├── TopologyGraph.tsx
    │       ├── TaskQueue.tsx
    │       ├── EventTimeline.tsx
    │       ├── CostPanel.tsx
    │       ├── PolicyPanel.tsx
    │       ├── ApprovalPanel.tsx
    │       ├── AuditTable.tsx
    │       └── MetricCards.tsx
    └── vite.config.ts
```

## Database Tables

```text
agent_versions
sessions
runs
run_steps
model_calls
tool_calls
sandbox_actions
policy_decisions
delegation_grants
approvals
budget_ledger
budget_snapshots
span_records
evidence_refs
reasoning_traces
agent_messages
collaboration_tasks
run_queue
run_leases
memory_items
experience_candidates
agent_health_snapshots
agent_dependency_edges
```

关键索引：

```text
runs(session_id, created_at)
runs(parent_run_id)
runs(status)
run_steps(run_id, seq)
run_steps(session_id, created_at)
policy_decisions(run_id, policy_id)
delegation_grants(parent_run_id, grantee_agent_id)
approvals(run_id, status)
span_records(trace_id, run_id)
evidence_refs(run_id, step_id)
agent_messages(trace_id, created_at)
collaboration_tasks(parent_run_id, assigned_agent_id)
run_queue(status, priority, available_at)
run_leases(run_id, lease_until)
experience_candidates(source_run_id)
agent_health_snapshots(agent_id, last_event_at)
agent_dependency_edges(source_agent_id, target_agent_id)
```

## Infrastructure Compatibility

MVP 不强制启动 PostgreSQL、Redis、MinIO/S3、Qdrant/Milvus，但上层业务必须只依赖接口，不直接依赖具体实现。

| Capability | MVP Implementation | Future Implementation | Used For |
|---|---|---|---|
| Relational DB | SQLite | PostgreSQL | Run / Key / Spend / Audit 持久化 |
| Event Bus | In-memory async pubsub backed by DB events | Redis Streams / PubSub | SSE、事件广播、多副本同步 |
| Rate Limit / Cache | DB-backed counters + in-memory cache | Redis | 预算缓存、限流、分布式锁 |
| Object Store | Local filesystem | MinIO / S3 | 大事件流、文件、报告、快照 |
| Vector Store | SQLite FTS / keyword index | Qdrant / Milvus | 长期记忆、RAG、经验检索 |

落地原则：

```text
业务模块只调用 infrastructure interface。
storage repositories 不直接向 API 暴露 ORM 对象。
数据库是 MVP 的事实源；内存 event bus 只负责本进程实时通知。
事件流先写关系库索引，超大 payload 可外溢到 ObjectStore。
MemoryStore 先写关系库元数据，再把 embedding 或检索索引写 VectorStore。
RateLimiter 和 SessionLock 先支持 DB-backed 本地实现，接口保留 Redis 原子操作语义。
```

## Configuration Shape

```yaml
providers:
  - name: xingwan-gpt
    protocol: openai
    base_url: https://xingwan.store/v1
    api_key_env: XINGWAN_API_KEY
    models:
      - name: gpt-5.5
        input_price: 0.0
        output_price: 0.0

mcp_servers:
  - name: context7
    command: npx
    args: ["-y", "@upstash/context7-mcp"]

sandboxes:
  - id: readonly
    runtime: local_readonly
    filesystem: read_only
    network: disabled
    allowed_commands: ["rg", "python", "pytest"]

policies:
  - id: max_cost_per_run
    type: budget
    max_usd: 1.0

  - id: require_approval_for_write
    type: hitl
    when:
      sandbox_filesystem: write

permissions:
  roles:
    admin:
      allow: ["*"]
    operator:
      allow: ["run.create", "run.cancel", "approval.decide", "agent.view"]
    auditor:
      allow: ["agent.view", "run.view", "audit.view", "policy.view"]
  delegation:
    coordinator:
      can_delegate_to: ["evidence", "execution", "policy_auditor", "reviewer"]
      allowed_actions: ["tool.call", "sandbox.execute.readonly", "report.review"]

agents:
  - id: coordinator
    name: Coordinator Agent
    provider: xingwan-gpt
    model: gpt-5.5
    tools: []
    sandbox: null
    policies: ["max_cost_per_run"]

  - id: evidence
    name: Evidence Agent
    provider: xingwan-gpt
    model: gpt-5.5
    tools: ["repo_search", "repo_read"]
    sandbox: readonly
    policies: ["max_cost_per_run"]

teams:
  - id: governance_review_team
    leader: coordinator
    members: ["evidence", "execution", "policy_auditor", "reviewer"]
    collaboration_strategy: leader_worker
```

`local.scripted.yaml` 和 `qualification.yaml` 可以把 provider 切换为 `scripted`，但这是测试环境配置，不是系统默认路径。

Infrastructure 配置预留：

```yaml
storage:
  relational:
    backend: sqlite
    url: sqlite+aiosqlite:///./data/agentgov.db
  event_bus:
    backend: memory
  cache:
    backend: db
  object_store:
    backend: local
    root: ./data/objects
  vector_store:
    backend: sqlite_fts

budgets:
  global:
    max_usd_per_day: 10.0
  teams:
    governance_review_team:
      max_usd_per_day: 2.0
  agents:
    researcher:
      max_usd_per_run: 0.2
  models:
    gpt-5.5:
      input_price_per_1k: 0.0
      output_price_per_1k: 0.0
```

## Technical Decisions

| Decision | Choice | Reason |
|---|---|---|
| Primary language | Python | 贴近 agent-platform、agentscope、OpenHands，方便你学习迁移和快速实验 |
| Backend framework | FastAPI | 原生 async，适合 SSE、API、控制台 |
| ORM | SQLAlchemy 2.x | 明确数据模型，SQLite/PostgreSQL 兼容 |
| MVP database | SQLite through `RelationalStore` | 本地启动简单；接口保持 PostgreSQL 兼容 |
| Future relational DB | PostgreSQL | 持久化 Run / Key / Spend / Audit 的生产目标 |
| Future event bus/cache | Redis | 多副本事件广播、限流、缓存、分布式锁 |
| Future object storage | MinIO/S3 | 存储大事件 payload、文件、报告、快照 |
| Future vector DB | Qdrant/Milvus | 长期记忆、RAG、经验检索 |
| Event storage | `RunStep` append-first | 支撑审计、恢复、时间线、科研追踪 |
| Agent registration | Config + database snapshot | 配置便于实验，运行绑定 AgentVersion 便于复现 |
| Runtime state | `RunRecord.status` + `RunStep` | 状态表快查，事件解释因果 |
| Model abstraction | `ModelProvider` protocol | 系统 provider 与测试 scripted provider 可替换，但默认主路径是真实 OpenAI-compatible |
| Tool abstraction | `ToolGateway` + providers | 后续接 MCP/A2A，不污染 RunService |
| Sandbox abstraction | `SandboxRuntime` protocol | MVP local readonly，后续 Docker/K8s |
| Policy design | `PolicyEngine` + `PolicyRule` | 横切治理可扩展，不重写主流程 |
| Permission model | `subject/action/resource` + `DelegationGrant` | 多 Agent 需要清楚表达谁代表谁操作什么资源 |
| HITL | `Approval` table + resume API | 等待状态可落库、可恢复、可审计 |
| Multi-agent | `parent_run_id` + `TeamBus` + `CollaborationStrategy` | 子任务、消息、委托链都可追踪，协作策略可替换 |
| Scheduling | `RunQueue` + `RunLease` | 支持高并发和多 worker，避免重复执行 |
| Trace model | `TraceContext` + `SpanRecord` | 支持跨 Agent、模型、工具、沙箱的调用链追踪 |
| Black-box governance | `ReasoningTrace` + `EvidenceRef` | 不记录模型完整思维链，记录可验证的决策摘要与证据 |
| Memory growth | `ExperienceCandidate` before `MemoryItem` | 防止未经评估的经验污染长期记忆 |
| Testing | Scripted model/tool/fault-injection sandbox in Test Harness | 省算力，保证治理测试稳定，同时不替代系统主路径 |
| Console | React/Vite + governance pages | 面向几十到上百 Agent 的系统治理，不只追踪单个 Run |
| Frontend state | TanStack Query + lightweight local state | 服务端数据为主，减少复杂全局状态 |
| Charts/topology | Recharts/ECharts + React Flow | 指标趋势、拓扑关系、调用频率热度 |
| Large lists | Virtualized tables | Agent 和审计日志数量上来后仍可用 |

## Spec Coverage

| Spec Area | Plan Coverage |
|---|---|
| 配置注册 | `agentgov.config`, `PlatformConfig`, YAML shape |
| Agent/Session/Run/Event 分层 | `AgentSpec`, `SessionRecord`, `RunRecord`, `RunStep` |
| 审计事件 | `event_stream`, `RunStep`, `AuditSink` |
| 模型调用与成本 | `ModelGateway`, `ModelCallRecord`, `BudgetService`, `BudgetLedgerEntry`, `BudgetPolicySnapshot` |
| 工具调用 | `ToolGateway`, `ToolCallRecord` |
| 策略与鉴权 | `PolicyEngine`, `PolicyRule`, `PolicyDecision` |
| 权限与委托 | `PermissionService`, `IdentityContext`, `ResourceRef`, `DelegationGrant` |
| HITL | `ApprovalService`, `Approval`, `resume_run` |
| 多 Agent 协作 | `CollaborationService`, `TeamBus`, `AgentMessage`, `LeaderWorkerStrategy`, `parent_run_id` |
| 沙箱隔离 | `SandboxService`, `SandboxRuntime`, `SandboxActionRecord` |
| 黑箱追踪 | `TraceContext`, `SpanRecord`, `ReasoningTrace`, `EvidenceRef` |
| 经验沉淀 | `ExperienceService`, `ExperienceCandidate`, `MemoryStore` |
| 控制台 | `web` Overview, Agent Directory, Agent Detail, Topology, Task Scheduling, Security Center, Audit Log, Run Detail |
| 测试环境 | `testing/scripted_model.py`, `testing/scripted_tools.py`, fault injection, qualification scenario |
| 并发控制 | `SessionLock`, run seq, child run merge |
| 调度与租约 | `RunQueue`, `RunWorker`, `RunLease` |
| 基础设施兼容 | `infrastructure` interfaces for PostgreSQL, Redis, MinIO/S3, Qdrant/Milvus |

