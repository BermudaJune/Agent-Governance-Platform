import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Bot,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Database,
  Download,
  Eye,
  FileText,
  GitBranch,
  Search,
  PauseCircle,
  PanelLeft,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Undo2,
  WalletCards,
  Wrench,
  X
} from "lucide-react";
import { Agent, Approval, AuditEvent, getJson, Overview, postJson, putJson, Run, Session } from "./api";
import "./styles.css";
import { CaseLibrary, SessionReviewPanel } from "./SessionLearning";

type PageKey = "overview" | "dispatch" | "sessions" | "knowledge" | "evolution" | "auditCenter" | "resources" | "config" | "tools" | "agents" | "runs" | "approvals" | "audit" | "topology" | "queue" | "security";
type TopologyNode = { id: string; type: string; label?: string; status?: string | null; metadata?: Record<string, unknown> };
type TopologyEdge = { id?: string; source: string; target: string; type: string; metadata?: Record<string, unknown> };
type Topology = { nodes: TopologyNode[]; edges: TopologyEdge[] };
type TeamConfig = { id: string; leader: string; members: string[]; collaboration_strategy: string };
type ToolSpec = {
  id: string;
  name: string;
  description: string;
  category: string;
  executor: string;
  risk_level: string;
  sandbox?: string | null;
  requires_approval: boolean;
  allowed_domains?: string[];
  source?: string;
  input_schema?: Record<string, unknown>;
};
type SkillSpec = {
  id: string;
  name: string;
  description: string;
  prompt_body?: string;
  recommended_tools: string[];
  output_artifacts: string[];
  capability_ids: string[];
  risk_level: string;
  source: string;
  source_url?: string | null;
  version: string;
  trust_level: string;
  install_mode: string;
  installed: boolean;
  source_ref?: string | null;
  content_hash?: string | null;
  scan_status?: string;
  scan_findings?: string[];
  license?: string | null;
  category?: string;
  tags?: string[];
};
type SkillSearchResult = { repository: string; path?: string; url: string; default_branch: string; description: string; stars: number };
type CapabilityAlternative = { title: string; proposal: string; tradeoff: string; prerequisites: string[] };
type LeaderState = {
  status?: string; understanding?: string; reply?: string; error?: string;
  questions?: string[]; acceptance?: string[];
  diff?: Record<string, string[]>;
  unresolved_gaps?: Array<{ capability: string; reason: string; search_query?: string; alternatives?: CapabilityAlternative[] }>;
  discovery?: Array<{ query: string; capability?: string; status: string; reason?: string; error?: string; repositories: SkillSearchResult[] }>;
};
type TaskRecommendation = {
  task: string;
  required_capabilities: string[];
  required_roles: string[];
  risk_hints: string[];
  expected_artifacts: string[];
  recommended_tools: string[];
  skills: Array<SkillSpec & { score: number; matched_capabilities: string[]; installed?: boolean }>;
};
type MatchingReport = {
  score: number;
  decision: string;
  covered_capabilities: string[];
  missing_capabilities: string[];
  redundant_agents: string[];
  risk_items: Array<Record<string, unknown>>;
  token_waste_warnings: string[];
  explanation: string;
};
type KnowledgeSourceInput = {
  name: string;
  source_type: string;
  content: string;
  locator?: string | null;
  trust_level?: string;
  required_citation: boolean;
  metadata?: Record<string, unknown>;
};
type KnowledgeSource = KnowledgeSourceInput & { id: string; session_id: string; status: string; created_at: string };
type QueueData = { queue: Array<Record<string, unknown>>; leases: Array<Record<string, unknown>>; running_runs: Run[]; recent_runs: Run[] };
type SecurityData = { policy_decisions: Array<Record<string, unknown>>; delegation_grants: Array<Record<string, unknown>>; approvals: Approval[]; budget_ledger: Array<Record<string, unknown>> };
type RunDetail = {
  run: Run | null;
  steps: AuditEvent[];
  model_calls: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
  action_intents?: Array<Record<string, unknown>>;
  observations?: Array<Record<string, unknown>>;
  sandbox_actions: Array<Record<string, unknown>>;
  policy_decisions: Array<Record<string, unknown>>;
  budget_ledger: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  experience_candidates: Array<Record<string, unknown>>;
  artifact_versions?: Array<Record<string, unknown>>;
};
type SessionDetail = {
  session: Session | null;
  runs: Run[];
  approvals?: Approval[];
  steps: AuditEvent[];
  messages: Array<Record<string, unknown>>;
  model_calls: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
  action_intents?: Array<Record<string, unknown>>;
  observations?: Array<Record<string, unknown>>;
  budget_ledger: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  artifacts?: Array<Record<string, unknown>>;
  artifact_versions?: Array<Record<string, unknown>>;
  matching_reports?: Array<Record<string, unknown>>;
  team_snapshot?: Record<string, unknown> | null;
  plans?: Array<Record<string, unknown>>;
  task_nodes?: Array<Record<string, unknown>>;
  task_edges?: Array<Record<string, unknown>>;
  knowledge_sources?: KnowledgeSource[];
  knowledge_grants?: Array<Record<string, unknown>>;
  knowledge_access_events?: Array<Record<string, unknown>>;
  knowledge_policy?: Record<string, unknown>;
  session_agents?: SessionAgent[];
  delegation_requests?: DelegationRequest[];
  skill_grants?: Array<Record<string, unknown>>;
  tool_grants?: Array<Record<string, unknown>>;
  agent_lifecycle_events?: Array<Record<string, unknown>>;
  checkpoints?: Array<Record<string, unknown>>;
  rollback_events?: Array<Record<string, unknown>>;
  requirements?: Array<Record<string, unknown>>;
  current_requirement?: Record<string, unknown> | null;
  feedback?: Array<Record<string, unknown>>;
  replan_required?: boolean;
  affected_nodes?: Array<Record<string, unknown>>;
  stale_artifacts?: Array<Record<string, unknown>>;
};
type SessionAgent = {
  id: string;
  session_id: string;
  agent_id: string;
  parent_agent_id?: string | null;
  role: string;
  origin: string;
  depth: number;
  status: string;
  spec_snapshot?: Record<string, unknown>;
  created_at: string;
};
type DelegationRequest = {
  id: string;
  session_id: string;
  requester_agent_id: string;
  parent_agent_id: string;
  requested_agent_id?: string | null;
  requested_role: string;
  objective: string;
  requested_skills: string[];
  requested_tools: string[];
  budget_usd: number;
  risk_level: string;
  status: string;
  approval_id?: string | null;
  created_at: string;
};
type PlatformConfigResponse = { path: string; config: Record<string, unknown>; note: string };
type GovernanceAction = { id: string; label: string; enabled: boolean; disabled_reason: string; endpoint: string; method: string };
type ActionResponse = { session_id?: string; run_id?: string; status?: string; actions: GovernanceAction[] };
type WorkbenchData = {
  overview: Overview;
  attention_items: Array<Record<string, unknown>>;
  active_sessions: Array<Record<string, unknown>>;
  runtime: Record<string, number>;
  audit_summary: Record<string, number>;
  backend_gaps: string[];
};
type SessionAuditReport = {
  session: Session | null;
  summary: Record<string, number>;
  timeline: AuditEvent[];
  decision_chain: Array<Record<string, unknown>>;
  tool_chain: Array<Record<string, unknown>>;
  model_chain: Array<Record<string, unknown>>;
  artifact_chain: Array<Record<string, unknown>>;
  rollback_chain: Array<Record<string, unknown>>;
  responsibility_chain: Array<Record<string, unknown>>;
  knowledge_chain?: Array<Record<string, unknown>>;
  delegation_chain?: DelegationRequest[];
  agent_lifecycle_chain?: Array<Record<string, unknown>>;
  grant_chain?: Array<Record<string, unknown>>;
};
type AgentForm = {
  id: string;
  name: string;
  provider: string;
  model: string;
  tools: string[];
  skills: string[];
  sandbox: string;
  policies: string[];
  system_prompt: string;
};

const navItems: Array<{ key: PageKey; label: string; group: string }> = [
  { key: "overview", label: "工作台", group: "主流程" },
  { key: "dispatch", label: "交给 Leader", group: "主流程" },
  { key: "sessions", label: "Session 驾驶舱", group: "主流程" },
  { key: "knowledge", label: "知识中心", group: "治理" },
  { key: "evolution", label: "进化实验室", group: "治理" },
  { key: "auditCenter", label: "审计中心", group: "治理" },
  { key: "resources", label: "能力中心", group: "配置" }
];

const knownTools = ["repo_search", "repo_read", "repo_list", "file_read", "file_write", "local_command"];

export default function App() {
  const [page, setPage] = useState<PageKey>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [skills, setSkills] = useState<SkillSpec[]>([]);
  const [teams, setTeams] = useState<TeamConfig[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [topology, setTopology] = useState<Topology>({ nodes: [], edges: [] });
  const [queue, setQueue] = useState<QueueData>({ queue: [], leases: [], running_runs: [], recent_runs: [] });
  const [security, setSecurity] = useState<SecurityData>({ policy_decisions: [], delegation_grants: [], approvals: [], budget_ledger: [] });
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [configText, setConfigText] = useState<string>("");
  const [configPath, setConfigPath] = useState<string>("");
  const [notice, setNotice] = useState<string>("正在读取平台数据...");
  const [latestMatching, setLatestMatching] = useState<MatchingReport | null>(null);
  const [liveSessionEvents, setLiveSessionEvents] = useState<AuditEvent[]>([]);
  const [workbench, setWorkbench] = useState<WorkbenchData | null>(null);
  const [sessionActions, setSessionActions] = useState<ActionResponse | null>(null);
  const [sessionAuditReport, setSessionAuditReport] = useState<SessionAuditReport | null>(null);

  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) ?? runs[0], [runs, selectedRunId]);
  const selectedSession = useMemo(() => sessions.find((item) => item.id === selectedSessionId) ?? sessions[0], [sessions, selectedSessionId]);
  const activeSessionRef = useRef<string | null>(null);
  activeSessionRef.current = selectedSession?.id ?? null;
  const pageCopy = pageMetadata(page);
  const navGroups = useMemo(() => {
    return navItems.reduce<Array<{ group: string; items: typeof navItems }>>((groups, item) => {
      const current = groups.find((entry) => entry.group === item.group);
      if (current) current.items.push(item);
      else groups.push({ group: item.group, items: [item] });
      return groups;
    }, []);
  }, []);

  async function loadSessionData(sessionId: string) {
    const [detail, actions, report] = await Promise.all([
      getJson<SessionDetail>(`/dashboard/sessions/${sessionId}`),
      getJson<ActionResponse>(`/dashboard/sessions/${sessionId}/available-actions`).catch(() => null),
      getJson<SessionAuditReport>(`/dashboard/sessions/${sessionId}/audit-report`).catch(() => null)
    ]);
    if (activeSessionRef.current !== sessionId) return;
    setSessionDetail(detail);
    setSessionActions(actions);
    setSessionAuditReport(report);
  }

  async function refresh(preferredSessionId?: string) {
    const [overviewData, agentData, toolData, skillData, sessionData, runData, approvalData, auditData, topologyData, queueData, securityData, configData, workbenchData] = await Promise.all([
      getJson<Overview>("/dashboard/overview"),
      getJson<Agent[]>("/agents"),
      getJson<ToolSpec[]>("/tools"),
      getJson<SkillSpec[]>("/skills"),
      getJson<Session[]>("/sessions"),
      getJson<Run[]>("/runs"),
      getJson<Approval[]>("/approvals"),
      getJson<AuditEvent[]>("/dashboard/audit"),
      getJson<Topology>("/dashboard/topology"),
      getJson<QueueData>("/dashboard/queue"),
      getJson<SecurityData>("/dashboard/security"),
      getJson<PlatformConfigResponse>("/config"),
      getJson<WorkbenchData>("/dashboard/workbench").catch(() => null)
    ]);
    setOverview(overviewData);
    setAgents(agentData);
    setTools(toolData);
    setSkills(skillData);
    setSessions(sessionData);
    setRuns(runData);
    setApprovals(approvalData);
    setAudit(auditData);
    setTopology(topologyData);
    setQueue(queueData);
    setSecurity(securityData);
    setWorkbench(workbenchData);
    setConfigText(JSON.stringify(configData.config, null, 2));
    setConfigPath(configData.path);
    setTeams(asList(configData.config.teams).map((item) => ({
      id: String(item.id ?? ""),
      leader: String(item.leader ?? ""),
      members: Array.isArray(item.members) ? item.members.map(String) : [],
      collaboration_strategy: String(item.collaboration_strategy ?? "leader_worker")
    })).filter((item) => item.id));

    const runId = selectedRunId ?? runData[0]?.id;
    if (runId) {
      setSelectedRunId(runId);
      setRunDetail(await getJson<RunDetail>(`/dashboard/runs/${runId}`));
    }
    const sessionId = preferredSessionId ?? activeSessionRef.current ?? sessionData[0]?.id;
    if (sessionId) {
      if (preferredSessionId || !activeSessionRef.current) {
        activeSessionRef.current = sessionId;
        setSelectedSessionId(sessionId);
      }
      await loadSessionData(sessionId);
    }
    setNotice(`已同步：${sessionData.length} 个 Session，${runData.length} 条 Run，${auditData.length} 条事件`);
  }

  useEffect(() => {
    refresh().catch((error) => setNotice(`数据读取失败：${error instanceof Error ? error.message : String(error)}`));
  }, []);

  useEffect(() => {
    if (!selectedRun?.id) return;
    getJson<RunDetail>(`/dashboard/runs/${selectedRun.id}`).then(setRunDetail).catch(() => undefined);
  }, [selectedRun?.id]);

  useEffect(() => {
    if (!selectedSession?.id) return;
    setSessionDetail(null);
    setSessionActions(null);
    setSessionAuditReport(null);
    loadSessionData(selectedSession.id).catch(() => undefined);
  }, [selectedSession?.id]);

  useEffect(() => {
    if (!selectedSession?.id) return;
    let active = true;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const scheduleRefresh = () => {
      if (refreshTimer !== undefined) return;
      refreshTimer = setTimeout(() => {
        refreshTimer = undefined;
        if (active) loadSessionData(selectedSession.id).catch(() => undefined);
      }, 300);
    };
    setLiveSessionEvents([]);
    const source = new EventSource(`/events/sessions/${selectedSession.id}`);
    source.onmessage = (event) => {
      if (!event.data) return;
      try {
        const parsed = JSON.parse(event.data) as AuditEvent;
        if (!active || activeSessionRef.current !== selectedSession.id) return;
        setLiveSessionEvents((current) => current.some((item) => item.id === parsed.id) ? current : [...current, parsed].slice(-120));
        scheduleRefresh();
      } catch {
        // SSE heartbeat; persisted history is still loaded through session detail.
      }
    };
    source.addEventListener("run.final", () => {
      if (active) scheduleRefresh();
    });
    source.onerror = () => source.close();
    return () => { active = false; clearTimeout(refreshTimer); source.close(); };
  }, [selectedSession?.id]);

  async function executeRun(runId: string) {
    setNotice("正在执行 Run...");
    const result = await postJson<Record<string, unknown>>(`/runs/${runId}/execute`);
    await refresh();
    setNotice(result.status === "failed" ? `执行失败：${String(result.error ?? "未知错误")}` : "执行完成，审计链路已刷新");
  }

  async function controlRun(runId: string, action: "pause" | "cancel" | "resume") {
    const label = action === "pause" ? "暂停" : action === "cancel" ? "取消" : "恢复";
    setNotice(`正在${label} Run...`);
    const result = await postJson<Record<string, unknown>>(`/runs/${runId}/${action}`, {
      reason: `控制台${label}`,
      execute_now: false
    });
    await refresh();
    setNotice(`Run 已${label}：${String(result.status ?? "ok")}`);
  }

  async function retryRun(runId: string) {
    setNotice("正在创建重试 Run...");
    const result = await postJson<{ retry_run_id?: string; status?: string }>(`/runs/${runId}/retry`, { execute_now: false });
    await refresh();
    if (result.retry_run_id) setSelectedRunId(result.retry_run_id);
    setNotice(result.retry_run_id ? "重试 Run 已创建，可在 Session 中继续执行" : "当前 Run 不满足重试条件");
  }

  async function controlSession(sessionId: string, action: "pause" | "cancel" | "resume" | "execute-pending") {
    const label = action === "pause" ? "暂停" : action === "cancel" ? "取消" : action === "resume" ? "恢复" : "执行待处理 Run";
    setNotice(`正在${label} Session...`);
    const result = await postJson<Record<string, unknown>>(
      `/sessions/${sessionId}/${action}`,
      action === "execute-pending" ? {} : { reason: `控制台${label}`, execute_now: false }
    );
    await refresh();
    setNotice(`Session：${String(result.status ?? "ok")}${result.reason ? ` · ${String(result.reason)}` : ""}${typeof result.executed === "number" ? ` · 本轮执行 ${result.executed} 个步骤` : ""}`);
  }

  async function createCheckpoint(sessionId: string) {
    await postJson(`/sessions/${sessionId}/checkpoints`, { label: "操作员检查点", reason: "用户在 Session 驾驶舱主动创建" });
    await refresh();
    setNotice("检查点已创建，后续运行可追加式回滚到此状态");
  }

  async function rollbackSession(sessionId: string, checkpointId: string) {
    if (!checkpointId) return;
    await postJson(`/sessions/${sessionId}/rollback`, { checkpoint_id: checkpointId, reason: "用户在 Session 驾驶舱执行回滚" });
    await refresh();
    setNotice("已记录回滚事件，Session 已暂停等待继续执行");
  }

  async function submitSessionFeedback(sessionId: string, payload: Record<string, unknown>) {
    setNotice("Leader 正在处理你的反馈并调整方案...");
    const result = await postJson<{ status?: string; impact?: { affected_node_keys?: string[]; approval_required?: boolean } }>(`/sessions/${sessionId}/leader/messages`, payload);
    await refresh();
    const affected = result.impact?.affected_node_keys?.length ?? 0;
    setNotice(result.status === "planning_failed" ? "反馈已保存，Leader 暂未完成规划，请查看原因后重试" : `Leader 已处理反馈，${affected} 个步骤受影响，请检查新方案`);
  }

  async function requestSessionReplan(sessionId: string) {
    setNotice("Leader 正在重新分析需求...");
    const result = await postJson<{ status?: string }>(`/sessions/${sessionId}/replan`, {});
    await refresh();
    setNotice(result.status === "planning_failed" ? "规划未完成，需求和历史结果已保留，请查看错误详情" : "Leader 已返回新方案，请检查理解与步骤");
  }

  async function decideSessionPlan(sessionId: string, approved: boolean) {
    const plans = sessionDetail?.plans ?? [];
    const planId = plans[plans.length - 1]?.id;
    await postJson(`/sessions/${sessionId}/plan-decision`, { approved, plan_id: planId, approver_id: "operator", reason: approved ? "用户批准 Leader 新计划" : "用户拒绝 Leader 新计划" });
    await refresh();
    setNotice(approved ? "新计划已批准，可以继续执行" : "新计划已拒绝，Session 等待再次校正");
  }

  async function saveConfig() {
    try {
      if (!configText.trim()) throw new Error("配置尚未加载成功");
      const parsed = JSON.parse(configText);
      await postJson("/config/validate", { config: parsed });
      await putJson("/config", { config: parsed });
      await refresh();
      setNotice("配置已保存。Provider 和模型运行时变更需要重启后端，Agent 列表可刷新读取。");
    } catch (error) {
      setNotice(`配置保存失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function dispatchTask(agentId: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>) {
    setNotice("正在发配任务...");
    const result = await postJson<{ run_id: string; session_id: string; status: string; result?: { error?: string } }>("/tasks/dispatch", {
      title,
      owner_id: "operator",
      agent_id: agentId,
      input_summary: inputSummary,
      execute_now: executeNow,
      knowledge_sources: knowledgeSources,
      knowledge_policy: knowledgePolicy
    });
    await refresh();
    setSelectedRunId(result.run_id);
    setSelectedSessionId(result.session_id);
    setPage("runs");
    setNotice(result.status === "failed" ? `任务执行失败：${result.result?.error ?? "请查看 Run 详情"}` : "任务已创建，审计记录已生成");
  }

  async function dispatchLeaderTask(leaderId: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>, requestedSkills: string[], requestedTools: string[]) {
    setNotice("正在创建 Leader Session...");
    const result = await postJson<{ session_id: string; parent_run_id?: string; status: string; result?: { error?: string } }>("/tasks/dispatch-leader", {
      title,
      owner_id: "operator",
      leader_id: leaderId,
      input_summary: inputSummary,
      execute_now: executeNow,
      requested_skills: requestedSkills,
      requested_tools: requestedTools,
      knowledge_sources: knowledgeSources,
      knowledge_policy: knowledgePolicy
    });
    await refresh(result.session_id);
    setSelectedSessionId(result.session_id);
    if (result.parent_run_id) setSelectedRunId(result.parent_run_id);
    setPage("sessions");
    setNotice(result.status === "planning_failed" ? "任务已保存，Leader 规划遇到问题，可在驾驶舱重试" : result.status === "needs_clarification" ? "Leader 有待确认的问题，请在对话中补充" : result.status === "capability_gap" ? "Leader 发现能力缺口，正在寻找解决途径" : "Leader 已接收任务，请检查方案后批准");
  }

  async function dispatchTeamTask(teamId: string, strategy: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>) {
    setNotice("正在发配多 Agent Team 任务...");
    const result = await postJson<{ session_id?: string; parent_run_id?: string; run_ids?: string[]; status: string; matching?: MatchingReport; report?: MatchingReport; blocked?: boolean }>("/tasks/dispatch-team", {
      title,
      owner_id: "operator",
      team_id: teamId,
      strategy,
      input_summary: inputSummary,
      execute_mode: executeNow ? "enqueue" : "manual",
      knowledge_sources: knowledgeSources,
      knowledge_policy: knowledgePolicy
    });
    setLatestMatching(result.matching ?? result.report ?? null);
    if (result.blocked || !result.session_id || !result.parent_run_id) {
      setNotice(`Team 能力匹配未通过：${result.report?.explanation ?? "请调整 Team 或强制执行"}`);
      return;
    }
    await refresh();
    setSelectedSessionId(result.session_id);
    setSelectedRunId(result.parent_run_id);
    setPage("topology");
    setNotice(`Team 任务已创建：${result.run_ids?.length ?? 0} 个 Run，模式 ${executeNow ? "后台入队" : "手动执行"}，匹配分 ${result.matching?.score ?? "-"}`);
  }

  async function dispatchAdHocTeamTask(leader: string, members: string[], strategy: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>) {
    setNotice("正在创建临时多 Agent Session...");
    const result = await postJson<{ session_id?: string; parent_run_id?: string; run_ids?: string[]; status: string; matching?: MatchingReport; report?: MatchingReport; blocked?: boolean }>("/tasks/dispatch-ad-hoc-team", {
      title,
      owner_id: "operator",
      leader,
      members,
      strategy,
      input_summary: inputSummary,
      execute_mode: executeNow ? "enqueue" : "manual",
      knowledge_sources: knowledgeSources,
      knowledge_policy: knowledgePolicy
    });
    setLatestMatching(result.matching ?? result.report ?? null);
    if (result.blocked || !result.session_id || !result.parent_run_id) {
      setNotice(`临时 Team 能力匹配未通过：${result.report?.explanation ?? "请调整 Agent 组合"}`);
      return;
    }
    await refresh();
    setSelectedSessionId(result.session_id);
    setSelectedRunId(result.parent_run_id);
    setPage("topology");
    setNotice(`临时 Team 已创建：${result.run_ids?.length ?? 0} 个 Run，模式 ${executeNow ? "后台入队" : "手动执行"}，匹配分 ${result.matching?.score ?? "-"}`);
  }

  async function workerTick() {
    const result = await postJson<{ processed: number }>("/worker/tick", {});
    await refresh();
    setNotice(`Worker 已处理 ${result.processed} 个队列项`);
  }

  async function saveTeamTemplate(sessionId: string) {
    const name = window.prompt("团队模板名称", "可复用 Agent 团队");
    if (!name) return;
    await postJson(`/teams/templates/from-session/${sessionId}`, {
      name,
      description: "从 Session 快照保存的团队模板"
    });
    await refresh();
    setNotice(`团队模板已保存：${name}`);
  }

  async function runStoryDemo() {
    setNotice("正在创建双 Agent 故事 Session...");
    const result = await postJson<{ session_id: string; run_ids: string[]; status: string }>("/tasks/demo/story-session", {
      owner_id: "operator",
      execute_now: true
    });
    await refresh();
    setSelectedSessionId(result.session_id);
    setSelectedRunId(result.run_ids[0]);
    setPage("sessions");
    setNotice(result.status === "completed" ? "故事 Session 完成：已生成 story.md 和 review.md" : "故事 Session 失败，请查看 Session 复盘");
  }

  async function decideApproval(approval: Approval, approved: boolean) {
    try {
      setNotice(approved ? "正在批准并恢复 Run..." : "正在拒绝审批...");
      const result = await postJson<{ status?: string; run_status?: string }>(`/approvals/${approval.id}/decide`, {
        approved,
        approver_id: "operator",
        reason: approved ? "控制台审批通过" : "控制台审批拒绝"
      });
      await refresh();
      setNotice(approved ? `审批已通过，Run 状态：${result.run_status ?? "已记录"}` : "审批已拒绝，Run 已停止");
    } catch (error) {
      setNotice(`审批失败：${error instanceof Error ? error.message : String(error)}`);
      throw error;
    }
  }

  async function requestDelegation(sessionId: string, payload: Record<string, unknown>) {
    try {
      await postJson(`/sessions/${sessionId}/delegations`, payload);
      await refresh();
      setNotice("Leader 扩展请求已提交，治理状态已刷新");
    } catch (error) {
      setNotice(`扩展请求失败：${error instanceof Error ? error.message : String(error)}`);
      throw error;
    }
  }

  async function decideDelegation(delegationId: string, approved: boolean) {
    try {
      await postJson(`/delegations/${delegationId}/decide`, {
        approved,
        approver_id: "operator",
        reason: approved ? "Session 驾驶舱批准扩展" : "Session 驾驶舱拒绝扩展"
      });
      await refresh();
      setNotice(approved ? "扩展已批准，Agent 和授权已刷新" : "扩展已拒绝，决定已写入审计");
    } catch (error) {
      setNotice(`扩展审批失败：${error instanceof Error ? error.message : String(error)}`);
      throw error;
    }
  }

  async function createDemoApproval() {
    await postJson("/approvals/demo", {});
    await refresh();
    setPage("approvals");
    setNotice("已生成一条高风险工具调用审批");
  }

  async function registerTool(tool: ToolSpec) {
    await postJson("/tools/register", { tool });
    await refresh();
    setNotice(`工具已注册：${tool.id}。现在可以在配置中心给 Agent 勾选这个工具。`);
  }

  async function registerSkill(skill: SkillSpec) {
    const approved = skill.scan_status !== "review" || window.confirm(`Skill ${skill.name} 存在扫描提示，确认仍然登记吗？`);
    if (!approved) return;
    await postJson("/skills/register", { skill: { ...skill, installed: undefined }, approved });
    await refresh();
    setNotice(`技能已登记：${skill.name}。完成 Session 授权后可加载；工具依赖单独检查。`);
  }

  async function registerSkillsBatch(skillsToRegister: SkillSpec[], approved = false) {
    await postJson("/skills/register-batch", {
      skills: skillsToRegister.map((skill) => ({ ...skill, installed: undefined })),
      approved
    });
    await refresh();
    setNotice(`已批量登记 ${skillsToRegister.length} 个技能，重启后端后生效。`);
  }

  async function scanGitHubSkills(url: string, ref: string, subpath: string): Promise<SkillSpec[]> {
    try {
      const result = await postJson<{ candidates: SkillSpec[]; repository: string; commit_sha: string; truncated?: boolean }>("/skills/github/scan", {
        url,
        ref: ref.trim() || null,
        subpath: subpath.trim() || null
      });
      const suffix = result.truncated ? "（仓库过大，已使用可用树结果）" : "";
      setNotice(`已扫描 ${result.repository}：发现 ${result.candidates.length} 个 Skill${suffix}`);
      return result.candidates;
    } catch (error) {
      setNotice(`GitHub 扫描失败：${error instanceof Error ? error.message : String(error)}`);
      return [];
    }
  }

  async function searchGitHubSkills(query: string): Promise<SkillSearchResult[]> {
    const result = await postJson<{ results: SkillSearchResult[] }>("/skills/github/search", { query, per_page: 20 });
    setNotice(`GitHub 找到 ${result.results.length} 个可扫描仓库`);
    return result.results;
  }

  async function recommendTask(task: string): Promise<TaskRecommendation> {
    return getJson<TaskRecommendation>(`/skills/recommend?task=${encodeURIComponent(task)}`);
  }

  return (
    <main className="shell">
      <aside className="nav">
        <div className="brand"><ShieldCheck size={22} /> AgentGov</div>
        {navGroups.map((group) => (
          <div className="navGroup" key={group.group}>
            <span>{group.group}</span>
            {group.items.map((item) => (
              <button className={page === item.key ? "active" : ""} key={item.key} onClick={() => setPage(item.key)}>{item.label}</button>
            ))}
          </div>
        ))}
      </aside>
      <section className="content">
        <header className="topbar">
          <div>
            <h1>{pageCopy.title}</h1>
            <p>{pageCopy.description}</p>
          </div>
          <button className="iconButton" onClick={() => refresh()} title="刷新数据"><RefreshCw size={18} /></button>
        </header>
        <div className="notice">{notice}</div>

        {page === "overview" && <OverviewPage workbench={workbench} overview={overview} agents={agents} sessions={sessions} runs={runs} approvals={approvals} audit={audit} queue={queue} setPage={setPage} setSelectedSessionId={setSelectedSessionId} setSelectedRunId={setSelectedRunId} runStoryDemo={runStoryDemo} />}
        {page === "dispatch" && <LeaderTaskPage agents={agents} skills={skills} recommendTask={recommendTask} dispatchLeaderTask={dispatchLeaderTask} />}
        {page === "sessions" && <SessionCockpitPage sessions={sessions} selectedSessionId={selectedSession?.id ?? null} setSelectedSessionId={setSelectedSessionId} detail={sessionDetail} auditReport={sessionAuditReport} availableActions={sessionActions?.actions ?? []} liveEvents={liveSessionEvents} setSelectedRunId={setSelectedRunId} setPage={setPage} controlSession={controlSession} createCheckpoint={createCheckpoint} rollbackSession={rollbackSession} saveTeamTemplate={saveTeamTemplate} agents={agents} skills={skills} tools={tools} requestDelegation={requestDelegation} decideDelegation={decideDelegation} decideApproval={decideApproval} submitSessionFeedback={submitSessionFeedback} requestSessionReplan={requestSessionReplan} decideSessionPlan={decideSessionPlan} />}
        {page === "knowledge" && <KnowledgeCenterPage sessions={sessions} selectedSessionId={selectedSession?.id ?? null} detail={sessionDetail} setSelectedSessionId={setSelectedSessionId} openSession={(id) => { setSelectedSessionId(id); setPage("sessions"); }} />}
        {page === "evolution" && <EvolutionLabPage />}
        {page === "auditCenter" && <AuditCenterPage approvals={approvals} runs={runs} audit={audit} topology={topology} sessions={sessions} selectedSessionId={selectedSession?.id ?? null} sessionAuditReport={sessionAuditReport} teams={teams} security={security} selectedRunId={selectedRun?.id ?? null} setSelectedRunId={setSelectedRunId} runDetail={runDetail} executeRun={executeRun} controlRun={controlRun} decideApproval={decideApproval} createDemoApproval={createDemoApproval} />}
        {page === "resources" && <ResourceCenterPage configText={configText} setConfigText={setConfigText} saveConfig={saveConfig} configPath={configPath} tools={tools} skills={skills} registerTool={registerTool} registerSkill={registerSkill} registerSkillsBatch={registerSkillsBatch} scanGitHubSkills={scanGitHubSkills} searchGitHubSkills={searchGitHubSkills} agents={agents} runs={runs} security={security} queue={queue} workerTick={workerTick} />}
        {page === "config" && <ConfigPage configText={configText} setConfigText={setConfigText} saveConfig={saveConfig} configPath={configPath} tools={tools} skills={skills} />}
        {page === "tools" && <ToolsPage tools={tools} registerTool={registerTool} />}
        {page === "agents" && <AgentsPage agents={agents} runs={runs} security={security} />}
        {page === "runs" && <RunsPage runs={runs} selectedRunId={selectedRun?.id ?? null} setSelectedRunId={setSelectedRunId} runDetail={runDetail} executeRun={executeRun} controlRun={controlRun} retryRun={retryRun} />}
        {page === "approvals" && <ApprovalsPage approvals={approvals} decideApproval={decideApproval} createDemoApproval={createDemoApproval} />}
        {page === "audit" && <AuditPage audit={audit} />}
        {page === "topology" && <TopologyPage topology={topology} sessions={sessions} selectedSessionId={selectedSession?.id ?? null} teams={teams} />}
        {page === "queue" && <QueuePage queue={queue} workerTick={workerTick} />}
        {page === "security" && <SecurityPage security={security} />}
      </section>
    </main>
  );
}

function OverviewPage({
  workbench,
  overview,
  agents,
  sessions,
  runs,
  approvals,
  audit,
  queue,
  setPage,
  setSelectedSessionId,
  setSelectedRunId,
  runStoryDemo
}: {
  workbench: WorkbenchData | null;
  overview: Overview | null;
  agents: Agent[];
  sessions: Session[];
  runs: Run[];
  approvals: Approval[];
  audit: AuditEvent[];
  queue: QueueData;
  setPage: (page: PageKey) => void;
  setSelectedSessionId: (id: string) => void;
  setSelectedRunId: (id: string) => void;
  runStoryDemo: () => void;
}) {
  const pendingApprovals = approvals.filter((approval) => approval.status === "pending");
  const blockedSessions = sessions.filter((session) => ["failed", "blocked", "awaiting_approval", "paused"].includes(session.status)).slice(0, 6);
  const runningSessions = sessions.filter((session) => ["running", "pending", "idle"].includes(session.status)).slice(0, 6);
  const failedRuns = runs.filter((run) => run.status === "failed").slice(0, 5);
  const runningRuns = runs.filter((run) => ["running", "pending", "awaiting_approval"].includes(run.status));
  const attentionItems = workbench?.attention_items ?? [];
  const activeSessions = workbench?.active_sessions ?? [];
  const displayAttention = attentionItems.length > 0;
  const displayActiveSessions = activeSessions.length > 0;
  const runtime = workbench?.runtime;
  const auditSummary = workbench?.audit_summary;

  function openSession(sessionId: string) {
    setSelectedSessionId(sessionId);
    setPage("sessions");
  }

  function openRun(runId: string) {
    setSelectedRunId(runId);
    setPage("runs");
  }

  return (
    <section className="pageStack">
      <section className="commandStrip">
        <article>
          <span>待我处理</span>
          <strong>{attentionItems.length || pendingApprovals.length + failedRuns.length + blockedSessions.length}</strong>
          <p>审批、失败和阻塞项集中处理。</p>
        </article>
        <article>
          <span>运行负载</span>
          <strong>{runtime?.running_runs ?? runningRuns.length}</strong>
          <p>{runtime?.queue_items ?? queue.queue.length} 个队列项，{runtime?.leases ?? queue.leases.length} 个 lease。</p>
        </article>
        <article>
          <span>治理覆盖</span>
          <strong>{agents.length}</strong>
          <p>{auditSummary?.policy_decisions ?? overview?.policy_decisions ?? 0} 条策略决策，{audit.length} 条事件。</p>
        </article>
        <article>
          <span>预算消耗</span>
          <strong>${(overview?.cost_usd ?? 0).toFixed(4)}</strong>
          <p>预算账本已接入，阈值告警待后端补齐。</p>
        </article>
      </section>

      <section className="workbenchGrid">
        <Panel title="待我处理">
          <div className="attentionList">
            {displayAttention ? attentionItems.map((item) => (
              <button className={`attentionItem ${String(item.severity ?? "")}`} key={String(item.id)} onClick={() => {
                const action = String(item.action ?? "");
                const sessionId = String(item.session_id ?? "");
                const runId = String(item.run_id ?? "");
                if (action === "open_approvals") setPage("auditCenter");
                else if (runId) openRun(runId);
                else if (sessionId) openSession(sessionId);
              }}>
                {String(item.kind).includes("approval") ? <ClipboardCheck size={17} /> : String(item.severity) === "danger" ? <AlertTriangle size={17} /> : <PauseCircle size={17} />}
                <span><strong>{displayText(String(item.title ?? "-"))}</strong><em>{displayText(String(item.summary ?? "-"))}</em></span>
                <ArrowRight size={16} />
              </button>
            )) : (
              <>
                {pendingApprovals.slice(0, 4).map((approval) => (
                  <button className="attentionItem warning" key={approval.id} onClick={() => setPage("auditCenter")}>
                    <ClipboardCheck size={17} />
                    <span><strong>待审批工具调用</strong><em>{approval.reason || approval.requested_by}</em></span>
                    <ArrowRight size={16} />
                  </button>
                ))}
                {failedRuns.map((run) => (
                  <button className="attentionItem danger" key={run.id} onClick={() => openRun(run.id)}>
                    <AlertTriangle size={17} />
                    <span><strong>{run.agent_id} 执行失败</strong><em>{displayText(run.input_summary)}</em></span>
                    <ArrowRight size={16} />
                  </button>
                ))}
                {blockedSessions.map((session) => (
                  <button className="attentionItem" key={session.id} onClick={() => openSession(session.id)}>
                    <PauseCircle size={17} />
                    <span><strong>{displayText(session.title)}</strong><em>{session.status} / {session.root_agent_id || "未指定 Agent"}</em></span>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </>
            )}
            {!displayAttention && !pendingApprovals.length && !failedRuns.length && !blockedSessions.length && <p className="emptyState">当前没有需要人工介入的 Session。</p>}
          </div>
        </Panel>

        <Panel title="运行中 Session">
          <div className="sessionRail">
            {displayActiveSessions ? activeSessions.map((session) => (
              <button className="sessionTile" key={String(session.id)} onClick={() => openSession(String(session.id))}>
                <div>
                  <strong>{displayText(String(session.title ?? session.id))}</strong>
                  <span>{shortId(String(session.id))} / {String(session.root_agent_id ?? "无 Root Agent")} / {String(session.stage ?? "unknown")}</span>
                </div>
                <Badge value={String(session.status ?? "unknown")} />
              </button>
            )) : runningSessions.map((session) => (
              <button className="sessionTile" key={session.id} onClick={() => openSession(session.id)}>
                <div>
                  <strong>{displayText(session.title)}</strong>
                  <span>{shortId(session.id)} / {session.root_agent_id || "无 Root Agent"}</span>
                </div>
                <Badge value={session.status} />
              </button>
            ))}
            {!displayActiveSessions && !runningSessions.length && <p className="emptyState">暂无运行中任务。</p>}
          </div>
        </Panel>
      </section>

      <section className="grid">
        <Panel title="治理指标">
          <section className="metrics compactMetrics">
            <Metric icon={<GitBranch />} label="Session" value={sessions.length} />
            <Metric icon={<Activity />} label="Run" value={overview?.runs ?? 0} />
            <Metric icon={<Clock />} label="运行中" value={overview?.running ?? 0} />
            <Metric icon={<CheckCircle2 />} label="已完成" value={overview?.completed ?? 0} />
            <Metric icon={<AlertTriangle />} label="失败" value={overview?.failed ?? 0} />
            <Metric icon={<WalletCards />} label="成本 USD" value={(overview?.cost_usd ?? 0).toFixed(4)} />
          </section>
        </Panel>
        <Panel title="快速启动">
          <p className="muted">用演示 Session 验证完整链路，或进入新建任务选择 Team、策略和执行模式。</p>
          <div className="heroActions">
            <button className="primaryButton" onClick={() => setPage("dispatch")}><Send size={16} />新建治理任务</button>
            <button onClick={runStoryDemo}><FileText size={16} />运行故事 Session</button>
          </div>
          <Signal label="Agent 数量" value={agents.length} />
          <Signal label="审计事件" value={audit.length} />
          <Signal label="后端待补" value={(workbench?.backend_gaps ?? ["回滚", "产物版本", "策略预览"]).slice(0, 3).join(" / ")} />
        </Panel>
      </section>
    </section>
  );
}

function ConfigPage({ configText, setConfigText, saveConfig, configPath, tools, skills }: { configText: string; setConfigText: (value: string) => void; saveConfig: () => void; configPath: string; tools: ToolSpec[]; skills: SkillSpec[] }) {
  const parsed = useMemo(() => parseConfig(configText), [configText]);
  const agents = asList(parsed?.agents);
  const providers = asList(parsed?.providers);
  const sandboxes = asList(parsed?.sandboxes);
  const policies = asList(parsed?.policies);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [form, setForm] = useState<AgentForm>(emptyAgentForm());

  useEffect(() => {
    const firstId = selectedAgentId || String(agents[0]?.id ?? "");
    const agent = agents.find((item) => item.id === firstId);
    if (agent) {
      setSelectedAgentId(String(agent.id));
      setForm(agentToForm(agent));
    }
  }, [configText]);

  const providerOptions = providers.map((provider) => String(provider.name ?? "")).filter(Boolean);
  const modelOptions = providerModels(providers, form.provider);
  const sandboxOptions = sandboxes.map((sandbox) => String(sandbox.id ?? "")).filter(Boolean);
  const policyOptions = policies.map((policy) => String(policy.id ?? "")).filter(Boolean);
  const toolOptions = tools.length ? tools.map((tool) => tool.id) : knownTools;
  const skillOptions = skills.filter((skill) => skill.installed).map((skill) => skill.id);

  function selectAgent(agentId: string) {
    const agent = agents.find((item) => item.id === agentId);
    if (!agent) return;
    setSelectedAgentId(agentId);
    setForm(agentToForm(agent));
  }

  function newAgent() {
    const provider = providerOptions[0] ?? "";
    setSelectedAgentId("");
    setForm({
      id: "coding_worker",
      name: "编程执行 Agent",
      provider,
      model: providerModels(providers, provider)[0] ?? "",
      tools: ["repo_search", "repo_read", "file_read", "file_write"],
      skills: skillOptions.slice(0, 2),
      sandbox: sandboxOptions[0] ?? "",
      policies: policyOptions[0] ? [policyOptions[0]] : [],
      system_prompt: "你是受治理平台约束的编程 Agent。所有文件写入必须进入当前 Session 工作区，所有结论必须可追溯。"
    });
  }

  function toggleList(field: "tools" | "skills" | "policies", value: string) {
    setForm((current) => {
      const exists = current[field].includes(value);
      return { ...current, [field]: exists ? current[field].filter((item) => item !== value) : [...current[field], value] };
    });
  }

  function writeAgentDraft() {
    if (!parsed) return;
    const next = { ...parsed };
    const nextAgents = [...agents];
    const draft: Record<string, unknown> = {
      id: form.id.trim(),
      name: form.name.trim(),
      provider: form.provider,
      model: form.model,
      tools: form.tools,
      skills: form.skills,
      sandbox: form.sandbox || null,
      policies: form.policies,
      system_prompt: form.system_prompt,
      metadata: {}
    };
    const index = nextAgents.findIndex((agent) => agent.id === draft.id);
    if (index >= 0) nextAgents[index] = draft;
    else nextAgents.push(draft);
    next.agents = nextAgents;
    setConfigText(JSON.stringify(next, null, 2));
    setSelectedAgentId(String(draft.id));
  }

  return (
    <section className="pageStack">
      <Panel title="可视化 Agent Builder">
        <div className="explain"><Settings size={18} /><span>这里配置的是长期能力模板。任务发配后会生成 Session 和 Run，审计、预算、工具调用都挂在具体运行上。</span></div>
        <div className="builder">
          <div className="builderList">
            <button className="primaryButton" onClick={newAgent}>新建 Agent</button>
            {agents.map((agent) => (
              <button className={selectedAgentId === agent.id ? "builderItem active" : "builderItem"} key={String(agent.id)} onClick={() => selectAgent(String(agent.id))}>
                <strong>{displayText(String(agent.name ?? agent.id))}</strong>
                <span>{String(agent.id)}</span>
              </button>
            ))}
          </div>
          <div className="builderForm">
            <div className="formGrid">
              <label>Agent ID</label><input value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} />
              <label>名称</label><input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
              <label>Provider</label>
              <select value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value, model: providerModels(providers, event.target.value)[0] ?? "" })}>
                {!providerOptions.length && <option value="">未配置 provider</option>}
                {providerOptions.map((provider) => <option key={provider} value={provider}>{provider}</option>)}
              </select>
              <label>模型</label>
              <select value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })}>
                {!modelOptions.length && <option value={form.model}>{form.model || "未配置模型"}</option>}
                {[form.model, ...modelOptions].filter(Boolean).filter(unique).map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
              <label>沙箱</label>
              <select value={form.sandbox} onChange={(event) => setForm({ ...form, sandbox: event.target.value })}>
                <option value="">不使用沙箱</option>
                {sandboxOptions.map((sandbox) => <option key={sandbox} value={sandbox}>{sandbox}</option>)}
              </select>
              <label>系统提示词</label><textarea value={form.system_prompt} onChange={(event) => setForm({ ...form, system_prompt: event.target.value })} />
            </div>
            <FieldGroup title="工具能力">{toolOptions.map((tool) => <Chip key={tool} checked={form.tools.includes(tool)} label={tool} onClick={() => toggleList("tools", tool)} />)}</FieldGroup>
            <FieldGroup title="技能绑定">{skillOptions.map((skill) => <Chip key={skill} checked={form.skills.includes(skill)} label={skill} onClick={() => toggleList("skills", skill)} />)}</FieldGroup>
            <FieldGroup title="治理策略">{policyOptions.map((policy) => <Chip key={policy} checked={form.policies.includes(policy)} label={policy} onClick={() => toggleList("policies", policy)} />)}</FieldGroup>
            <div className="panelToolbar"><button className="primaryButton" onClick={writeAgentDraft} disabled={!parsed}>写入配置草稿</button><button className="primaryButton" onClick={saveConfig} disabled={!parsed}>校验并保存</button></div>
          </div>
        </div>
      </Panel>
      <Panel title="高级 JSON 配置">
        <div className="panelToolbar"><span className="pathText">{configPath}</span><button className="primaryButton" onClick={saveConfig} disabled={!parsed}><Settings size={16} />校验并保存</button></div>
        <textarea className="configEditor" value={configText} onChange={(event) => setConfigText(event.target.value)} spellCheck={false} />
      </Panel>
    </section>
  );
}

function SkillLibraryPage({ skills, registerSkill, registerSkillsBatch, scanGitHubSkills, searchGitHubSkills }: { skills: SkillSpec[]; registerSkill: (skill: SkillSpec) => void; registerSkillsBatch: (skills: SkillSpec[], approved?: boolean) => void; scanGitHubSkills: (url: string, ref: string, subpath: string) => Promise<SkillSpec[]>; searchGitHubSkills: (query: string) => Promise<SkillSearchResult[]> }) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [category, setCategory] = useState("all");
  const [selected, setSelected] = useState<string[]>([]);
  const [githubUrl, setGithubUrl] = useState("");
  const [githubRef, setGithubRef] = useState("");
  const [githubSubpath, setGithubSubpath] = useState("");
  const [githubCandidates, setGithubCandidates] = useState<SkillSpec[]>([]);
  const [scanning, setScanning] = useState(false);
  const [githubQuery, setGithubQuery] = useState("");
  const [githubResults, setGithubResults] = useState<SkillSearchResult[]>([]);
  const [searchingGithub, setSearchingGithub] = useState(false);
  const filtered = skills.filter((skill) => {
    const haystack = `${skill.id} ${skill.name} ${skill.description} ${skill.recommended_tools.join(" ")}`.toLowerCase();
    return (!query || haystack.includes(query.toLowerCase())) && (source === "all" || skill.source === source) && (category === "all" || skill.category === category);
  });
  const sources = Array.from(new Set(skills.map((skill) => skill.source)));
  const categories = Array.from(new Set(skills.map((skill) => skill.category || "general"))).sort();
  const toggleSelected = (id: string) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  return (
    <section className="pageStack">
      <Panel title="技能库">
        <div className="explain"><Database size={18} /><span>技能是可审计的工作方法和提示模板；工具是实际执行能力。安装只登记版本与来源，是否绑定到 Agent 由你明确选择。</span></div>
        <div className="libraryToolbar">
          <label className="searchBox"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索技能、用途或工具" /></label>
          <select value={source} onChange={(event) => setSource(event.target.value)}><option value="all">全部来源</option>{sources.map((item) => <option value={item} key={item}>{item}</option>)}</select>
          <select value={category} onChange={(event) => setCategory(event.target.value)}><option value="all">全部领域</option>{categories.map((item) => <option value={item} key={item}>{item}</option>)}</select>
          <span className="muted">{filtered.length} 个结果</span>
          <button className="primaryButton" disabled={!selected.length} onClick={() => { registerSkillsBatch(skills.filter((skill) => selected.includes(skill.id))); setSelected([]); }}>批量登记 {selected.length || ""}</button>
        </div>
      </Panel>
      <Panel title="从 GitHub 批量发现 Skill">
        <div className="explain"><GitBranch size={18} /><span>输入公开仓库地址，平台只读取 Skill 描述文件，不执行仓库代码；扫描结果会锁定 commit、计算 hash，并标记风险后等待你登记。</span></div>
        <div className="githubImportForm">
          <input value={githubQuery} onChange={(event) => setGithubQuery(event.target.value)} placeholder="联网搜索 GitHub Skill，例如 ppt excel research" />
          <button className="secondaryButton" disabled={searchingGithub} onClick={async () => { setSearchingGithub(true); try { setGithubResults(await searchGitHubSkills(githubQuery)); } finally { setSearchingGithub(false); } }}><Search size={15} />{searchingGithub ? "搜索中..." : "搜索公开 Skill"}</button>
        </div>
        {githubResults.length > 0 && <div className="githubSearchResults">{githubResults.map((item) => <button className="githubResult" key={item.repository} onClick={() => { setGithubUrl(item.url); setGithubRef(item.default_branch); }}><strong>{item.repository}</strong><span>{item.path || "SKILL.md"} · ★ {item.stars}</span><small>{item.description || "无仓库描述"}</small></button>)}</div>}
        <div className="githubImportForm">
          <input value={githubUrl} onChange={(event) => setGithubUrl(event.target.value)} placeholder="https://github.com/owner/repository" />
          <input value={githubRef} onChange={(event) => setGithubRef(event.target.value)} placeholder="可选：branch / tag / commit" />
          <input value={githubSubpath} onChange={(event) => setGithubSubpath(event.target.value)} placeholder="可选：仓库子目录" />
          <button className="primaryButton" disabled={!githubUrl.trim() || scanning} onClick={async () => { setScanning(true); try { setGithubCandidates(await scanGitHubSkills(githubUrl, githubRef, githubSubpath)); } finally { setScanning(false); } }}><Search size={15} />{scanning ? "扫描中..." : "扫描仓库"}</button>
        </div>
        {githubCandidates.length > 0 && <div className="importResults"><strong>本次发现 {githubCandidates.length} 个 Skill</strong><div className="skillGrid">{githubCandidates.map((skill) => <article className="skillCard" key={skill.id}><div className="skillCardHead"><div><strong>{skill.name}</strong><span>{skill.id}</span></div><Badge value={skill.scan_status === "passed" ? "scan passed" : "needs review"} /></div><p>{skill.description || "无描述"}</p><div className="skillMeta"><span>版本 {skill.version}</span><span>commit {skill.source_ref?.slice(0, 12) || "-"}</span><span>风险 {skill.risk_level}</span></div>{skill.scan_findings?.length ? <div className="scanFindings">{skill.scan_findings.join("；")}</div> : null}<div className="skillCardActions"><a href={skill.source_url ?? undefined} target="_blank" rel="noreferrer">查看来源</a><button className="primaryButton" onClick={() => registerSkill(skill)}>登记到平台</button></div></article>)}</div></div>}
      </Panel>
      <div className="skillGrid">
        {filtered.map((skill) => (
          <article className={`skillCard ${skill.installed ? "installed" : ""}`} key={skill.id}>
            <div className="skillCardHead"><label className="skillSelect"><input type="checkbox" checked={selected.includes(skill.id)} onChange={() => toggleSelected(skill.id)} disabled={skill.installed} /></label><div><strong>{skill.name}</strong><span>{skill.id}</span></div><Badge value={skill.installed ? "installed" : skill.trust_level} /></div>
            <p>{skill.description}</p>
            <div className="skillMeta"><span>版本 {skill.version}</span><span>来源 {skill.source}</span><span>领域 {skill.category || "general"}</span><span>风险 {skill.risk_level}</span></div>
            <div className="chipGroup">{skill.recommended_tools.map((tool) => <span className="miniChip" key={tool}>{tool}</span>)}</div>
            <div className="chipGroup">{(skill.tags || []).map((tag) => <span className="miniChip secondary" key={tag}>#{tag}</span>)}</div>
            <div className="skillCardActions">
              {skill.source_url && <a href={skill.source_url} target="_blank" rel="noreferrer">查看来源</a>}
              <button className={skill.installed ? "" : "primaryButton"} disabled={skill.installed} onClick={() => registerSkill(skill)}>{skill.installed ? "已登记" : "登记到平台"}</button>
            </div>
          </article>
        ))}
        {!filtered.length && <p className="emptyState">没有匹配的技能。可以先调整搜索词，后续再接 Git 仓库导入。</p>}
      </div>
    </section>
  );
}

function ToolsPage({ tools, registerTool }: { tools: ToolSpec[]; registerTool: (tool: ToolSpec) => void }) {
  const [form, setForm] = useState<ToolSpec>({
    id: "custom_http_lookup",
    name: "自定义 HTTP 查询",
    description: "通过受限域名发起 GET 请求，返回文本内容。",
    category: "network",
    executor: "http_get",
    risk_level: "medium",
    sandbox: null,
    requires_approval: false,
    allowed_domains: ["example.com"],
    input_schema: {
      type: "object",
      properties: {
        url: { type: "string", description: "完整 URL，域名必须在 allowed_domains 内" }
      },
      required: ["url"]
    }
  });
  const [schemaText, setSchemaText] = useState<string>(JSON.stringify(form.input_schema, null, 2));
  const [domainsText, setDomainsText] = useState<string>((form.allowed_domains ?? []).join(", "));
  const [query, setQuery] = useState("");

  function update<K extends keyof ToolSpec>(key: K, value: ToolSpec[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function submit() {
    const inputSchema = JSON.parse(schemaText || "{}") as Record<string, unknown>;
    registerTool({
      ...form,
      input_schema: inputSchema,
      allowed_domains: domainsText.split(",").map((item) => item.trim()).filter(Boolean)
    });
  }

  return (
    <section className="pageStack">
      <Panel title="工具注册">
        <div className="explain"><Wrench size={18} /><span>这里注册的是可被模型结构化调用的 ToolSpec。Agent 只有在配置中心被授予该工具后，运行时才能调用。</span></div>
        <div className="formGrid">
          <label>工具 ID</label><input value={form.id} onChange={(event) => update("id", event.target.value)} />
          <label>名称</label><input value={form.name} onChange={(event) => update("name", event.target.value)} />
          <label>描述</label><textarea value={form.description} onChange={(event) => update("description", event.target.value)} />
          <label>类别</label>
          <select value={form.category} onChange={(event) => update("category", event.target.value)}>
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="command">command</option>
            <option value="network">network</option>
            <option value="mcp">mcp</option>
          </select>
          <label>执行器</label>
          <select value={form.executor} onChange={(event) => update("executor", event.target.value)}>
            <option value="http_get">http_get</option>
            <option value="weather_lookup">weather_lookup</option>
            <option value="file_read">file_read</option>
            <option value="file_write">file_write</option>
            <option value="local_command">local_command</option>
            <option value="repo_search">repo_search</option>
            <option value="repo_read">repo_read</option>
            <option value="repo_list">repo_list</option>
          </select>
          <label>风险等级</label>
          <select value={form.risk_level} onChange={(event) => update("risk_level", event.target.value)}>
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
          <label>允许域名</label><input value={domainsText} onChange={(event) => setDomainsText(event.target.value)} placeholder="example.com, api.example.com" />
          <label className="checkLine"><input type="checkbox" checked={form.requires_approval} onChange={(event) => update("requires_approval", event.target.checked)} />需要人工审批</label>
          <label>输入 Schema</label><textarea value={schemaText} onChange={(event) => setSchemaText(event.target.value)} spellCheck={false} />
        </div>
        <div className="panelToolbar"><button className="primaryButton" onClick={submit}><Wrench size={16} />注册工具</button></div>
      </Panel>
      <Panel title="已注册工具">
        <div className="libraryToolbar"><label className="searchBox"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索工具、执行器或风险等级" /></label><span className="muted">{tools.filter((tool) => `${tool.id} ${tool.name} ${tool.executor} ${tool.category}`.toLowerCase().includes(query.toLowerCase())).length} 个结果</span></div>
        <div className="toolGrid">
          {tools.filter((tool) => `${tool.id} ${tool.name} ${tool.executor} ${tool.category}`.toLowerCase().includes(query.toLowerCase())).map((tool) => (
            <article className="toolCard" key={tool.id}>
              <div className="agentHead"><Wrench size={18} /><strong>{displayText(tool.name || tool.id)}</strong><Badge value={tool.source || "builtin"} /></div>
              <span>ID：{tool.id}</span>
              <span>执行器：{tool.executor}</span>
              <span>类别：{tool.category} / 风险：{tool.risk_level}</span>
              <span>沙箱：{tool.sandbox || "-"}</span>
              <p className="muted">{displayText(tool.description)}</p>
              <pre>{JSON.stringify(cleanJson(tool.input_schema ?? {}), null, 2)}</pre>
            </article>
          ))}
        </div>
      </Panel>
    </section>
  );
}

function KnowledgeComposer({
  sources,
  setSources,
  policy,
  setPolicy
}: {
  sources: KnowledgeSourceInput[];
  setSources: (sources: KnowledgeSourceInput[]) => void;
  policy: Record<string, unknown>;
  setPolicy: (policy: Record<string, unknown>) => void;
}) {
  function addSource() {
    setSources([...sources, { name: `Session 知识 ${sources.length + 1}`, source_type: "session_note", content: "", required_citation: true }]);
  }
  function updateSource(index: number, patch: Partial<KnowledgeSourceInput>) {
    setSources(sources.map((source, itemIndex) => itemIndex === index ? { ...source, ...patch } : source));
  }
  return (
    <Panel title="Session 知识范围">
      <div className="knowledgeIntro"><BookOpen size={18} /><span>只配置本次 Session 可以使用的知识。Leader 会在规划阶段为每个 Agent 生成访问计划，平台会在执行前再次校验。</span></div>
      <div className="knowledgeComposer">
        <div className="knowledgeSourceList">
          {sources.map((source, index) => (
            <article className="knowledgeSourceRow" key={`${index}-${source.name}`}>
              <div className="knowledgeSourceFields">
                <input value={source.name} onChange={(event) => updateSource(index, { name: event.target.value })} placeholder="来源名称" />
                <select value={source.source_type} onChange={(event) => updateSource(index, { source_type: event.target.value })}>
                  <option value="session_note">Session 备注</option>
                  <option value="text">文本资料</option>
                  <option value="uploaded_file">文件元数据</option>
                  <option value="path">本地路径</option>
                </select>
                <textarea value={source.content} onChange={(event) => updateSource(index, { content: event.target.value })} placeholder="粘贴需求、约束、接口说明或验收标准" />
                <input value={source.locator ?? ""} onChange={(event) => updateSource(index, { locator: event.target.value })} placeholder="可选：文件路径、URL 或外部引用" />
              </div>
              <div className="knowledgeSourceMeta">
                <label className="checkLine"><input type="checkbox" checked={source.required_citation} onChange={(event) => updateSource(index, { required_citation: event.target.checked })} />该来源必须引用</label>
                <button className="iconButton" type="button" title="移除知识源" onClick={() => setSources(sources.filter((_, itemIndex) => itemIndex !== index))}><X size={15} /></button>
              </div>
            </article>
          ))}
          {!sources.length && <div className="knowledgeEmpty">尚未添加 Session 知识。可以先用任务输入启动，后续再补充来源。</div>}
        </div>
        <div className="knowledgeControls">
          <button type="button" onClick={addSource}><Plus size={15} />添加知识源</button>
          <label className="checkLine"><input type="checkbox" checked={Boolean(policy.allow_agent_search)} onChange={(event) => setPolicy({ ...policy, allow_agent_search: event.target.checked })} />允许 Agent 检索</label>
          <label className="checkLine"><input type="checkbox" checked={Boolean(policy.require_citation)} onChange={(event) => setPolicy({ ...policy, require_citation: event.target.checked })} />强制事实引用</label>
          <label className="checkLine"><input type="checkbox" checked={Boolean(policy.allow_upstream_artifacts)} onChange={(event) => setPolicy({ ...policy, allow_upstream_artifacts: event.target.checked })} />允许使用上游产物</label>
        </div>
      </div>
      <div className="contextPreview"><strong>访问范围预览</strong><span>{sources.length} 个 Session 来源</span><span>{policy.allow_agent_search ? "允许 Agent 检索" : "仅加载 Leader 授权上下文"}</span><span>{policy.require_citation ? "要求引用来源" : "引用由 Agent 自行决定"}</span><em>Agent 级授权将在规划阶段生成</em></div>
    </Panel>
  );
}

function LeaderTaskPage({
  agents,
  skills,
  recommendTask,
  dispatchLeaderTask
}: {
  agents: Agent[];
  skills: SkillSpec[];
  recommendTask: (task: string) => Promise<TaskRecommendation>;
  dispatchLeaderTask: (leaderId: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>, requestedSkills: string[], requestedTools: string[]) => Promise<void>;
}) {
  const [leaderId, setLeaderId] = useState(agents[0]?.id ?? "");
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [operationError, setOperationError] = useState("");
  const [knowledgeSources, setKnowledgeSources] = useState<KnowledgeSourceInput[]>([]);
  const [knowledgePolicy, setKnowledgePolicy] = useState<Record<string, unknown>>({ allow_agent_search: true, require_citation: true, allow_upstream_artifacts: true });
  const [recommendation, setRecommendation] = useState<TaskRecommendation | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => { if (!leaderId && agents[0]?.id) setLeaderId(agents[0].id); }, [agents, leaderId]);

  async function analyze() {
    if (!objective.trim()) return;
    setAnalyzing(true); setOperationError("");
    try {
      const result = await recommendTask(objective.trim());
      setRecommendation(result);
      setSelectedSkills(result.skills.filter((skill) => skill.installed).map((skill) => skill.id));
      setSelectedTools(result.recommended_tools);
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : String(error));
    } finally {
      setAnalyzing(false);
    }
  }

  async function submit() {
    if (submitting || !leaderId || !objective.trim()) return;
    setSubmitting(true); setOperationError("");
    try {
      await dispatchLeaderTask(leaderId, title.trim() || objective.trim().slice(0, 40), objective.trim(), false, knowledgeSources, knowledgePolicy, selectedSkills, selectedTools);
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  }

  function toggle(current: string[], value: string) {
    return current.includes(value) ? current.filter((item) => item !== value) : [...current, value];
  }

  return (
    <section className="pageStack leaderTaskPage">
      <section>
        <Panel title="新任务">
          <div className="leaderForm">
            <label>最终目标<textarea value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="你希望完成什么？需要什么交付物？有哪些必须保留或避免的内容？" /></label>
            <label>任务名称（可选）<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="留空则使用目标作为名称" /></label>
          </div>
        </Panel>
      </section>
      <details className="leaderAdvanced">
        <summary>本次资料与引用{knowledgeSources.length ? ` · ${knowledgeSources.length} 项` : "（可选）"}</summary>
        <KnowledgeComposer sources={knowledgeSources} setSources={setKnowledgeSources} policy={knowledgePolicy} setPolicy={setKnowledgePolicy} />
      </details>
      <details className="leaderAdvanced">
        <summary>高级设置 · Leader 与能力偏好</summary>
        <div className="leaderForm">
          <label>负责 Leader<select value={leaderId} onChange={(event) => setLeaderId(event.target.value)}>{agents.map((agent) => <option value={agent.id} key={agent.id}>{displayText(agent.name)} · {agent.id}</option>)}</select></label>
          <div className="leaderFormActions"><button type="button" onClick={analyze} disabled={!objective.trim() || analyzing}><Search size={15} />{analyzing ? "分析中..." : "查看能力建议"}</button></div>
        </div>
        <Panel title="能力偏好">
          {!recommendation ? <p className="muted">尚未指定能力偏好</p> : (
            <div className="leaderPreflight">
              <div className="preflightSignals"><Signal label="能力" value={recommendation.required_capabilities.length || "待识别"} /><Signal label="工具" value={recommendation.recommended_tools.length || "待识别"} /><Signal label="预期产物" value={recommendation.expected_artifacts.length || "待识别"} /></div>
              {recommendation.risk_hints.length > 0 && <div className="riskNotice"><ShieldAlert size={16} /><span>{recommendation.risk_hints.join("；")}</span></div>}
              <div className="capabilitySelection">
                <strong>本次允许 Leader 申请的能力</strong>
                {recommendation.skills.map((skill) => <label key={skill.id}><input type="checkbox" checked={selectedSkills.includes(skill.id)} onChange={() => setSelectedSkills(toggle(selectedSkills, skill.id))} /><span><b>{skill.name}</b><small>{skill.installed ? "已登记，可进入 Session 授权" : "未登记，需要先进入能力中心审核"}</small></span><Badge value={skill.installed ? "已登记" : "候选"} /></label>)}
                {!recommendation.skills.length && <p className="muted">暂未匹配到已登记 Skill，Leader 仍可以使用现有能力，并在 Session 中提出能力缺口。</p>}
              </div>
              {recommendation.recommended_tools.length > 0 && <div className="toolIntent"><strong>推荐 Tool</strong><span>{recommendation.recommended_tools.join(" · ")}</span></div>}
            </div>
          )}
        </Panel>
      </details>

      <section className="leaderLaunchBar">
        <div><strong>{agents.find((agent) => agent.id === leaderId)?.name ?? "Leader"}</strong><span>先确认方案，再授权执行</span></div>
        <button className="primaryButton" disabled={submitting || analyzing || !leaderId || !objective.trim()} onClick={submit}><Send size={16} />{submitting ? "正在创建..." : "交给 Leader"}</button>
      </section>
      {operationError && <p role="alert" className="learningError">{operationError}</p>}
    </section>
  );
}

function KnowledgeCenterPage({
  sessions,
  selectedSessionId,
  detail,
  setSelectedSessionId,
  openSession
}: {
  sessions: Session[];
  selectedSessionId: string | null;
  detail: SessionDetail | null;
  setSelectedSessionId: (id: string) => void;
  openSession: (id: string) => void;
}) {
  const [view, setView] = useState("sources");
  const sources = detail?.knowledge_sources ?? [];
  const grants = detail?.knowledge_grants ?? [];
  const accessEvents = detail?.knowledge_access_events ?? [];
  return (
    <section className="pageStack">
      <div className="pageTabs" role="tablist" aria-label="知识类别"><button role="tab" aria-selected={view === "sources"} className={view === "sources" ? "active" : ""} onClick={() => setView("sources")}><FileText size={15} />任务资料</button><button role="tab" aria-selected={view === "cases"} className={view === "cases" ? "active" : ""} onClick={() => setView("cases")}><BookOpen size={15} />历史案例</button></div>
      {view === "cases" ? <CaseLibrary ownerId={detail?.session?.owner_id ?? "operator"} openSession={openSession} /> : <>
      <Panel title="知识范围">
        <div className="knowledgeCenterHeader">
          <div><strong>Session 知识优先</strong><p>用户在创建任务时添加资料，Leader 再为每个 Agent 生成最小访问计划。知识是依据，不是 Skill。</p></div>
          <select value={selectedSessionId ?? ""} onChange={(event) => setSelectedSessionId(event.target.value)}>{sessions.map((session) => <option value={session.id} key={session.id}>{displayText(session.title)} · {session.status}</option>)}</select>
        </div>
        <div className="knowledgeScopeGrid"><article><span>当前 Session 来源</span><strong>{sources.length}</strong><small>本次任务可用的资料</small></article><article><span>Leader 访问计划</span><strong>{grants.length}</strong><small>按 Agent 和 Run 授权</small></article><article><span>引用访问</span><strong>{accessEvents.length}</strong><small>允许与拒绝都有记录</small></article></div>
      </Panel>
      <section className="grid">
        <Panel title="Session 来源">
          {sources.length ? <div className="knowledgeCenterList">{sources.map((source) => {
            const accesses = accessEvents.filter((event) => event.source_id === source.id);
            return <article key={source.id}><div><strong>{displayText(source.name)}</strong><span>{source.source_type} · {source.trust_level}</span></div><Badge value={source.required_citation ? "需要引用" : "可选引用"} /><small>{accesses.length ? `已访问 ${accesses.length} 次` : "尚未访问"}</small></article>;
          })}</div> : <p className="emptyState">当前 Session 还没有添加知识来源。创建任务时可以添加说明、文件路径或项目资料。</p>}
        </Panel>
        <Panel title="Agent 访问计划">
{grants.length ? <div className="knowledgeCenterList">{grants.map((grant) => <article key={String(grant.id)}><div><strong>{displayText(String(grant.agent_id ?? "Agent"))}</strong><span>{String(grant.access_mode ?? "read")} · {String(grant.granted_by ?? "Leader")}</span></div><strong>{Array.isArray(grant.source_ids) ? grant.source_ids.length : 0} 个来源</strong><small>{displayText(String(grant.rationale ?? "Leader 规划授权"))}</small></article>)}</div> : <p className="emptyState">Leader 生成计划后，这里会显示每个 Agent 的知识访问范围。</p>}
        </Panel>
      </section>
      <Panel title="最近访问事件">
        {accessEvents.length ? <div className="eventTable">{accessEvents.slice(-12).reverse().map((event) => <div key={String(event.id)}><span>{String(event.agent_id ?? "agent")}</span><span>{String(event.action ?? "access")}</span><span>{String(event.decision ?? "-")}</span><em>{String(event.reason ?? "")}</em></div>)}</div> : <p className="emptyState">暂无知识访问记录。</p>}
      </Panel>
      </>}
    </section>
  );
}

function EvolutionLabPage() {
  const [operationError, setOperationError] = useState("");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<{ candidates: Array<Record<string, unknown>>; counts: Record<string, number>; pipeline: string[] } | null>(null);
  async function refreshEvolution() { setData(await getJson<typeof data>("/dashboard/evolution")); }
  useEffect(() => { refreshEvolution().catch(error => setOperationError(String(error))); }, []);
  async function decide(candidateId: string, status: string) {
    setBusy(true); setOperationError("");
    try {
      await postJson(`/dashboard/evolution/candidates/${candidateId}/decision`, { status, reason: `operator ${status}` });
      await refreshEvolution();
    } catch (error) { setOperationError(String(error)); } finally { setBusy(false); }
  }
  const candidates = data?.candidates ?? [];
  return (
    <section className="pageStack">
      <Panel title="受控进化流水线">
        <div className="evolutionIntro"><Activity size={20} /><div><strong>经验不会直接改写系统</strong><p>每个候选都必须保留来源和证据，经过评估与人工审批后，才允许成为新的 Agent、Skill、策略或协作方案版本。</p></div></div>
        <div className="evolutionPipeline">{(data?.pipeline ?? ["候选", "证据复核", "评测", "人工审批", "版本发布", "可回滚"]).map((stage, index) => <span key={stage}><b>{index + 1}</b>{stage}</span>)}</div>
        <div className="evolutionCounts">{Object.entries(data?.counts ?? {}).map(([key, value]) => <Signal key={key} label={key} value={value} />)}</div>
      </Panel>
      <Panel title="经验候选">
        {operationError && <p role="alert">{operationError}</p>}
        <p className="muted">评测与版本发布待接通 · 当前候选不会改变运行配置</p>
        {candidates.length ? <div className="evolutionList">{candidates.map((candidate) => <article key={String(candidate.id)}><div><strong>{displayText(String(candidate.summary ?? "未命名经验"))}</strong><small>来源案例：{String(candidate.source_case_id ?? "历史候选，尚未关联案例")} · 类型：{String(candidate.target_type ?? "待分类")}</small><details><summary>证据引用</summary><pre className="candidateEvidence">{JSON.stringify(candidate.evidence_refs ?? [], null, 2)}</pre></details></div><div className="evolutionActions"><Badge value={String(candidate.status ?? "pending")} />{candidate.status === "pending" && <button disabled={busy} onClick={() => decide(String(candidate.id), "rejected")}><X size={14} />拒绝</button>}</div></article>)}</div> : <p className="emptyState">暂无候选。</p>}
      </Panel>
    </section>
  );
}

function DispatchPage({
  agents,
  teams,
  skills,
  latestMatching,
  dispatchTask,
  dispatchTeamTask,
  dispatchAdHocTeamTask,
  recommendTask,
  runStoryDemo
}: {
  agents: Agent[];
  teams: TeamConfig[];
  skills: SkillSpec[];
  latestMatching: MatchingReport | null;
  dispatchTask: (agentId: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>) => void;
  dispatchTeamTask: (teamId: string, strategy: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>) => void;
  dispatchAdHocTeamTask: (leader: string, members: string[], strategy: string, title: string, inputSummary: string, executeNow: boolean, knowledgeSources: KnowledgeSourceInput[], knowledgePolicy: Record<string, unknown>) => void;
  recommendTask: (task: string) => Promise<TaskRecommendation>;
  runStoryDemo: () => void;
}) {
  const [agentId, setAgentId] = useState<string>(agents[0]?.id ?? "");
  const [teamId, setTeamId] = useState<string>(teams[0]?.id ?? "");
  const [leaderId, setLeaderId] = useState<string>(agents[0]?.id ?? "");
  const [selectedMembers, setSelectedMembers] = useState<string[]>(agents.slice(0, 2).map((agent) => agent.id));
  const [title, setTitle] = useState<string>("代码治理审计任务");
  const [teamTitle, setTeamTitle] = useState<string>("多 Agent 协作治理任务");
  const [adHocTitle, setAdHocTitle] = useState<string>("临时多 Agent 协作任务");
  const [input, setInput] = useState<string>("分析当前仓库的 Agent 运行链路，找出一个审计或工具调用治理风险，并给出可追踪建议。");
  const [teamInput, setTeamInput] = useState<string>("围绕当前平台设计一次多 Agent 治理评审：证据收集、执行验证、策略审计、最终评审都要有独立输出。");
  const [adHocInput, setAdHocInput] = useState<string>("请由多个 Agent 协作完成：先拆分任务，再分别输出证据、执行结果和最终评审。");
  const [strategy, setStrategy] = useState<string>(teams[0]?.collaboration_strategy ?? "leader_worker");
  const [adHocStrategy, setAdHocStrategy] = useState<string>("leader_worker");
  const [executeNow, setExecuteNow] = useState<boolean>(true);
  const [teamExecuteNow, setTeamExecuteNow] = useState<boolean>(false);
  const [adHocExecuteNow, setAdHocExecuteNow] = useState<boolean>(false);
  const [launchMode, setLaunchMode] = useState<"team" | "adhoc" | "single">("team");
  const [knowledgeSources, setKnowledgeSources] = useState<KnowledgeSourceInput[]>([]);
  const [knowledgePolicy, setKnowledgePolicy] = useState<Record<string, unknown>>({ allow_agent_search: true, require_citation: true, allow_upstream_artifacts: true });
  const [taskBrief, setTaskBrief] = useState<string>("");
  const [recommendation, setRecommendation] = useState<TaskRecommendation | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  useEffect(() => { if (!agentId && agents[0]?.id) setAgentId(agents[0].id); }, [agents, agentId]);
  useEffect(() => {
    if (!leaderId && agents[0]?.id) setLeaderId(agents[0].id);
    if (!selectedMembers.length && agents.length >= 2) setSelectedMembers(agents.slice(0, 2).map((agent) => agent.id));
  }, [agents, leaderId, selectedMembers.length]);
  useEffect(() => {
    if (!teamId && teams[0]?.id) {
      setTeamId(teams[0].id);
      setStrategy(teams[0].collaboration_strategy);
    }
  }, [teams, teamId]);

  function toggleMember(agent: Agent) {
    setSelectedMembers((current) => {
      const exists = current.includes(agent.id);
      const next = exists ? current.filter((id) => id !== agent.id) : [...current, agent.id];
      if (!next.includes(leaderId) && agent.id === leaderId) setLeaderId(next[0] ?? "");
      return next;
    });
  }

  async function analyzeTask() {
    if (!taskBrief.trim()) return;
    setAnalyzing(true);
    try {
      setRecommendation(await recommendTask(taskBrief));
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <section className="pageStack">
      <Panel title="启动向导">
        <div className="stepper">
          <span className="active">1 选择模式</span>
          <span className="active">2 配置治理约束</span>
          <span>3 预检并启动</span>
        </div>
        <div className="modeGrid">
          <button className={launchMode === "team" ? "modeCard active" : "modeCard"} onClick={() => setLaunchMode("team")} type="button">
            <GitBranch size={20} />
            <strong>预定义 Team</strong>
            <span>推荐。复用稳定的 Agent 分工和协作策略。</span>
          </button>
          <button className={launchMode === "adhoc" ? "modeCard active" : "modeCard"} onClick={() => setLaunchMode("adhoc")} type="button">
            <Bot size={20} />
            <strong>临时组队</strong>
            <span>快速挑选多个 Agent，创建一次性协作 Session。</span>
          </button>
          <button className={launchMode === "single" ? "modeCard active" : "modeCard"} onClick={() => setLaunchMode("single")} type="button">
            <Wrench size={20} />
            <strong>单 Agent</strong>
            <span>适合调试、冒烟测试和简单审计任务。</span>
          </button>
        </div>
      </Panel>

      <Panel title="任务意图与能力预检">
        <div className="taskIntentIntro"><Activity size={18} /><span>先描述最终目标，系统会匹配 Skill、Tool、角色和风险。推荐结果只用于预览，不会自动授权或执行。</span></div>
        <div className="taskIntentComposer">
          <textarea value={taskBrief} onChange={(event) => setTaskBrief(event.target.value)} placeholder="例如：分析这个仓库的治理风险，输出一份带证据的 Excel 和架构图" />
          <button className="primaryButton" type="button" disabled={!taskBrief.trim() || analyzing} onClick={analyzeTask}><Search size={15} />{analyzing ? "分析中..." : "分析任务"}</button>
        </div>
        {recommendation && <div className="taskRecommendation">
          <div className="recommendationSignals">
            <span>需要能力：{recommendation.required_capabilities.length || "暂未识别"}</span>
            <span>推荐工具：{recommendation.recommended_tools.length || "暂未识别"}</span>
            <span>预计产物：{recommendation.expected_artifacts.length || "待确认"}</span>
            {recommendation.risk_hints.map((risk) => <strong key={risk}>风险：{risk}</strong>)}
          </div>
          <div className="recommendationCards">{recommendation.skills.map((skill) => <article className="recommendationCard" key={skill.id}><div><strong>{skill.name}</strong><span>{skill.category || "general"} · 匹配 {skill.score}</span></div><Badge value={skill.installed ? "已登记" : "需先登记"} /><small>{skill.recommended_tools.join(" · ") || "无额外工具"}</small></article>)}</div>
          {!recommendation.skills.length && <p className="emptyState">暂未找到高匹配 Skill，可以继续使用当前 Agent 配置，或先去技能库导入能力。</p>}
        </div>}
      </Panel>

      <KnowledgeComposer sources={knowledgeSources} setSources={setKnowledgeSources} policy={knowledgePolicy} setPolicy={setKnowledgePolicy} />

      {launchMode === "team" && (
        <section className="grid">
          <Panel title="按 Team 模板启动">
            <div className="formGrid">
              <label>目标 Team</label>
              <select value={teamId} onChange={(event) => {
                const nextTeam = teams.find((team) => team.id === event.target.value);
                setTeamId(event.target.value);
                setStrategy(nextTeam?.collaboration_strategy ?? "leader_worker");
              }}>
                {!teams.length && <option value="">未配置 Team</option>}
                {teams.map((team) => <option value={team.id} key={team.id}>{team.id} ({team.leader})</option>)}
              </select>
              <label>协作策略</label>
              <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
                <option value="leader_worker">leader_worker</option>
                <option value="sequential_artifact_review">sequential_artifact_review</option>
                <option value="parallel_review">parallel_review</option>
                <option value="planner_executor_reviewer">planner_executor_reviewer</option>
              </select>
              <label>任务标题</label><input value={teamTitle} onChange={(event) => setTeamTitle(event.target.value)} />
              <label>任务输入</label><textarea value={teamInput} onChange={(event) => setTeamInput(event.target.value)} />
              <label className="checkLine"><input type="checkbox" checked={teamExecuteNow} onChange={(event) => setTeamExecuteNow(event.target.checked)} />创建后立即执行全部 Run</label>
            </div>
            <div className="panelToolbar">
              <button className="primaryButton" disabled={!teamId} onClick={() => dispatchTeamTask(teamId, strategy, teamTitle, taskBrief.trim() || teamInput, teamExecuteNow, knowledgeSources, knowledgePolicy)}><GitBranch size={16} />创建 Team Session</button>
              <button onClick={runStoryDemo}><Play size={16} />运行故事示例</button>
            </div>
          </Panel>
          <LaunchReadiness mode="team" agentCount={teams.find((team) => team.id === teamId)?.members.length ?? 0} strategy={strategy} executeNow={teamExecuteNow} />
        </section>
      )}

      {launchMode === "adhoc" && (
        <section className="grid">
          <Panel title="临时选择多个 Agent 组队">
            <div className="agentPicker">
              {agents.map((agent) => {
                const checked = selectedMembers.includes(agent.id);
                return (
                  <button type="button" className={checked ? "agentPick selected" : "agentPick"} key={agent.id} onClick={() => toggleMember(agent)}>
                    <strong>{displayText(agent.name)}</strong>
                    <span>{agent.id}</span>
                    <em>{agent.tools?.length ? agent.tools.join(", ") : "无工具"} / {agent.sandbox || "无沙箱"}</em>
                  </button>
                );
              })}
            </div>
            <div className="formGrid">
              <label>Leader</label>
              <select value={leaderId} onChange={(event) => {
                const nextLeader = event.target.value;
                setLeaderId(nextLeader);
                if (!selectedMembers.includes(nextLeader)) setSelectedMembers([nextLeader, ...selectedMembers]);
              }}>
                {selectedMembers.map((id) => <option value={id} key={id}>{id}</option>)}
              </select>
              <label>协作策略</label>
              <select value={adHocStrategy} onChange={(event) => setAdHocStrategy(event.target.value)}>
                <option value="leader_worker">leader_worker</option>
                <option value="sequential_artifact_review">sequential_artifact_review</option>
                <option value="parallel_review">parallel_review</option>
                <option value="planner_executor_reviewer">planner_executor_reviewer</option>
              </select>
              <label>任务标题</label><input value={adHocTitle} onChange={(event) => setAdHocTitle(event.target.value)} />
              <label>任务输入</label><textarea value={adHocInput} onChange={(event) => setAdHocInput(event.target.value)} />
              <label className="checkLine"><input type="checkbox" checked={adHocExecuteNow} onChange={(event) => setAdHocExecuteNow(event.target.checked)} />创建后立即执行全部 Run</label>
            </div>
            <div className="panelToolbar">
              <button className="primaryButton" disabled={selectedMembers.length < 2 || !leaderId} onClick={() => dispatchAdHocTeamTask(leaderId, selectedMembers, adHocStrategy, adHocTitle, taskBrief.trim() || adHocInput, adHocExecuteNow, knowledgeSources, knowledgePolicy)}>
                <GitBranch size={16} />创建临时 Team Session
              </button>
            </div>
          </Panel>
          <LaunchReadiness mode="adhoc" agentCount={selectedMembers.length} strategy={adHocStrategy} executeNow={adHocExecuteNow} />
        </section>
      )}

      {launchMode === "single" && (
        <section className="grid">
          <Panel title="发配单 Agent 任务">
            <div className="formGrid">
              <label>目标 Agent</label>
              <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>{agents.map((agent) => <option value={agent.id} key={agent.id}>{displayText(agent.name)} ({agent.id})</option>)}</select>
              <label>任务标题</label><input value={title} onChange={(event) => setTitle(event.target.value)} />
              <label>任务输入</label><textarea value={input} onChange={(event) => setInput(event.target.value)} />
              <label className="checkLine"><input type="checkbox" checked={executeNow} onChange={(event) => setExecuteNow(event.target.checked)} />创建后立即执行</label>
            </div>
            <div className="panelToolbar"><button className="primaryButton" onClick={() => dispatchTask(agentId, title, taskBrief.trim() || input, executeNow, knowledgeSources, knowledgePolicy)}><Send size={16} />发配任务</button></div>
          </Panel>
          <LaunchReadiness mode="single" agentCount={agentId ? 1 : 0} strategy="direct" executeNow={executeNow} />
        </section>
      )}

      {latestMatching && <Panel title="能力匹配结果"><MatchingReportView report={latestMatching} /></Panel>}
    </section>
  );
}

function SessionCockpitPage({
  sessions,
  selectedSessionId,
  setSelectedSessionId,
  detail,
  auditReport,
  availableActions,
  liveEvents,
  setSelectedRunId,
  setPage,
  controlSession,
  createCheckpoint,
  rollbackSession,
  saveTeamTemplate,
  agents,
  skills,
  tools,
  requestDelegation,
  decideDelegation,
  decideApproval,
  submitSessionFeedback,
  requestSessionReplan,
  decideSessionPlan
}: {
  sessions: Session[];
  selectedSessionId: string | null;
  setSelectedSessionId: (id: string) => void;
  detail: SessionDetail | null;
  auditReport: SessionAuditReport | null;
  availableActions: GovernanceAction[];
  liveEvents: AuditEvent[];
  setSelectedRunId: (id: string) => void;
  setPage: (page: PageKey) => void;
  controlSession: (sessionId: string, action: "pause" | "cancel" | "resume" | "execute-pending") => Promise<void>;
  createCheckpoint: (sessionId: string) => Promise<void>;
  rollbackSession: (sessionId: string, checkpointId: string) => Promise<void>;
  saveTeamTemplate: (sessionId: string) => void;
  agents: Agent[];
  skills: SkillSpec[];
  tools: ToolSpec[];
  requestDelegation: (sessionId: string, payload: Record<string, unknown>) => Promise<void>;
  decideDelegation: (delegationId: string, approved: boolean) => Promise<void>;
  decideApproval: (approval: Approval, approved: boolean) => Promise<void>;
  submitSessionFeedback: (sessionId: string, payload: Record<string, unknown>) => Promise<void>;
  requestSessionReplan: (sessionId: string) => Promise<void>;
  decideSessionPlan: (sessionId: string, approved: boolean) => Promise<void>;
}) {
  const report = detail?.matching_reports?.[0] as MatchingReport | undefined;
  const [view, setView] = useState("task");
  const [sessionQuery, setSessionQuery] = useState("");
  const [queueOpen, setQueueOpen] = useState(true);
  const [controlBusy, setControlBusy] = useState("");
  const [controlError, setControlError] = useState("");
  async function control(action: "pause" | "cancel" | "resume" | "execute-pending") {
    if (!detail?.session || (controlBusy && !["pause", "cancel"].includes(action))) return;
    setControlBusy(action); setControlError("");
    try { await controlSession(detail.session.id, action); }
    catch (error) { setControlError(error instanceof Error ? error.message : String(error)); }
    finally { setControlBusy(""); }
  }
  useEffect(() => { setView("task"); }, [selectedSessionId]);
  const events = liveEvents.length ? liveEvents : detail?.steps ?? [];
  const currentTaskRunIds = new Set((detail?.task_nodes ?? []).filter(node => node.status !== "superseded").map(node => String(node.run_id)));
  const operationalRuns = (detail?.runs ?? []).filter(run => run.run_type !== "leader_planning" && (!detail?.task_nodes?.length || currentTaskRunIds.has(run.id)));
  const failedRuns = operationalRuns.filter(run => run.status === "failed");
  const pendingRuns = operationalRuns.filter(run => ["pending", "queued", "awaiting_approval", "blocked", "paused"].includes(run.status));
  const completedRuns = operationalRuns.filter(run => run.status === "completed");
  const leaderState = (detail?.session?.metadata?.leader ?? {}) as LeaderState;
  const interventionCount = failedRuns.length + (detail?.approvals ?? []).filter(a => a.status === "pending").length + (detail?.plans ?? []).filter(p => p.status === "awaiting_approval").length + (leaderState.questions?.length ?? 0) + (leaderState.unresolved_gaps?.length ?? 0) + (leaderState.status === "planning_failed" ? 1 : 0);
  const phase = sessionPhase(detail?.session?.status ?? "", failedRuns.length, pendingRuns.length);
  const actionById = new Map(availableActions.map((action) => [action.id, action]));
  const actionEnabled = (id: string) => actionById.get(id)?.enabled ?? true;
  const actionTitle = (id: string) => actionById.get(id)?.disabled_reason || actionById.get(id)?.label || "";
  const [selectedCheckpointId, setSelectedCheckpointId] = useState("");
  const auditSummary = auditReport?.summary ?? {};
  const budgetCost = detail?.budget_ledger.reduce((sum, item) => sum + Number(item.amount_usd ?? 0), 0) ?? 0;
  const evidenceRows = [
    ...(auditReport?.artifact_chain ?? detail?.artifacts ?? []),
    ...(detail?.evidence_refs ?? [])
  ];
  const decisionRows = auditReport?.decision_chain ?? [];
  return (
    <section className={queueOpen ? "cockpitLayout" : "cockpitLayout queueCollapsed"}>
      <div className="sessionQueueColumn"><button title={queueOpen ? "收起任务列表" : "展开任务列表"} aria-expanded={queueOpen} onClick={() => setQueueOpen(!queueOpen)}><PanelLeft size={16} />{queueOpen ? "收起列表" : "任务"}</button>
      {queueOpen && <Panel title="Session 队列">
        <input className="sessionSearch" aria-label="搜索 Session" placeholder="搜索任务" value={sessionQuery} onChange={e => setSessionQuery(e.target.value)} />
        <div className="sessionQueue">
          {sessions.filter(s => `${s.title} ${s.id}`.toLowerCase().includes(sessionQuery.toLowerCase())).map((session) => {
            const selected = selectedSessionId === session.id;
            const relatedRuns = detail?.session?.id === session.id ? detail.runs : [];
            return (
              <button className={selected ? "sessionQueueItem selected" : "sessionQueueItem"} key={session.id} onClick={() => setSelectedSessionId(session.id)}>
                <span><Badge value={session.status} />{formatTime(session.updated_at || session.created_at)}</span>
                <strong>{displayText(session.title)}</strong>
                <em>{session.team_id || session.root_agent_id || "未绑定执行主体"}{relatedRuns.length ? ` / ${relatedRuns.length} Runs` : ""}</em>
              </button>
            );
          })}
        </div>
      </Panel>}</div>
      <section className="cockpitWorkspace">
        {detail?.session ? (
          <>
            <section className="sessionHero">
              <div className="sessionHeroMain">
                <Badge value={detail.session.status} />
                <h2>{displayText(detail.session.title)}</h2>
                <p>{displayText(detail.session.context_summary || "暂无上下文摘要")}</p>
                <div className="phaseTrack">
                  {["规划", "执行", "审批", "产物", "复盘"].map((step, index) => (
                    <span className={index <= phase ? "active" : ""} key={step}>{step}</span>
                  ))}
                </div>
              </div>
              <div className="sessionHeroActions">
                <StatusPill icon={<AlertTriangle size={16} />} label="需要介入" value={interventionCount} tone={failedRuns.length || leaderState.status === "planning_failed" ? "danger" : interventionCount ? "warning" : "ok"} />
                <StatusPill icon={<WalletCards size={16} />} label="预算消耗" value={`$${budgetCost.toFixed(4)}`} tone="neutral" />
              </div>
            </section>
            <nav className="cockpitTabs" aria-label="任务视图">
              {[{ id: "task", label: "任务与 Leader", icon: <Bot size={16} /> }, { id: "collaboration", label: "协作现场", icon: <GitBranch size={16} /> }, { id: "artifacts", label: "交付与验收", icon: <FileText size={16} /> }, { id: "records", label: "记录与诊断", icon: <Activity size={16} /> }].map(tab => <button key={tab.id} aria-pressed={view === tab.id} className={view === tab.id ? "active" : ""} onClick={() => setView(tab.id)}>{tab.icon}{tab.label}</button>)}
            </nav>
            <section className="cockpitGrid">
              <section className="cockpitCenter">
                {view === "task" && <>
                  <div id="session-feedback"><SessionFeedbackPanel key={detail.session.id} detail={detail} submitFeedback={submitSessionFeedback} requestReplan={requestSessionReplan} decidePlan={decideSessionPlan} /></div>
                  <LeaderSkillDiscovery key={`skills-${detail.session.id}`} detail={detail} requestReplan={requestSessionReplan} submitFeedback={submitSessionFeedback} />
                  <Panel title="当前执行步骤"><TaskPlanView nodes={(detail.task_nodes ?? []).filter(n => n.status !== "superseded")} edges={detail.task_edges ?? []} setSelectedRunId={setSelectedRunId} setPage={setPage} /></Panel>
                  {detail.session.status === "completed" && <button className="primaryButton" onClick={() => setView("artifacts")}><FileText size={16} />查看交付并验收</button>}
                </>}
                {view === "artifacts" && <>
                  <SessionArtifacts key={`artifacts-${detail.session.id}`} detail={detail} submitFeedback={submitSessionFeedback} />
                  <SessionReviewPanel key={`review-${detail.session.id}`} sessionId={detail.session.id} revision={detail.session.updated_at} openSession={setSelectedSessionId} continueEditing={() => setView("task")} />
                  <Panel title="交付证据记录"><EvidenceChain artifacts={evidenceRows} decisions={[]} messages={[]} /></Panel>
                  <KnowledgeContextPanel detail={detail} />
                </>}
                {view === "collaboration" && <>
                  <Panel title="当前协作图"><SessionTopologyPanel sessionId={detail.session.id} revision={`${detail.session.updated_at}:${events.length}`} /></Panel>
                  <Panel title="Agent 通信"><MessageList rows={detail.messages} /></Panel>
                  <details className="advancedSession"><summary>成员与高级编排</summary><LeaderOrchestrationPanel detail={detail} agents={agents} skills={skills} tools={tools} requestDelegation={requestDelegation} decideDelegation={decideDelegation} /></details>
                </>}
                {failedRuns.length > 0 && <section className="sessionFailures" aria-label="执行异常">
                  <h3>执行异常</h3>
                  {failedRuns.map(run => <div key={run.id}><strong>{run.agent_id}</strong><p>{run.error || "执行失败，暂无详细原因"}</p><button onClick={() => { setSelectedRunId(run.id); setPage("runs"); }}><ArrowRight size={14} />查看详情与重试</button></div>)}
                </section>}
                {view === "records" && <><Panel title="执行态势">
                  <div className="signalGrid">
                    <Signal label="Session ID" value={shortId(detail.session.id)} />
                    <Signal label="执行主体" value={detail.session.team_id || detail.session.root_agent_id || "临时/单 Agent"} />
                    <Signal label="Run" value={detail.runs.length} />
                    <Signal label="事件" value={auditSummary.events ?? events.length} />
                    <Signal label="审批" value={auditSummary.approvals ?? 0} />
                    <Signal label="策略决策" value={auditSummary.policy_decisions ?? 0} />
                    <Signal label="模型调用" value={detail.model_calls.length} />
                    <Signal label="工具调用" value={detail.tool_calls.length} />
                    <Signal label="Artifact 版本" value={detail.artifact_versions?.length ?? 0} />
                  </div>
                  <section className="riskGrid">
                    <StatusPill icon={<AlertTriangle size={16} />} label="失败 Run" value={failedRuns.length} tone={failedRuns.length ? "danger" : "ok"} />
                    <StatusPill icon={<Clock size={16} />} label="待处理 Run" value={pendingRuns.length} tone={pendingRuns.length ? "warning" : "ok"} />
                    <StatusPill icon={<CheckCircle2 size={16} />} label="已完成 Run" value={completedRuns.length} tone="ok" />
                    <StatusPill icon={<FileText size={16} />} label="证据/产物" value={evidenceRows.length} tone="neutral" />
                  </section>
                </Panel>
                <MonitoringLayers detail={detail} events={events} auditSummary={auditSummary} />
                <section className="grid compactGrid">
                  <Panel title="本 Session 的 Run">
                    <RunTable runs={detail.runs} onSelect={(id) => { setSelectedRunId(id); setPage("runs"); }} compact />
                  </Panel>
                  <Panel title="实时事件流">
                    <Timeline events={events} />
                  </Panel>
                </section>
                <AuditReportPanel report={auditReport} />
                <Panel title="审计证据链"><EvidenceChain artifacts={evidenceRows} decisions={decisionRows} messages={detail.messages} /></Panel>
                </>}
              </section>
              <aside className="cockpitSide">
                <LeaderDecisionPanel key={detail.session.id} detail={detail} decidePlan={decideSessionPlan} decideDelegation={decideDelegation} decideApproval={decideApproval} />
                <Panel title="操作与介入">
                  <div className="controlStack">
                    <button className="primaryButton" disabled={!!controlBusy || !actionEnabled("execute-pending")} title={actionTitle("execute-pending")} onClick={() => control("execute-pending")}><Play size={15} />{controlBusy === "execute-pending" ? "执行中…" : "执行待处理"}</button>
                    <button disabled={controlBusy === "pause" || !actionEnabled("pause")} title={actionTitle("pause")} onClick={() => control("pause")}><PauseCircle size={15} />暂停</button>
                    <button disabled={!!controlBusy || !actionEnabled("resume")} title={actionTitle("resume")} onClick={() => control("resume")}><Play size={15} />恢复</button>
                    <button disabled={controlBusy === "cancel" || !actionEnabled("cancel")} title={actionTitle("cancel")} onClick={() => control("cancel")}><AlertTriangle size={15} />取消</button>
                  </div>
                  {controlError && <p role="alert" className="inlineError">{controlError}</p>}
                  <details className="advancedSession"><summary>检查点、回滚与模板</summary><div className="controlStack">
                    <button onClick={() => createCheckpoint(detail.session!.id)}><Plus size={15} />创建检查点</button>
                    <select className="checkpointSelect" value={selectedCheckpointId} onChange={(event) => setSelectedCheckpointId(event.target.value)} title="选择回滚目标">
                      <option value="">选择回滚目标</option>
                      {(detail.checkpoints ?? []).map((checkpoint) => <option value={String(checkpoint.id)} key={String(checkpoint.id)}>{String(checkpoint.label ?? checkpoint.id)} · {formatTime(String(checkpoint.created_at ?? ""))}</option>)}
                    </select>
                    <button disabled={!actionEnabled("rollback") || !selectedCheckpointId} title={actionTitle("rollback")} onClick={() => rollbackSession(detail.session!.id, selectedCheckpointId)}><Undo2 size={15} />回滚</button>
                    <button onClick={() => saveTeamTemplate(detail.session!.id)}><Bot size={15} />保存 Team 模板</button>
                  </div></details>
                  <h3>当前任务状态</h3>
                  <div className="recommendList">
                    {failedRuns.length > 0 && <span>优先打开失败 Run，定位错误、证据和可重试节点。</span>}
                    {pendingRuns.length > 0 && <span>执行待处理 Run 前检查审批、依赖和预算阈值。</span>}
                    {leaderState.status === "planning_failed" && <span>Leader 规划调用失败，需求与反馈已保存。查看错误后重试规划。</span>}
                    {!!leaderState.questions?.length && <span>Leader 需要补充信息，请在对话中回答。</span>}
                    {!!leaderState.unresolved_gaps?.length && <span>存在能力缺口，请查看搜索候选及运行条件，或与 Leader 调整方案。</span>}
                    {detail.session.status === "completed" && <span>执行已完成，请到交付与验收查看结果并确认。</span>}
                    {detail.session.status === "running" && <span>正在执行，可暂停或向 Leader 提交调整。</span>}
                  </div>
                </Panel>
                {view === "records" && <><RollbackPlan report={auditReport} actions={availableActions} />
                <Panel title="当前治理判断">
                  {report ? <MatchingReportView report={report} /> : <p>暂无匹配报告。</p>}
                </Panel></>}
              </aside>
            </section>
          </>
        ) : <Panel title="Session 驾驶舱"><p>请选择一个 Session。</p></Panel>}
      </section>
    </section>
  );
}

type ArtifactPreview = {
  kind: "text" | "image" | "download";
  content?: string;
  content_url?: string;
  truncated?: boolean;
  mime_type: string;
  size: number;
  filename: string;
};

function SessionArtifacts({ detail, submitFeedback }: {
  detail: SessionDetail;
  submitFeedback: (sessionId: string, payload: Record<string, unknown>) => Promise<void>;
}) {
  const [preview, setPreview] = useState<{ id: string; data: ArtifactPreview } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [feedbackId, setFeedbackId] = useState("");
  const [feedback, setFeedback] = useState("");
  const [result, setResult] = useState("");
  const sessionId = detail.session?.id ?? "";
  useEffect(() => { setPreview(null); setFeedbackId(""); setFeedback(""); setError(""); setResult(""); }, [sessionId]);
  const versions = detail.artifact_versions ?? [];
  const current = Array.from((detail.artifacts ?? []).reduce((byPath, item) => {
    const path = String(item.path);
    if (!byPath.has(path)) byPath.set(path, item);
    return byPath;
  }, new Map<string, Record<string, unknown>>()).values());

  async function openPreview(id: string) {
    setBusy(`preview:${id}`); setError("");
    try { setPreview({ id, data: await getJson<ArtifactPreview>(`/sessions/${sessionId}/artifacts/${id}/preview`) }); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(""); }
  }

  async function sendFeedback(artifact: Record<string, unknown>) {
    if (!feedback.trim()) return;
    const id = String(artifact.id);
    setBusy(`feedback:${id}`); setError(""); setResult("");
    try {
      await submitFeedback(sessionId, { target_type: "artifact", target_id: id, message: feedback.trim(),
        requested_action: "replan", created_by: "operator", reason_type: "preference" });
      setFeedback(""); setFeedbackId(""); setResult("反馈已保存并交给 Leader，请查看上方处理结果和最新方案。");
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(""); }
  }

  return <Panel title={`本次交付 · ${current.length}`}>
    <div className="artifactDelivery" aria-live="polite">
      {error && <p className="learningError" role="alert">{error}</p>}
      {result && <p className="artifactResult" role="status">{result}</p>}
      {!current.length && <p>任务还没有生成可交付文件。执行步骤完成后，产物会出现在这里。</p>}
      {current.map(artifact => {
        const id = String(artifact.id);
        const metadata = (artifact.metadata ?? {}) as Record<string, unknown>;
        const path = String(artifact.path ?? "");
        const pathVersions = versions.filter(item => String(item.path) === path);
        const stale = Boolean(metadata.stale);
        return <article className={stale ? "artifactItem stale" : "artifactItem"} key={id}>
          <header><span><FileText size={18} /><strong>{String(metadata.relative_path ?? path.split(/[\\/]/).pop() ?? "产物")}</strong></span><Badge value={stale ? "stale" : "ready"} /></header>
          <p>{String(artifact.summary ?? "Session 产物")}</p>
          <code title={path}>{path}</code>
          <small>由 {String(artifact.created_by_agent_id ?? "agent")} 生成 · {pathVersions.length || 1} 个版本记录 · {formatTime(String(artifact.created_at ?? ""))}</small>
          <div className="artifactActions">
            <button disabled={!!busy} onClick={() => openPreview(id)}><Eye size={14} />{busy === `preview:${id}` ? "读取中..." : "预览"}</button>
            <a className="buttonLink" href={`/sessions/${sessionId}/artifacts/${id}/download`} download><Download size={14} />下载</a>
            <button disabled={!!busy} onClick={() => { setFeedbackId(feedbackId === id ? "" : id); setFeedback(""); }}><Send size={14} />反馈给 Leader</button>
          </div>
          {preview?.id === id && <section className="artifactPreview">
            <header><strong>{preview.data.filename}</strong><small>{preview.data.mime_type} · {preview.data.size} bytes</small><button title="关闭预览" onClick={() => setPreview(null)}><X size={14} /></button></header>
            {preview.data.kind === "text" && <><pre>{preview.data.content}</pre>{preview.data.truncated && <small>这里只显示前 100,000 个字符，请下载查看完整内容。</small>}</>}
            {preview.data.kind === "image" && <img src={preview.data.content_url} alt={preview.data.filename} />}
            {preview.data.kind === "download" && <p>该文件类型不在网页内直接打开，请下载后查看。</p>}
          </section>}
          {feedbackId === id && <section className="artifactFeedback"><textarea aria-label={`对 ${String(metadata.relative_path ?? path)} 的反馈`} rows={3} value={feedback} onChange={e => setFeedback(e.target.value)} placeholder="说明要保留什么、调整什么，以及验收标准" /><button className="primaryButton" disabled={!feedback.trim() || !!busy} onClick={() => sendFeedback(artifact)}><Send size={14} />{busy === `feedback:${id}` ? "Leader 正在分析..." : "提交并重规划"}</button></section>}
        </article>;
      })}
    </div>
  </Panel>;
}

function SessionFeedbackPanel({
  detail,
  submitFeedback,
  requestReplan,
  decidePlan
}: {
  detail: SessionDetail;
  submitFeedback: (sessionId: string, payload: Record<string, unknown>) => Promise<void>;
  requestReplan: (sessionId: string) => Promise<void>;
  decidePlan: (sessionId: string, approved: boolean) => Promise<void>;
}) {
  const [targetType, setTargetType] = useState("session");
  const [targetId, setTargetId] = useState("");
  const [message, setMessage] = useState("");
  const [reasonType, setReasonType] = useState("unspecified");
  const [submitting, setSubmitting] = useState(false);
  const [operationError, setOperationError] = useState("");
  const nodes = (detail.task_nodes ?? []).filter((node) => node.status !== "superseded");
  const artifacts = detail.artifacts ?? [];
  const agents = detail.session_agents ?? [];
  const latestPlan = detail.plans?.[detail.plans.length - 1];
  const leaderState = detail.session?.metadata?.leader as LeaderState | undefined;
  const conversation = detail.messages.filter(m => ["leader.user", "leader.reply", "leader.error"].includes(String(m.message_type)));
  const targetOptions = targetType === "action"
    ? nodes.map((node) => ({ id: String(node.id), label: String(node.title ?? node.node_key ?? node.id) }))
    : targetType === "artifact"
      ? artifacts.map((artifact) => ({ id: String(artifact.id), label: String(artifact.path ?? artifact.id) }))
      : targetType === "agent"
        ? agents.map((agent) => ({ id: String(agent.agent_id), label: String(agent.agent_id) }))
        : [];

  async function perform(operation: () => Promise<void>) {
    setOperationError("");
    setSubmitting(true);
    try {
      await operation();
    } catch (error) {
      setOperationError(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  }

  async function submit() {
    if (!detail.session?.id || !message.trim()) return;
    const sessionId = detail.session.id;
    await perform(async () => {
      await submitFeedback(sessionId, {
        target_type: targetType,
        target_id: targetType === "session" ? null : targetId || null,
        message: message.trim(),
        requested_action: "replan",
        created_by: "operator",
        reason_type: reasonType
      });
      setMessage("");
    });
  }

  return (
    <Panel title="与 Leader 协作">
      <div className="feedbackPanel">
        <div className="feedbackIntro">
          <div>
            <strong>{latestPlan?.status === "awaiting_approval" ? "新计划待批准" : detail.replan_required ? "等待 Leader 重规划" : "向 Leader 提出调整"}</strong>
            <p className="muted">需求 v{String(detail.current_requirement?.version ?? 1)} · 计划 v{String(latestPlan?.version ?? 1)}</p>
          </div>
          {(detail.replan_required || leaderState?.status === "planning_failed") && <button onClick={() => perform(() => requestReplan(detail.session!.id))} disabled={submitting}><RefreshCw size={14} />{submitting ? "Leader 正在规划..." : "重试规划"}</button>}
        </div>
        {leaderState?.error && <p className="learningError" role="alert">规划未完成：{leaderState.error}</p>}
        {conversation.length > 0 && <div className="leaderConversation" aria-label="Leader 对话" aria-live="polite">{conversation.slice(-12).map(m => {
          const payload = m.payload as Record<string, unknown> | undefined;
          return <article key={String(m.id)} className={m.message_type === "leader.user" ? "userMessage" : "leaderMessage"}><header><strong>{m.message_type === "leader.user" ? "你" : "Leader"}</strong><small>{formatTime(String(m.created_at))}</small></header><p>{String(payload?.content ?? "")}</p></article>;
        })}</div>}
        {!!leaderState?.questions?.length && <section className="leaderQuestions"><strong>需要你确认</strong>{leaderState.questions.map(q => <p key={q}>{q}</p>)}</section>}
        {!!leaderState?.acceptance?.length && <details className="advancedSession"><summary>任务理解与验收标准</summary><p>{leaderState.understanding}</p><ul>{leaderState.acceptance.map(a => <li key={a}>{a}</li>)}</ul></details>}
        {leaderState?.diff && <div className="planDiff">{[{ key: "added", label: "新增" }, { key: "revised", label: "调整" }, { key: "preserved", label: "复用已完成" }, { key: "removed", label: "移除" }].map(item => !!leaderState.diff?.[item.key]?.length && <span key={item.key}>{item.label}：{leaderState.diff[item.key].join("、")}</span>)}</div>}
        {operationError && <p role="alert">{operationError}</p>}
        {latestPlan?.status === "awaiting_approval" && <details className="advancedSession"><summary>检查计划指令</summary><div className="feedbackHistory">
          <strong>变更原因</strong><span>{String(latestPlan.change_reason ?? "用户调整任务要求")}</span>
          {nodes.filter((node) => node.plan_id === latestPlan.id).map((node) => <div key={String(node.id)}><strong>{String(node.title)}</strong><span>{String(node.instruction)}</span></div>)}
        </div></details>}
        <div className="feedbackForm">
          <textarea aria-label="校正内容" disabled={submitting} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="补充要求，或告诉 Leader 保留什么、修改什么" rows={3} />
          <details className="advancedSession"><summary>限定反馈范围与原因</summary>
          <select aria-label="校正范围" disabled={submitting} value={targetType} onChange={(event) => { setTargetType(event.target.value); setTargetId(""); }}>
            <option value="session">整个 Session</option>
            <option value="action">某个 Action</option>
            <option value="artifact">某个产物</option>
            <option value="agent">某个 Agent</option>
          </select>
          <select aria-label="校正原因" disabled={submitting} value={reasonType} onChange={(event) => setReasonType(event.target.value)}><option value="unspecified">暂不分类</option><option value="new_requirement">新增需求</option><option value="misunderstanding">需求理解偏差</option><option value="execution_issue">执行未达标</option><option value="preference">偏好调整</option></select>
          {targetType !== "session" && <select aria-label="校正目标" disabled={submitting} value={targetId} onChange={(event) => setTargetId(event.target.value)}>
            <option value="">选择目标</option>
            {targetOptions.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}
          </select>}
          </details>
          <button className="primaryButton" onClick={submit} disabled={submitting || !message.trim() || (targetType !== "session" && !targetId)}><Send size={15} />{submitting ? "Leader 正在分析并调整方案..." : "发送给 Leader"}</button>
        </div>
        {(detail.affected_nodes?.length ?? 0) > 0 && <div className="impactSummary">
          <span>待重规划节点：{detail.affected_nodes?.length}</span>
          <span>过期产物：{detail.stale_artifacts?.length ?? 0}</span>
          <span>需求版本：v{String(detail.current_requirement?.version ?? "-")}</span>
        </div>}
        {(detail.feedback?.length ?? 0) > 0 && <div className="feedbackHistory">
          {detail.feedback?.slice(-3).reverse().map((item) => <div key={String(item.id)}><strong>{String(item.target_type)}</strong><span>{String(item.message)}</span><small>{String(item.status)}</small></div>)}
        </div>}
      </div>
    </Panel>
  );
}

function LeaderDecisionPanel({ detail, decidePlan, decideDelegation, decideApproval }: {
  detail: SessionDetail;
  decidePlan: (sessionId: string, approved: boolean) => Promise<void>;
  decideDelegation: (id: string, approved: boolean) => Promise<void>;
  decideApproval: (approval: Approval, approved: boolean) => Promise<void>;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState("");
  const plan = detail.plans?.[detail.plans.length - 1];
  const state = detail.session?.metadata?.leader as LeaderState | undefined;
  const requests = (detail.delegation_requests ?? []).filter(r => r.status === "pending");
  const approvals = (detail.approvals ?? []).filter(a => a.status === "pending" && a.action_summary?.type !== "delegation");
  const waitingPlan = plan?.status === "awaiting_approval";
  const blocked = !!state?.questions?.length || !!state?.unresolved_gaps?.length || state?.status === "planning_failed";
  async function perform(id: string, action: () => Promise<void>, message: string) {
    if (busy) return;
    setBusy(id); setError(""); setResult("");
    try { await action(); setResult(message); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  }
  return <Panel title={`等待你的决定 · ${Number(waitingPlan) + requests.length + approvals.length}`}>
    <div className="decisionInbox" aria-busy={!!busy}>
      {error && <p className="learningError" role="alert">{error}</p>}
      {result && <p role="status">{result}</p>}
      {waitingPlan && <article><strong>任务计划 v{String(plan.version)}</strong><p>{blocked ? "先补充问题或解决能力缺口" : "确认步骤与交付要求"}</p><div className="decisionButtons"><button className="primaryButton" disabled={!!busy || blocked} onClick={() => perform("plan", () => decidePlan(detail.session!.id, true), "计划已批准，可以执行任务")}><CheckCircle2 size={14} />批准计划</button><button disabled={!!busy} onClick={() => perform("plan", () => decidePlan(detail.session!.id, false), "计划已拒绝，请告诉 Leader 调整要求")}><X size={14} />拒绝</button></div></article>}
      {requests.map(r => <article key={r.id}><strong>成员与能力扩展</strong><p>{r.requested_agent_id || r.requested_role}</p><small>{r.objective}</small><p className="capabilityNames">{[...r.requested_skills, ...r.requested_tools].join(" · ") || "复用 Agent 配置"}</p><Badge value={r.risk_level} /><div className="decisionButtons"><button className="primaryButton" disabled={!!busy} onClick={() => perform(r.id, () => decideDelegation(r.id, true), "扩展已授权，任务仍按批准的计划执行")}><CheckCircle2 size={14} />批准扩展</button><button disabled={!!busy} onClick={() => perform(r.id, () => decideDelegation(r.id, false), "扩展已拒绝，可向 Leader 调整方案")}><X size={14} />拒绝</button></div></article>)}
      {approvals.map(a => <article key={a.id}><strong>执行动作 · {String(a.action_summary?.tool ?? "工具")}</strong><p>{a.reason || "需要确认这次具体动作"}</p><details><summary>动作参数</summary><pre>{JSON.stringify(a.action_summary, null, 2)}</pre></details><div className="decisionButtons"><button className="primaryButton" disabled={!!busy} onClick={() => perform(a.id, () => decideApproval(a, true), "审批已记录，执行状态已刷新")}><CheckCircle2 size={14} />批准并恢复</button><button disabled={!!busy} onClick={() => perform(a.id, () => decideApproval(a, false), "动作已拒绝")}><X size={14} />拒绝</button></div></article>)}
      {!waitingPlan && !requests.length && !approvals.length && <p className="muted">当前没有待审批事项。</p>}
      {!!busy && <p role="status">正在处理，请稍候...</p>}
    </div>
  </Panel>;
}

function LeaderSkillDiscovery({ detail, requestReplan, submitFeedback }: {
  detail: SessionDetail;
  requestReplan: (id: string) => Promise<void>;
  submitFeedback: (id: string, payload: Record<string, unknown>) => Promise<void>;
}) {
  const state = detail.session?.metadata?.leader as LeaderState | undefined;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [candidates, setCandidates] = useState<SkillSpec[]>([]);
  const [query, setQuery] = useState("");
  const [repositories, setRepositories] = useState<SkillSearchResult[]>([]);
  if (!state?.unresolved_gaps?.length) return null;
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  }
  async function scan(repository: SkillSearchResult) {
    await perform(async () => {
      const response = await postJson<{ candidates: SkillSpec[]; truncated?: boolean }>("/skills/github/scan", { url: repository.url });
      setCandidates(response.candidates);
      setNotice(response.candidates.length ? `发现 ${response.candidates.length} 个候选${response.truncated ? "，此仓库仅扫描前 30 项" : ""}，请检查说明与依赖` : "此仓库未发现可导入的 SKILL.md");
    });
  }
  async function install(skill: SkillSpec) {
    await perform(async () => {
      await postJson("/skills/register", { skill, approved: true });
      setNotice("Skill 已登记，Leader 正在检查适用性和工具依赖...");
      await requestReplan(detail.session!.id);
    });
  }
  async function chooseAlternative(capability: string, alternative: CapabilityAlternative) {
    await perform(async () => {
      await submitFeedback(detail.session!.id, {
        target_type: "session", requested_action: "replan", created_by: "operator", reason_type: "preference",
        message: `针对能力缺口「${capability}」，我选择候选路线「${alternative.title}」。\n${alternative.proposal}\n取舍：${alternative.tradeoff}\n前置条件：${alternative.prerequisites.join("；") || "请 Leader 核实"}\n请据此重新规划并检查前置条件，等待我批准新计划；这不是执行授权，也不表示缺口已解决。`
      });
    });
  }
  const rows = repositories.length ? repositories : (state.discovery ?? []).flatMap(d => d.repositories ?? []);
  return <Panel title="能力缺口与寻找方案">
    <div className="skillDiscovery">
      {state.unresolved_gaps.map((g, index) => <section key={`${g.capability}-${index}`}><strong>{g.capability}</strong><p>{g.reason}</p>
        {!!g.alternatives?.length && <div className="capabilityAlternatives">{g.alternatives.map((a, option) => <article key={option}>
          <strong>{a.title}</strong><p>{a.proposal}</p><p className="muted">取舍：{a.tradeoff}</p>
          {!!a.prerequisites.length && <p className="muted">需要：{a.prerequisites.join("；")}</p>}
          <button disabled={busy || state.status === "planning"} onClick={() => chooseAlternative(g.capability, a)}><Send size={14} />交给 Leader 重规划</button>
        </article>)}</div>}
      </section>)}
      {(state.discovery ?? []).map((d, index) => <p key={`${d.query}-${index}`} className={d.status === "failed" ? "learningError" : "muted"}>{d.query}：{d.status === "failed" ? `搜索失败，${d.error}` : d.status === "not_searched" ? d.reason : d.status === "no_results" ? "未找到候选，可换关键词或选择候选路线" : `找到 ${d.repositories.length} 个仓库，尚未验证适用性`}</p>)}
      <form className="skillSearchForm" onSubmit={e => { e.preventDefault(); void perform(async () => { const response = await postJson<{ results: SkillSearchResult[] }>("/skills/github/search", { query, per_page: 6 }); setRepositories(response.results); setNotice(response.results.length ? "已返回候选仓库" : "没有结果，请调整搜索词"); }); }}><input aria-label="寻找 Skill" placeholder="搜索其他 Skill，例如 creative writing" value={query} onChange={e => setQuery(e.target.value)} /><button disabled={busy || !query.trim()}><Search size={15} />搜索</button></form>
      {error && <p role="alert" className="learningError">{error}</p>}{notice && <p role="status">{notice}</p>}
      {!!busy && <p role="status">正在查找或检查能力，请稍候...</p>}
      <div className="skillRepositoryList">{Array.from(new Map(rows.map(r => [r.repository, r])).values()).map(r => <article key={r.repository}><div><a href={r.url} target="_blank" rel="noreferrer">{r.repository}</a><p>{r.description}</p></div><button disabled={busy} onClick={() => scan(r)}><Search size={14} />检查 Skills</button></article>)}</div>
      {candidates.length > 0 && <div className="skillCandidateList">{candidates.map(s => <details key={s.id}><summary>{s.name} · {s.scan_status === "review" ? "需检查风险提示" : "规则扫描未发现已知模式"}</summary><p>{s.description}</p><p>工具依赖：{s.recommended_tools.join("、") || "未声明"}</p><small>版本：{s.source_ref} · {s.content_hash}</small>{s.scan_findings?.map(f => <p className="learningError" key={f}>{f}</p>)}<pre>{s.prompt_body}</pre><button disabled={busy} onClick={() => install(s)}><Plus size={14} />批准登记并让 Leader 检查</button></details>)}</div>}
    </div>
  </Panel>;
}

function LeaderOrchestrationPanel({
  detail,
  agents,
  skills,
  tools,
  requestDelegation,
  decideDelegation
}: {
  detail: SessionDetail;
  agents: Agent[];
  skills: SkillSpec[];
  tools: ToolSpec[];
  requestDelegation: (sessionId: string, payload: Record<string, unknown>) => Promise<void>;
  decideDelegation: (delegationId: string, approved: boolean) => Promise<void>;
}) {
  const sessionAgents = detail.session_agents ?? [];
  const requests = detail.delegation_requests ?? [];
  const leader = sessionAgents.find((item) => item.role === "leader") ?? sessionAgents[0];
  const [objective, setObjective] = useState("Produce a specialist result for the current Session");
  const [role, setRole] = useState("specialist");
  const [reuseAgent, setReuseAgent] = useState("");
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const activeAgents = sessionAgents.filter((item) => item.status === "active");
  const toggle = (current: string[], id: string) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id];

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!leader || !objective.trim()) return;
    setSubmitting(true);
    try {
      await requestDelegation(detail.session!.id, {
        parent_agent_id: leader.agent_id,
        requester_agent_id: leader.agent_id,
        requested_agent_id: reuseAgent || null,
        requested_role: role,
        objective: objective.trim(),
        requested_skills: selectedSkills,
        requested_tools: selectedTools,
        auto_approve: true
      });
      setObjective("Produce a specialist result for the current Session");
      setSelectedSkills([]);
      setSelectedTools([]);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Panel title="Leader 编排">
      <div className="orchestrationSummary">
        <StatusPill icon={<GitBranch size={16} />} label="Leader" value={leader?.agent_id ?? "not assigned"} tone={leader ? "ok" : "warning"} />
        <StatusPill icon={<Bot size={16} />} label="运行中 Agent" value={activeAgents.length} tone="neutral" />
        <StatusPill icon={<ClipboardCheck size={16} />} label="待处理请求" value={requests.filter((item) => item.status === "pending").length} tone={requests.some((item) => item.status === "pending") ? "warning" : "ok"} />
      </div>
      <div className="orchestrationLayout">
        <div className="agentRoster">
          <h3>Session Agent</h3>
          {activeAgents.length ? activeAgents.map((agent) => <div className="agentRosterRow" key={agent.id}><span className={`agentDepth depth-${Math.min(agent.depth, 3)}`} /> <div><strong>{displayText(agent.agent_id)}</strong><small>{agent.role} / {agent.origin} / depth {agent.depth}</small></div><Badge value={agent.status} /></div>) : <p className="muted">The Session has no registered Leader yet.</p>}
        </div>
        <form className="delegationComposer" onSubmit={submit}>
          <div className="composerHeader"><strong>Leader 请求扩展协作</strong><span>低风险自动通过，中高风险进入人工审批。</span></div>
          <input value={objective} onChange={(event) => setObjective(event.target.value)} placeholder="请输入子任务目标" />
          <div className="composerFields"><label>Role<select value={role} onChange={(event) => setRole(event.target.value)}><option value="specialist">specialist</option><option value="researcher">researcher</option><option value="reviewer">reviewer</option><option value="builder">builder</option></select></label><label>Reuse Agent<select value={reuseAgent} onChange={(event) => setReuseAgent(event.target.value)}><option value="">Create dynamic Agent</option>{agents.map((agent) => <option value={agent.id} key={agent.id}>{agent.id}</option>)}</select></label></div>
          <div className="capabilityPicker"><span>Skills</span><div>{skills.slice(0, 8).map((skill) => <label key={skill.id}><input type="checkbox" checked={selectedSkills.includes(skill.id)} onChange={() => setSelectedSkills(toggle(selectedSkills, skill.id))} />{skill.id}</label>)}</div></div>
          <div className="capabilityPicker"><span>Tools</span><div>{tools.slice(0, 8).map((tool) => <label key={tool.id}><input type="checkbox" checked={selectedTools.includes(tool.id)} onChange={() => setSelectedTools(toggle(selectedTools, tool.id))} />{tool.id}</label>)}</div></div>
          <button className="primaryButton" type="submit" disabled={submitting || !leader}><GitBranch size={15} />{submitting ? "提交中..." : "提交扩展请求"}</button>
        </form>
      </div>
      {requests.length > 0 && <div className="delegationList"><h3>扩展请求与审批</h3>{requests.slice(0, 8).map((request) => <article className={`delegationRow ${request.status}`} key={request.id}><div><strong>{request.requested_role}</strong><p>{displayText(request.objective)}</p><small>{request.requester_agent_id} · {request.risk_level} 风险 · ${request.budget_usd.toFixed(4)} · {request.requested_skills.length} 个 Skill / {request.requested_tools.length} 个 Tool</small></div><div className="delegationActions"><Badge value={request.status} />{request.status === "pending" && <><button className="primaryButton" onClick={() => decideDelegation(request.id, true)} title="批准扩展"><CheckCircle2 size={14} />批准</button><button onClick={() => decideDelegation(request.id, false)} title="拒绝扩展"><X size={14} />拒绝</button></>}</div></article>)}</div>}
    </Panel>
  );
}

function SessionApprovalPanel({ approvals, decideApproval }: { approvals: Approval[]; decideApproval: (approval: Approval, approved: boolean) => Promise<void> }) {
  const pending = approvals.filter((approval) => approval.status === "pending");
  return (
    <Panel title="Session 执行审批">
      <p className="panelHint">这里处理 Agent 执行高风险 Tool 的审批；Leader 扩展审批在上方，两者不是同一类决定。</p>
      {approvals.length === 0 ? <p className="emptyState">当前 Session 没有执行审批。</p> : <div className="delegationList">{approvals.slice(0, 8).map((approval) => {
        const summary = approval.action_summary as Record<string, unknown> | undefined;
        return <article className={`delegationRow ${approval.status}`} key={approval.id}><div><strong>{String(summary?.tool ?? "工具执行")}</strong><p>{approval.reason || "高风险动作需要人工确认"}</p><small>{approval.requested_by} · Run {shortId(approval.run_id)}</small></div><div className="delegationActions"><Badge value={approval.status} />{approval.status === "pending" && <><button className="primaryButton" onClick={() => decideApproval(approval, true)}><CheckCircle2 size={14} />批准并恢复</button><button onClick={() => decideApproval(approval, false)}><X size={14} />拒绝</button></>}</div></article>;
      })}</div>}
      {pending.length > 0 && <small className="muted">批准后系统会自动恢复对应 Run，并重新执行经过授权的动作。</small>}
    </Panel>
  );
}

function SessionTopologyPanel({ sessionId, revision = "" }: { sessionId: string; revision?: string }) {
  const [graph, setGraph] = useState<Topology>({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setGraph({ nodes: [], edges: [] });
    setSelectedNode(null);
  }, [sessionId]);
  useEffect(() => {
    let active = true;
    getJson<Topology>(`/dashboard/topology/sessions/${sessionId}?current_only=true`).then(data => {
      if (!active) return;
      setGraph(data); setError("");
      setSelectedNode(current => current ? data.nodes.find(node => node.id === current.id) ?? null : null);
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : String(err)); });
    return () => { active = false; };
  }, [sessionId, revision]);
  return <div className="sessionTopology">{error && <p role="alert" className="learningError">协作图加载失败：{error}</p>}{graph.nodes.length ? <><GraphCanvas graph={graph} selectedNode={selectedNode} onSelect={setSelectedNode} /><div className="graphLegend"><span><i className="dot live" />Agent / 请求</span><span><i className="dot audit" />授权 / 生命周期</span><span><i className="dot trace" />Run / 工具</span></div></> : !error && <p className="emptyState">暂无协作节点。</p>}</div>;
}

function MonitoringLayers({ detail, events, auditSummary }: { detail: SessionDetail; events: AuditEvent[]; auditSummary: Record<string, number> }) {
  const stateCount = detail.runs.filter((run) => ["running", "pending", "paused", "blocked", "awaiting_approval"].includes(run.status)).length;
  const auditCount = Number(auditSummary.events ?? events.length);
  const traceCount = detail.model_calls.length + detail.tool_calls.length;
  const evidenceCount = (detail.evidence_refs?.length ?? 0) + (detail.artifacts?.length ?? 0);
  const layers = [
    { key: "state", label: "状态 State", value: stateCount, caption: "现在发生什么", tone: stateCount ? "warning" : "ok", detail: `${detail.runs.length} 个 Run · ${detail.session?.status ?? "unknown"}` },
    { key: "audit", label: "审计 Audit", value: auditCount, caption: "谁在何时做了什么", tone: "neutral", detail: "append-only 事件链" },
    { key: "trace", label: "追踪 Trace", value: traceCount, caption: "模型和工具怎么执行", tone: traceCount ? "ok" : "neutral", detail: `${detail.model_calls.length} 模型 · ${detail.tool_calls.length} 工具` },
    { key: "evidence", label: "证据 Evidence", value: evidenceCount, caption: "什么可以证明结果", tone: evidenceCount ? "ok" : "warning", detail: `${detail.artifacts?.length ?? 0} 产物 · ${detail.evidence_refs?.length ?? 0} 引用` }
  ];
  return (
    <Panel title="监测模型">
      <div className="monitorLayers">
        {layers.map((layer) => <article className={`monitorLayer ${layer.tone}`} key={layer.key}><div><span>{layer.label}</span><strong>{layer.value}</strong></div><p>{layer.caption}</p><em>{layer.detail}</em></article>)}
      </div>
      <div className="monitorLegend"><span><i className="dot live" />状态用于操作</span><span><i className="dot audit" />审计用于复盘</span><span><i className="dot trace" />追踪用于定位</span><span><i className="dot evidence" />证据用于结论</span></div>
    </Panel>
  );
}

function KnowledgeContextPanel({ detail }: { detail: SessionDetail }) {
  const sources = detail.knowledge_sources ?? [];
  const grants = detail.knowledge_grants ?? [];
  const accessEvents = detail.knowledge_access_events ?? [];
  const sourceNames = new Map(sources.map((source) => [source.id, source.name]));
  const grantsByAgent = new Map<string, number>();
  grants.forEach((grant) => {
    const agent = String(grant.agent_id ?? "unknown");
    grantsByAgent.set(agent, (grantsByAgent.get(agent) ?? 0) + (Array.isArray(grant.source_ids) ? grant.source_ids.length : 0));
  });
  return (
    <Panel title="Session 知识上下文">
      <div className="knowledgeSummary">
        <Signal label="Session 来源" value={sources.length} />
        <Signal label="Leader 授权" value={grants.length} />
        <Signal label="实际访问" value={accessEvents.length} />
        <Signal label="引用要求" value={detail.knowledge_policy?.require_citation ? "是" : "否"} />
      </div>
      <div className="knowledgeDashboardGrid">
        <section className="knowledgeAudit">
          <h3>知识源</h3>
          {sources.length ? sources.map((source) => {
            const loaded = accessEvents.some((event) => event.source_id === source.id && event.decision === "allow");
            return <div className="knowledgeAuditRow" key={source.id}><span className="knowledgeMarker" /><div><strong>{displayText(source.name)}</strong><em>{source.source_type} · {source.trust_level} · {loaded ? "已加载" : "未加载"}</em></div><b>{source.required_citation ? "需引用" : "可选"}</b></div>;
          }) : <p className="muted">本 Session 没有附加知识源。</p>}
        </section>
        <section className="knowledgeAudit">
          <h3>Agent 访问计划</h3>
          {grantsByAgent.size ? Array.from(grantsByAgent.entries()).map(([agent, count]) => <div className="knowledgeGrant" key={agent}><strong>{displayText(agent)}</strong><span>{count} 个来源</span></div>) : <p className="muted">规划完成后将在这里显示 Leader 授权。</p>}
        </section>
      </div>
      <div className="knowledgeEventStrip">
        <span><i className="dot trace" />{accessEvents.filter((event) => event.action === "context_build").length} 次 Context Pack 加载</span>
        <span><i className="dot audit" />{accessEvents.filter((event) => event.action === "knowledge_search").length} 次知识检索</span>
        <span><i className="dot danger" />{accessEvents.filter((event) => event.decision === "deny").length} 次越权拒绝</span>
      </div>
      {accessEvents.length > 0 && <div className="knowledgeRecent"><strong>最近访问</strong>{accessEvents.slice(-5).reverse().map((event, index) => <span key={`${String(event.id ?? "event")}-${index}`}>{String(event.agent_id ?? "agent")} · {String(event.action ?? "access")} · {sourceNames.get(String(event.source_id ?? "")) ?? String(event.source_id ?? "-")} · {String(event.decision ?? "-")}</span>)}</div>}
    </Panel>
  );
}

function RollbackPlan({ report, actions }: { report: SessionAuditReport | null; actions: GovernanceAction[] }) {
  const rollbackAction = actions.find((action) => action.id === "rollback");
  const checkpoints = report?.artifact_chain ?? [];
  const rollbackEvents = report?.rollback_chain ?? [];
  return (
    <Panel title="回滚计划">
      <div className="rollbackPlan">
        <StatusPill icon={<RotateCcw size={16} />} label="当前能力" value={rollbackAction?.enabled ? "可执行" : "待后端接入"} tone={rollbackAction?.enabled ? "ok" : "neutral"} />
        <div className="planSteps">
          <span className={checkpoints.length ? "ready" : ""}>1. 选择 artifact/checkpoint 版本</span>
          <span>2. 生成 rollback.requested 审批事件</span>
          <span>3. 恢复产物或重排待执行节点</span>
          <span>4. 追加 rollback.applied 审计事件</span>
        </div>
        <p className="muted">{rollbackEvents.length ? `已有 ${rollbackEvents.length} 条回滚/重试相关事件。` : rollbackAction?.disabled_reason || "需要 checkpoint、artifact version restore 和 node retry API。"}</p>
      </div>
    </Panel>
  );
}

function AuditReportPanel({ report }: { report: SessionAuditReport | null }) {
  if (!report) return <Panel title="审计报告"><p>审计报告接口暂不可用或尚未选择 Session。</p></Panel>;
  const summary = report.summary ?? {};
  return (
    <Panel title="审计报告">
      <div className="auditReportMini">
        <Signal label="事件" value={summary.events ?? report.timeline.length} />
        <Signal label="责任链" value={report.responsibility_chain.length} />
        <Signal label="策略/审批" value={report.decision_chain.length} />
        <Signal label="产物" value={report.artifact_chain.length} />
      </div>
    </Panel>
  );
}

function EvidenceChain({
  artifacts,
  decisions,
  messages
}: {
  artifacts: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  messages: Array<Record<string, unknown>>;
}) {
  const rows = [
    ...artifacts.slice(0, 4).map((item) => ({ kind: "产物/证据", title: String(item.path ?? item.uri ?? item.id ?? "artifact"), meta: String(item.run_id ?? item.created_at ?? "-") })),
    ...decisions.slice(0, 4).map((item) => ({ kind: "策略/审批", title: String(item.decision ?? item.status ?? item.reason ?? "decision"), meta: String(item.run_id ?? item.created_at ?? "-") })),
    ...messages.slice(0, 4).map((item) => ({ kind: "通信", title: String(item.message_type ?? item.role ?? item.id ?? "message"), meta: String(item.sender_agent_id ?? item.created_at ?? "-") }))
  ];
  if (!rows.length) return <p>暂无证据链数据。</p>;
  return (
    <div className="evidenceChain">
      {rows.map((row, index) => (
        <article key={`${row.kind}-${index}`}>
          <span>{row.kind}</span>
          <strong>{displayText(row.title)}</strong>
          <em>{displayText(row.meta)}</em>
        </article>
      ))}
    </div>
  );
}

function MessageList({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p>暂无 Agent 通信。</p>;
  return (
    <div className="messageList">
      {rows.slice(-12).map((row, index) => {
        const payload = (row.payload ?? {}) as Record<string, unknown>;
        const source = String(row.source_agent_id ?? row.sender_agent_id ?? row.role ?? row.actor_id ?? "agent");
        const target = String(row.target_agent_id ?? "Session");
        const content = String(payload.content ?? payload.summary ?? payload.instruction ?? row.content ?? row.message ?? row.summary ?? row.message_type ?? "消息已记录");
        return <article key={String(row.id ?? index)}><strong>{displayText(`${source} → ${target}`)}</strong><p>{displayText(content)}</p><small>{displayText(String(row.message_type ?? row.status ?? "message"))}</small><span>{formatTime(String(row.created_at ?? ""))}</span></article>;
      })}
    </div>
  );
}

function SessionsPage({
  sessions,
  selectedSessionId,
  setSelectedSessionId,
  detail,
  setSelectedRunId,
  setPage,
  controlSession
}: {
  sessions: Session[];
  selectedSessionId: string | null;
  setSelectedSessionId: (id: string) => void;
  detail: SessionDetail | null;
  setSelectedRunId: (id: string) => void;
  setPage: (page: PageKey) => void;
  controlSession: (sessionId: string, action: "pause" | "cancel" | "resume" | "execute-pending") => void;
}) {
  return (
    <section className="split">
      <Panel title="Session 列表">
        <table><thead><tr><th>标题</th><th>状态</th><th>Root Agent</th><th>创建时间</th></tr></thead><tbody>{sessions.map((session) => (
          <tr className={selectedSessionId === session.id ? "selected" : ""} key={session.id} onClick={() => setSelectedSessionId(session.id)}>
            <td>{displayText(session.title)}</td><td><Badge value={session.status} /></td><td>{session.root_agent_id || "-"}</td><td>{formatTime(session.created_at)}</td>
          </tr>
        ))}</tbody></table>
      </Panel>
      <Panel title="Session 复盘">
        {detail?.session ? (
          <div className="detail">
            <div className="detailHead">
              <div><h3>{displayText(detail.session.title)}</h3><p>{displayText(detail.session.context_summary || "暂无上下文摘要")}</p></div>
              <div className="actions">
                <button onClick={() => controlSession(detail.session!.id, "execute-pending")}><Play size={15} />执行待处理</button>
                <button onClick={() => controlSession(detail.session!.id, "pause")}>暂停</button>
                <button onClick={() => controlSession(detail.session!.id, "resume")}>恢复</button>
                <button onClick={() => controlSession(detail.session!.id, "cancel")}>取消</button>
              </div>
            </div>
            <Signal label="Session ID" value={shortId(detail.session.id)} />
            <Signal label="状态" value={detail.session.status} />
            <Signal label="Team" value={detail.session.team_id || "临时/单 Agent"} />
            <Signal label="Run 数量" value={detail.runs.length} />
            <Signal label="模型调用" value={detail.model_calls.length} />
            <Signal label="工具调用" value={detail.tool_calls.length} />
            <Signal label="证据文件" value={detail.evidence_refs.length} />
            <h3>本 Session 的 Run</h3>
            <RunTable runs={detail.runs} onSelect={(id) => { setSelectedRunId(id); setPage("runs"); }} compact />
            <h3>Agent 消息 / 委托</h3>
            <JsonList rows={detail.messages} />
            <h3>产物与证据</h3>
            <JsonList rows={detail.evidence_refs} />
            <h3>跨 Run 时间线</h3>
            <Timeline events={detail.steps} />
          </div>
        ) : <p>请选择一个 Session。</p>}
      </Panel>
    </section>
  );
}

function AgentsPage({ agents, runs, security }: { agents: Agent[]; runs: Run[]; security: SecurityData }) {
  return (
    <section className="pageStack">
      <Panel title="Agent 目录">
        <div className="agentGrid">{agents.map((agent) => {
          const related = runs.filter((run) => run.agent_id === agent.id);
          return (
            <article className="agentCard" key={agent.id}>
              <div className="agentHead"><Bot size={18} /><strong>{displayText(agent.name)}</strong></div>
              <span>标识：{agent.id}</span>
              <span>模型：{agent.provider} / {agent.model}</span>
              <span>工具：{agent.tools?.length ? agent.tools.join(", ") : "无工具"}</span>
              <span>沙箱：{agent.sandbox || "无"}</span>
              <div className="statusLine"><b>{related.length}</b> 次运行 <b>{related.filter((r) => r.status === "failed").length}</b> 次失败</div>
            </article>
          );
        })}</div>
      </Panel>
      <Panel title="权限与策略绑定">
        <table><thead><tr><th>Agent</th><th>策略</th><th>最近策略决策数</th></tr></thead><tbody>{agents.map((agent) => (
          <tr key={agent.id}><td>{agent.id}</td><td>{(agent as unknown as { policies?: string[] }).policies?.join(", ") || "默认策略"}</td><td>{security.policy_decisions.filter((d) => String(d.subject).includes(agent.id)).length}</td></tr>
        ))}</tbody></table>
      </Panel>
    </section>
  );
}

function RunsPage({
  runs,
  selectedRunId,
  setSelectedRunId,
  runDetail,
  executeRun,
  controlRun,
  retryRun
}: {
  runs: Run[];
  selectedRunId: string | null;
  setSelectedRunId: (id: string) => void;
  runDetail: RunDetail | null;
  executeRun: (id: string) => void;
  controlRun: (id: string, action: "pause" | "cancel" | "resume") => void;
  retryRun?: (id: string) => void;
}) {
  return (
    <section className="split">
      <Panel title="Run 列表"><RunTable runs={runs} selectedRunId={selectedRunId} onSelect={setSelectedRunId} /></Panel>
      <Panel title="Run 详情">
        {runDetail?.run ? (
          <div className="detail">
            <div className="detailHead">
              <div><h3>{runDetail.run.agent_id}</h3><p>{displayText(runDetail.run.input_summary)}</p></div>
              <div className="actions">
                <button className="primaryButton" onClick={() => executeRun(runDetail.run!.id)}><Play size={16} />执行</button>
                <button onClick={() => controlRun(runDetail.run!.id, "pause")}>暂停</button>
                <button onClick={() => controlRun(runDetail.run!.id, "resume")}>恢复</button>
                <button onClick={() => controlRun(runDetail.run!.id, "cancel")}>取消</button>
                <button disabled={!retryRun || !['failed', 'cancelled', 'timeout', 'rejected'].includes(runDetail.run!.status)} onClick={() => retryRun?.(runDetail.run!.id)}><RotateCcw size={15} />重试</button>
              </div>
            </div>
            <Signal label="状态" value={runDetail.run.status} />
            <Signal label="Session" value={shortId(runDetail.run.session_id)} />
            <Signal label="输入 Token" value={(runDetail.run as unknown as { input_tokens?: number }).input_tokens ?? 0} />
            <Signal label="输出 Token" value={(runDetail.run as unknown as { output_tokens?: number }).output_tokens ?? 0} />
            <Signal label="成本 USD" value={String((runDetail.run as unknown as { actual_cost_usd?: number }).actual_cost_usd ?? 0)} />
            {runDetail.run.error && <div className="errorBox">{runDetail.run.error}</div>}
            <h3>模型调用上下文</h3><JsonList rows={runDetail.model_calls} />
            <h3>Action 意图 / Observation</h3><JsonList rows={[...(runDetail.action_intents ?? []), ...(runDetail.observations ?? [])]} />
            <h3>工具调用与产物</h3><JsonList rows={[...runDetail.tool_calls, ...runDetail.evidence_refs]} />
            <h3>沙箱动作</h3><JsonList rows={runDetail.sandbox_actions} />
            <h3>策略与预算</h3><JsonList rows={[...runDetail.policy_decisions, ...runDetail.budget_ledger]} />
            <h3>事件时间线</h3><Timeline events={runDetail.steps} />
          </div>
        ) : <p>请选择一个 Run。</p>}
      </Panel>
    </section>
  );
}

function ApprovalsPage({ approvals, decideApproval, createDemoApproval }: { approvals: Approval[]; decideApproval: (approval: Approval, approved: boolean) => void; createDemoApproval: () => void }) {
  return (
    <Panel title="人工审批">
      <div className="panelToolbar"><button className="primaryButton" onClick={createDemoApproval}><ShieldCheck size={16} />生成高风险审批</button></div>
      <table><thead><tr><th>状态</th><th>Run</th><th>请求方</th><th>原因</th><th>操作</th></tr></thead><tbody>{approvals.map((approval) => (
        <tr key={approval.id}><td><Badge value={approval.status} /></td><td>{shortId(approval.run_id)}</td><td>{approval.requested_by}</td><td>{approval.reason || "-"}</td><td className="actions"><button disabled={approval.status !== "pending"} onClick={() => decideApproval(approval, true)}>通过</button><button disabled={approval.status !== "pending"} onClick={() => decideApproval(approval, false)}>拒绝</button></td></tr>
      ))}</tbody></table>
      {!approvals.length && <p>当前没有审批记录。触发高风险工具或写入动作后会出现在这里。</p>}
    </Panel>
  );
}

function AuditPage({ audit }: { audit: AuditEvent[] }) {
  return <Panel title="事件日志"><table><thead><tr><th>序号</th><th>事件类型</th><th>Actor</th><th>状态</th><th>Run</th><th>时间</th></tr></thead><tbody>{audit.map((event) => <tr key={event.id}><td>{event.seq}</td><td>{event.event_type}</td><td>{event.actor_id}</td><td><Badge value={event.status} /></td><td>{shortId(event.run_id)}</td><td>{formatTime(event.created_at)}</td></tr>)}</tbody></table></Panel>;
}

function GraphCanvas({ graph, selectedNode, onSelect }: { graph: Topology; selectedNode: TopologyNode | null; onSelect: (node: TopologyNode) => void }) {
  const columnOrder = ["session", "team", "agent", "run", "model", "model_call", "tool", "tool_call", "artifact", "approval", "policy", "sandbox"];
  const grouped = new Map<string, TopologyNode[]>();
  for (const node of graph.nodes) grouped.set(node.type, [...(grouped.get(node.type) ?? []), node]);
  const columns = columnOrder.filter((type) => grouped.has(type));
  const extras = Array.from(grouped.keys()).filter((type) => !columnOrder.includes(type));
  const allColumns = [...columns, ...extras];
  const positions = new Map<string, { x: number; y: number }>();
  allColumns.forEach((type, column) => grouped.get(type)?.forEach((node, row) => positions.set(node.id, { x: 24 + column * 208, y: 34 + row * 94 })));
  const width = Math.max(880, allColumns.length * 208 + 32);
  const height = Math.max(320, Math.max(...Array.from(grouped.values()).map((items) => items.length), 1) * 94 + 80);
  return (
    <div className="graphViewport">
      <svg className="topologySvg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Session 协作拓扑图">
        <defs><marker id="topologyArrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#94a3b8" /></marker></defs>
        {allColumns.map((type, index) => <text className="graphColumnLabel" key={type} x={24 + index * 208} y="18">{type}</text>)}
        {graph.edges.map((edge, index) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) return null;
          const sx = source.x + 174;
          const sy = source.y + 35;
          const tx = target.x;
          const ty = target.y + 35;
          const mid = (sx + tx) / 2;
          return <path className="graphEdge" key={`${edge.source}-${edge.target}-${index}`} d={`M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`} markerEnd="url(#topologyArrow)" />;
        })}
        {graph.nodes.map((node) => {
          const point = positions.get(node.id);
          if (!point) return null;
          const selected = selectedNode?.id === node.id;
          return <g className={`graphNode ${node.status ?? ""} ${selected ? "selected" : ""}`} key={node.id} transform={`translate(${point.x}, ${point.y})`} role="button" tabIndex={0} onClick={() => onSelect(node)} onKeyDown={(event) => { if (event.key === "Enter") onSelect(node); }}>
            <rect width="174" height="70" rx="8" />
            <text className="graphNodeType" x="12" y="17">{node.type}</text>
            <text className="graphNodeLabel" x="12" y="37">{graphLabel(node.label ?? node.id, 23)}</text>
            <text className="graphNodeStatus" x="12" y="57">{node.status ?? "unknown"}</text>
          </g>;
        })}
      </svg>
    </div>
  );
}

function TopologyPage({ topology, sessions, selectedSessionId, teams }: { topology: Topology; sessions: Session[]; selectedSessionId: string | null; teams: TeamConfig[] }) {
  const [mode, setMode] = useState<"session" | "team" | "agent">("session");
  const [sessionId, setSessionId] = useState<string>(selectedSessionId ?? sessions[0]?.id ?? "");
  const [teamId, setTeamId] = useState<string>(teams[0]?.id ?? "");
  const [graph, setGraph] = useState<Topology>(topology);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [graphError, setGraphError] = useState<string>("");

  useEffect(() => {
    if (!sessionId && selectedSessionId) setSessionId(selectedSessionId);
  }, [selectedSessionId, sessionId]);

  useEffect(() => {
    async function loadGraph() {
      setGraphError("");
      if (mode === "session" && sessionId) {
        setGraph(await getJson<Topology>(`/dashboard/topology/sessions/${sessionId}`));
      } else if (mode === "team") {
        const suffix = teamId ? `?team_id=${encodeURIComponent(teamId)}` : "";
        setGraph(await getJson<Topology>(`/dashboard/topology/teams${suffix}`));
      } else {
        setGraph(await getJson<Topology>("/dashboard/topology"));
      }
    }
    loadGraph().catch((error) => {
      setGraph(topology);
      setGraphError(error instanceof Error ? error.message : String(error));
    });
    if (mode !== "session") return;
    const timer = window.setInterval(() => { loadGraph().catch(() => undefined); }, 4000);
    return () => window.clearInterval(timer);
  }, [mode, sessionId, teamId, topology]);

  const visibleGraph = mode === "agent" ? topology : graph;

  return (
    <section className="pageStack">
      <Panel title="拓扑视角">
        <div className="toolbarWrap">
          <div className="segmented">
            <button className={mode === "session" ? "active" : ""} onClick={() => setMode("session")}>Session 实时图</button>
            <button className={mode === "team" ? "active" : ""} onClick={() => setMode("team")}>Team 设计图</button>
            <button className={mode === "agent" ? "active" : ""} onClick={() => setMode("agent")}>Agent 全局图</button>
          </div>
          {mode === "session" && (
            <select value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
              {sessions.map((session) => <option key={session.id} value={session.id}>{displayText(session.title)} ({shortId(session.id)})</option>)}
            </select>
          )}
          {mode === "team" && (
            <select value={teamId} onChange={(event) => setTeamId(event.target.value)}>
              <option value="">全部 Team</option>
              {teams.map((team) => <option key={team.id} value={team.id}>{team.id}</option>)}
            </select>
          )}
        </div>
        {graphError && <div className="errorBox">拓扑接口读取失败：{graphError}。请确认后端已重启到最新代码。</div>}
      </Panel>
      <section className="grid">
        <Panel title={`${mode === "session" ? "Session" : mode === "team" ? "Team" : "Agent"} 拓扑节点`}>
          <GraphCanvas graph={visibleGraph} selectedNode={selectedNode} onSelect={setSelectedNode} />
        </Panel>
        <Panel title="节点详情">
          {selectedNode ? (
            <div className="detail">
              <Signal label="ID" value={selectedNode.id} />
              <Signal label="类型" value={selectedNode.type} />
              <Signal label="状态" value={selectedNode.status ?? "-"} />
              <JsonList rows={[selectedNode.metadata ?? {}]} />
            </div>
          ) : <p>点击左侧节点查看详情。</p>}
        </Panel>
      </section>
      <Panel title="拓扑边">
        <table><thead><tr><th>来源</th><th>目标</th><th>关系</th><th>详情</th></tr></thead><tbody>{visibleGraph.edges.map((edge, index) => <tr key={`${edge.source}-${edge.target}-${edge.type}-${index}`}><td>{edge.source}</td><td>{edge.target}</td><td>{edge.type}</td><td>{edge.metadata ? JSON.stringify(edge.metadata) : "-"}</td></tr>)}</tbody></table>
      </Panel>
    </section>
  );
}

function QueuePage({ queue, workerTick }: { queue: QueueData; workerTick: () => void }) {
  return (
    <section className="pageStack">
      <Panel title="本地 Worker">
        <div className="explain"><Clock size={18} /><span>当前是本地开发模式。点击一次处理一个队列项；后续可替换为常驻后台 Worker 或 Redis 队列。</span></div>
        <div className="panelToolbar left"><button className="primaryButton" onClick={workerTick}><Play size={16} />处理一个队列项</button></div>
      </Panel>
      <section className="grid">
        <Panel title="任务队列"><JsonList rows={queue.queue.length ? queue.queue : queue.recent_runs as unknown as Array<Record<string, unknown>>} /></Panel>
        <Panel title="Worker Lease"><JsonList rows={queue.leases} /></Panel>
      </section>
    </section>
  );
}

function TaskPlanView({
  nodes,
  edges,
  setSelectedRunId,
  setPage
}: {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  setSelectedRunId: (id: string) => void;
  setPage: (page: PageKey) => void;
}) {
  if (!nodes.length) return <p>暂无编排规划。普通单 Agent 任务不会生成 Task Graph。</p>;
  const phases = [
    { key: "plan", label: "规划", match: (node: Record<string, unknown>) => /plan|delegate|coordinate/.test(String(node.node_key ?? node.title ?? "")) },
    { key: "execute", label: "执行", match: (node: Record<string, unknown>) => /write|execute|collect|evidence/.test(String(node.node_key ?? node.title ?? "")) },
    { key: "review", label: "评审", match: (node: Record<string, unknown>) => /review|audit|policy/.test(String(node.node_key ?? node.title ?? "")) }
  ];
  const grouped = phases.map((phase) => ({ ...phase, nodes: [] as Array<Record<string, unknown>> }));
  const finalGroup = { key: "final", label: "收尾", match: () => false, nodes: [] as Array<Record<string, unknown>> };
  for (const node of nodes) {
    const target = grouped.find((phase) => phase.match(node));
    (target ?? finalGroup).nodes.push(node);
  }
  grouped.push(finalGroup);
  const graphWidth = Math.max(900, grouped.filter((group) => group.nodes.length).length * 246 + 30);
  const positions = new Map<string, { x: number; y: number }>();
  const visibleGroups = grouped.filter((group) => group.nodes.length);
  visibleGroups.forEach((group, column) => group.nodes.forEach((node, row) => positions.set(String(node.id), { x: 18 + column * 246, y: 44 + row * 116 })));
  const graphHeight = Math.max(260, Math.max(...visibleGroups.map((group) => group.nodes.length), 1) * 116 + 72);
  return (
    <div className="taskGraphViewport">
      <svg className="taskGraphSvg" viewBox={`0 0 ${graphWidth} ${graphHeight}`} role="img" aria-label="Session 编排图">
        <defs><marker id="taskArrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#8b9bb1" /></marker></defs>
        {visibleGroups.map((group, column) => <g key={group.key}><rect className="phaseLane" x={column * 246 + 8} y="24" width="226" height={graphHeight - 38} rx="10" /><text className="phaseLaneLabel" x={column * 246 + 22} y="17">{group.label}</text></g>)}
        {edges.map((edge, index) => {
          const source = positions.get(String(edge.source_node_id ?? ""));
          const target = positions.get(String(edge.target_node_id ?? ""));
          if (!source || !target) return null;
          const sx = source.x + 210;
          const sy = source.y + 40;
          const tx = target.x;
          const ty = target.y + 40;
          const mid = (sx + tx) / 2;
          return <path className="taskGraphEdge" key={`${edge.source_node_id}-${edge.target_node_id}-${index}`} d={`M ${sx} ${sy} C ${mid} ${sy}, ${mid} ${ty}, ${tx} ${ty}`} markerEnd="url(#taskArrow)" />;
        })}
        {nodes.map((node) => {
          const nodeId = String(node.id ?? "");
          const point = positions.get(nodeId);
          if (!point) return null;
          const runId = String(node.run_id ?? "");
          const status = String(node.status ?? "unknown");
          return <g className={`taskGraphNode ${status}`} key={nodeId} transform={`translate(${point.x}, ${point.y})`} role="button" tabIndex={0} onClick={() => { if (runId) { setSelectedRunId(runId); setPage("runs"); } }}>
            <rect width="210" height="80" rx="8" />
            <text className="taskGraphNodeKey" x="12" y="19">{graphLabel(String(node.node_key ?? "-"), 23)}</text>
            <text className="taskGraphNodeTitle" x="12" y="39">{graphLabel(String(node.title ?? ""), 25)}</text>
            <text className="taskGraphNodeMeta" x="12" y="60">{graphLabel(`${String(node.assigned_agent_id ?? "-")} · ${status}`, 30)}</text>
            <text className="taskGraphNodeHint" x="12" y="73">{runId ? "点击查看 Run" : "等待依赖"}</text>
          </g>;
        })}
      </svg>
    </div>
  );
}

function MatchingReportView({ report }: { report: MatchingReport }) {
  return (
    <div className="matchingBox">
      <div className="matchingHead">
        <strong>能力匹配报告</strong>
        <Badge value={report.decision} />
        <span>分数 {report.score}</span>
      </div>
      <Signal label="已覆盖能力" value={report.covered_capabilities.join(", ") || "-"} />
      <Signal label="缺失能力" value={report.missing_capabilities.join(", ") || "-"} />
      <Signal label="冗余 Agent" value={report.redundant_agents.join(", ") || "-"} />
      {report.token_waste_warnings.length > 0 && <JsonList rows={report.token_waste_warnings.map((warning) => ({ warning }))} />}
      <p className="muted">{report.explanation}</p>
    </div>
  );
}

function SecurityPage({ security }: { security: SecurityData }) {
  return <section className="pageStack"><Panel title="策略决策"><JsonList rows={security.policy_decisions} /></Panel><section className="grid"><Panel title="委托授权"><JsonList rows={security.delegation_grants} /></Panel><Panel title="预算账本"><JsonList rows={security.budget_ledger} /></Panel></section></section>;
}

function AuditCenterPage({
  approvals,
  runs,
  audit,
  topology,
  sessions,
  selectedSessionId,
  sessionAuditReport,
  teams,
  security,
  selectedRunId,
  setSelectedRunId,
  runDetail,
  executeRun,
  controlRun,
  decideApproval,
  createDemoApproval
}: {
  approvals: Approval[];
  runs: Run[];
  audit: AuditEvent[];
  topology: Topology;
  sessions: Session[];
  selectedSessionId: string | null;
  sessionAuditReport: SessionAuditReport | null;
  teams: TeamConfig[];
  security: SecurityData;
  selectedRunId: string | null;
  setSelectedRunId: (id: string) => void;
  runDetail: RunDetail | null;
  executeRun: (id: string) => void;
  controlRun: (id: string, action: "pause" | "cancel" | "resume") => void;
  decideApproval: (approval: Approval, approved: boolean) => void;
  createDemoApproval: () => void;
}) {
  const [tab, setTab] = useState<"approvals" | "runs" | "report" | "timeline" | "topology" | "security">("approvals");
  const pending = approvals.filter((approval) => approval.status === "pending").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  return (
    <section className="pageStack">
      <section className="auditSummary">
        <StatusPill icon={<ClipboardCheck size={16} />} label="待审批" value={pending} tone={pending ? "warning" : "ok"} />
        <StatusPill icon={<AlertTriangle size={16} />} label="失败 Run" value={failed} tone={failed ? "danger" : "ok"} />
        <StatusPill icon={<ShieldCheck size={16} />} label="策略决策" value={security.policy_decisions.length} tone="neutral" />
        <StatusPill icon={<Activity size={16} />} label="审计事件" value={audit.length} tone="neutral" />
      </section>
      <Tabs
        value={tab}
        onChange={(value) => setTab(value as typeof tab)}
        items={[
          { key: "approvals", label: "人工审批" },
          { key: "runs", label: "Run 审计" },
          { key: "report", label: "Session 报告" },
          { key: "timeline", label: "事件时间线" },
          { key: "topology", label: "协作拓扑" },
          { key: "security", label: "策略与预算" }
        ]}
      />
      {tab === "approvals" && <ApprovalsPage approvals={approvals} decideApproval={decideApproval} createDemoApproval={createDemoApproval} />}
      {tab === "runs" && <RunsPage runs={runs} selectedRunId={selectedRunId} setSelectedRunId={setSelectedRunId} runDetail={runDetail} executeRun={executeRun} controlRun={controlRun} />}
      {tab === "report" && <SessionAuditReportPage report={sessionAuditReport} selectedSessionId={selectedSessionId} />}
      {tab === "timeline" && <AuditPage audit={audit} />}
      {tab === "topology" && <TopologyPage topology={topology} sessions={sessions} selectedSessionId={selectedSessionId} teams={teams} />}
      {tab === "security" && <SecurityPage security={security} />}
    </section>
  );
}

function SessionAuditReportPage({ report, selectedSessionId }: { report: SessionAuditReport | null; selectedSessionId: string | null }) {
  if (!selectedSessionId) return <Panel title="Session 审计报告"><p>请先在 Session 驾驶舱选择一个 Session。</p></Panel>;
  if (!report) return <Panel title="Session 审计报告"><p>当前 Session 的审计报告暂不可用，请确认后端已启动最新接口。</p></Panel>;
  const summary = report.summary ?? {};
  return (
    <section className="pageStack">
      <section className="auditSummary">
        <StatusPill icon={<Activity size={16} />} label="事件" value={summary.events ?? report.timeline.length} tone="neutral" />
        <StatusPill icon={<ShieldCheck size={16} />} label="策略/审批" value={report.decision_chain.length} tone="neutral" />
        <StatusPill icon={<Wrench size={16} />} label="工具调用" value={summary.tool_calls ?? report.tool_chain.length} tone="neutral" />
        <StatusPill icon={<Undo2 size={16} />} label="回滚事件" value={summary.rollback_events ?? report.rollback_chain.length} tone={report.rollback_chain.length ? "warning" : "neutral"} />
      </section>
      <section className="grid">
        <Panel title="责任链">
          <table><thead><tr><th>Agent</th><th>Run</th><th>状态</th><th>输入/错误</th></tr></thead><tbody>{report.responsibility_chain.map((row, index) => (
            <tr key={String(row.run_id ?? index)}><td>{String(row.agent_id ?? "-")}</td><td>{shortId(String(row.run_id ?? ""))}</td><td><Badge value={String(row.status ?? "unknown")} /></td><td>{displayText(String(row.error ?? row.input_summary ?? "-"))}</td></tr>
          ))}</tbody></table>
        </Panel>
        <Panel title="决策链">
          <DecisionChain rows={report.decision_chain} />
        </Panel>
      </section>
      <section className="grid">
        <Panel title="工具链">
          <ToolChain rows={report.tool_chain} />
        </Panel>
        <Panel title="产物链">
          <ArtifactChain rows={report.artifact_chain} />
        </Panel>
      </section>
      <Panel title="回滚 / 重试链">
        {report.rollback_chain.length ? <Timeline events={report.rollback_chain as AuditEvent[]} /> : <p>暂无回滚或重试事件。后续接入 rollback.requested、rollback.applied、run.retried 后会在这里形成完整链路。</p>}
      </Panel>
    </section>
  );
}

function DecisionChain({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p>暂无策略或审批记录。</p>;
  return (
    <table><thead><tr><th>类型</th><th>结果</th><th>Run</th><th>说明</th></tr></thead><tbody>{rows.slice(0, 20).map((row, index) => (
      <tr key={String(row.id ?? index)}><td>{String(row.policy_id ?? row.requested_by ?? row.kind ?? "decision")}</td><td>{String(row.decision ?? row.status ?? "-")}</td><td>{shortId(String(row.run_id ?? ""))}</td><td>{displayText(String(row.reason ?? row.explanation ?? row.created_at ?? "-"))}</td></tr>
    ))}</tbody></table>
  );
}

function ToolChain({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p>暂无工具调用。</p>;
  return (
    <table><thead><tr><th>工具</th><th>调用方</th><th>Run</th><th>结果</th></tr></thead><tbody>{rows.slice(0, 20).map((row, index) => (
      <tr key={String(row.id ?? index)}><td>{String(row.tool_id ?? row.tool_name ?? "-")}</td><td>{String(row.caller_agent_id ?? "-")}</td><td>{shortId(String(row.run_id ?? ""))}</td><td>{displayText(String(row.status ?? row.error ?? row.created_at ?? "-"))}</td></tr>
    ))}</tbody></table>
  );
}

function ArtifactChain({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p>暂无产物。</p>;
  return (
    <div className="evidenceChain">
      {rows.slice(0, 12).map((row, index) => (
        <article key={String(row.id ?? index)}>
          <span>{String(row.kind ?? row.artifact_type ?? "artifact")}</span>
          <strong>{displayText(String(row.path ?? row.uri ?? row.id ?? "-"))}</strong>
          <em>{shortId(String(row.run_id ?? "")) || formatTime(String(row.created_at ?? ""))}</em>
        </article>
      ))}
    </div>
  );
}

function ResourceCenterPage({
  configText,
  setConfigText,
  saveConfig,
  configPath,
  tools,
  skills,
  registerTool,
  registerSkill,
  registerSkillsBatch,
  scanGitHubSkills,
  searchGitHubSkills,
  agents,
  runs,
  security,
  queue,
  workerTick
}: {
  configText: string;
  setConfigText: (value: string) => void;
  saveConfig: () => void;
  configPath: string;
  tools: ToolSpec[];
  skills: SkillSpec[];
  registerTool: (tool: ToolSpec) => void;
  registerSkill: (skill: SkillSpec) => void;
  registerSkillsBatch: (skills: SkillSpec[], approved?: boolean) => void;
  scanGitHubSkills: (url: string, ref: string, subpath: string) => Promise<SkillSpec[]>;
  searchGitHubSkills: (query: string) => Promise<SkillSearchResult[]>;
  agents: Agent[];
  runs: Run[];
  security: SecurityData;
  queue: QueueData;
  workerTick: () => void;
}) {
  const [tab, setTab] = useState<"agents" | "skills" | "tools" | "config" | "runtime">("agents");
  return (
    <section className="pageStack">
      <section className="resourceSummary">
        <StatusPill icon={<Bot size={16} />} label="Agent" value={agents.length} tone="neutral" />
        <StatusPill icon={<Wrench size={16} />} label="工具" value={tools.length} tone="neutral" />
        <StatusPill icon={<Database size={16} />} label="技能" value={skills.length} tone="neutral" />
        <StatusPill icon={<ShieldCheck size={16} />} label="策略绑定" value={security.policy_decisions.length} tone="neutral" />
        <StatusPill icon={<Clock size={16} />} label="队列项" value={queue.queue.length} tone={queue.queue.length ? "warning" : "ok"} />
      </section>
      <Tabs
        value={tab}
        onChange={(value) => setTab(value as typeof tab)}
        items={[
          { key: "agents", label: "Agent 目录" },
          { key: "skills", label: "技能库" },
          { key: "tools", label: "工具中心" },
          { key: "config", label: "配置编辑" },
          { key: "runtime", label: "运行队列" }
        ]}
      />
      {tab === "agents" && <AgentsPage agents={agents} runs={runs} security={security} />}
      {tab === "skills" && <SkillLibraryPage skills={skills} registerSkill={registerSkill} registerSkillsBatch={registerSkillsBatch} scanGitHubSkills={scanGitHubSkills} searchGitHubSkills={searchGitHubSkills} />}
      {tab === "tools" && <ToolsPage tools={tools} registerTool={registerTool} />}
      {tab === "config" && <ConfigPage configText={configText} setConfigText={setConfigText} saveConfig={saveConfig} configPath={configPath} tools={tools} skills={skills} />}
      {tab === "runtime" && <QueuePage queue={queue} workerTick={workerTick} />}
    </section>
  );
}

function Tabs({ value, onChange, items }: { value: string; onChange: (value: string) => void; items: Array<{ key: string; label: string }> }) {
  return (
    <div className="pageTabs">
      {items.map((item) => (
        <button className={value === item.key ? "active" : ""} key={item.key} onClick={() => onChange(item.key)}>{item.label}</button>
      ))}
    </div>
  );
}

function LaunchReadiness({ mode, agentCount, strategy, executeNow }: { mode: string; agentCount: number; strategy: string; executeNow: boolean }) {
  return (
    <Panel title="启动预检">
      <div className="readinessCard">
        <StatusPill icon={<Bot size={16} />} label="参与 Agent" value={agentCount || "未选择"} tone={agentCount ? "ok" : "warning"} />
        <StatusPill icon={<GitBranch size={16} />} label="协作模式" value={strategy} tone="neutral" />
        <StatusPill icon={<Play size={16} />} label="执行方式" value={executeNow ? "创建后入队" : "人工启动"} tone={executeNow ? "ok" : "neutral"} />
        <StatusPill icon={<ShieldCheck size={16} />} label="治理链路" value="审计 / 预算 / 策略" tone="ok" />
      </div>
      <div className="backendPlan">
        <strong>后端待补能力</strong>
        <span>{mode === "single" ? "单 Agent 可用动作 API" : "Team 能力预检摘要 API"}</span>
        <span>Session checkpoint 与 artifact version 支持</span>
        <span>启动前预算阈值和策略 override 预览</span>
      </div>
    </Panel>
  );
}

function StatusPill({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string | number; tone: "ok" | "warning" | "danger" | "neutral" }) {
  return (
    <div className={`statusPill ${tone}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RunTable({ runs, selectedRunId, onSelect, compact = false }: { runs: Run[]; selectedRunId?: string | null; onSelect?: (id: string) => void; compact?: boolean }) {
  return <table><thead><tr><th>Agent</th><th>状态</th><th>输入</th>{!compact && <th>创建时间</th>}</tr></thead><tbody>{runs.map((run) => <tr className={selectedRunId === run.id ? "selected" : ""} key={run.id} onClick={() => onSelect?.(run.id)}><td>{run.agent_id}</td><td><Badge value={run.status} /></td><td>{displayText(run.input_summary)}</td>{!compact && <td>{formatTime(run.created_at)}</td>}</tr>)}</tbody></table>;
}

function Timeline({ events }: { events: AuditEvent[] }) {
  return <div className="timeline">{events.map((event) => <div className="timelineItem" key={event.id}><span>{event.seq}</span><div><strong>{event.event_type}</strong><p>{event.actor_id} / {event.status}</p></div></div>)}</div>;
}

function FieldGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="fieldGroup"><h3>{title}</h3><div className="chipGroup">{children}</div></div>;
}

function Chip({ checked, label, onClick }: { checked: boolean; label: string; onClick: () => void }) {
  return <button className={checked ? "chip checked" : "chip"} onClick={onClick} type="button">{label}</button>;
}

function JsonList({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <p>暂无数据。</p>;
  return <div className="jsonList">{rows.slice(0, 20).map((row, index) => <pre key={index}>{JSON.stringify(cleanJson(row), null, 2)}</pre>)}</div>;
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string | number }) {
  return <article className="metric">{icon}<span>{label}</span><strong>{value}</strong></article>;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="panel"><h2>{title}</h2>{children}</section>;
}

function Signal({ label, value }: { label: string; value: string | number }) {
  return <div className="signal"><span>{label}</span><strong>{value}</strong></div>;
}

function Badge({ value }: { value: string }) {
  return <span className={`badge ${value}`}>{value}</span>;
}

function graphLabel(value: string, maxLength: number): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}…` : normalized;
}

function pageMetadata(page: PageKey) {
  const copy: Record<PageKey, { title: string; description: string }> = {
    overview: {
      title: "治理工作台",
      description: "集中处理待审批、失败、阻塞和运行中 Session，让操作者先看到需要介入的事项。"
    },
    dispatch: {
      title: "交给 Leader",
      description: "描述最终目标，Leader 负责规划、拆分、委派和申请能力。"
    },
    sessions: {
      title: "Session 驾驶舱",
      description: "围绕一次任务查看阶段、编排、风险、产物、预算和人工控制动作。"
    },
    knowledge: {
      title: "知识中心",
      description: "管理 Session 资料、Leader 访问计划和可引用证据。"
    },
    evolution: {
      title: "进化实验室",
      description: "把成功 Session 里的经验变成可评估、可审批、可回滚的候选版本。"
    },
    auditCenter: {
      title: "审计中心",
      description: "集中查看审批、Run、事件、拓扑、策略和预算证据链。"
    },
    resources: {
      title: "资源配置",
      description: "维护 Agent、工具、配置和运行队列，让治理能力可持续复用。"
    },
    config: {
      title: "Agent 配置",
      description: "维护长期能力模板、模型、工具、沙箱和策略绑定。"
    },
    tools: {
      title: "工具中心",
      description: "注册和检查工具风险等级、执行器、审批要求和输入结构。"
    },
    agents: {
      title: "Agent 目录",
      description: "查看 Agent 能力、工具权限、沙箱绑定和最近运行表现。"
    },
    runs: {
      title: "Run 审计",
      description: "深入单次执行，追踪模型调用、工具调用、策略、预算和错误原因。"
    },
    approvals: {
      title: "人工审批",
      description: "处理高风险工具、写入动作和策略要求的人类确认。"
    },
    audit: {
      title: "事件日志",
      description: "按时间查看 append-only 审计事件。"
    },
    topology: {
      title: "协作拓扑",
      description: "从 Session、Team 和 Agent 维度查看协作关系。"
    },
    queue: {
      title: "运行队列",
      description: "检查 worker、lease 和待执行 Run。"
    },
    security: {
      title: "安全策略",
      description: "查看策略决策、委托授权和预算账本。"
    }
  };
  return copy[page];
}

function sessionPhase(status: string, failedRuns: number, pendingRuns: number) {
  if (failedRuns > 0 || status === "failed") return 1;
  if (status === "awaiting_approval") return 2;
  if (status === "completed") return 4;
  if (pendingRuns > 0 || ["running", "pending", "paused"].includes(status)) return 1;
  return 0;
}

function parseConfig(text: string): Record<string, unknown> | null {
  try { return JSON.parse(text) as Record<string, unknown>; } catch { return null; }
}

function asList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : [];
}

function emptyAgentForm(): AgentForm {
  return { id: "", name: "", provider: "", model: "", tools: [], skills: [], sandbox: "", policies: [], system_prompt: "" };
}

function agentToForm(agent: Record<string, unknown>): AgentForm {
  return {
    id: String(agent.id ?? ""),
    name: String(agent.name ?? ""),
    provider: String(agent.provider ?? ""),
    model: String(agent.model ?? ""),
    tools: Array.isArray(agent.tools) ? agent.tools.map(String) : [],
    skills: Array.isArray(agent.skills) ? agent.skills.map(String) : [],
    sandbox: agent.sandbox ? String(agent.sandbox) : "",
    policies: Array.isArray(agent.policies) ? agent.policies.map(String) : [],
    system_prompt: String(agent.system_prompt ?? "")
  };
}

function providerModels(providers: Array<Record<string, unknown>>, providerName: string): string[] {
  const provider = providers.find((item) => item.name === providerName);
  const models = Array.isArray(provider?.models) ? provider.models as Array<Record<string, unknown>> : [];
  return models.map((model) => String(model.name ?? "")).filter(Boolean);
}

function unique(value: string, index: number, array: string[]) {
  return array.indexOf(value) === index;
}

function displayText(value?: string | null) {
  if (!value) return "-";
  if (/^\?{3,}$/.test(value.trim())) return "历史编码损坏记录";
  if (/[脙脗氓忙莽猫茅盲枚眉ÃÂåæçèéäöü]/.test(value)) {
    try {
      const bytes = Uint8Array.from(Array.from(value, (char) => char.charCodeAt(0) & 0xff));
      const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      if (decoded && !/[�]/.test(decoded)) return decoded;
    } catch {
      return value;
    }
  }
  return value;
}

function cleanJson(value: unknown): unknown {
  if (typeof value === "string") return displayText(value);
  if (Array.isArray(value)) return value.map(cleanJson);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, cleanJson(item)]));
  }
  return value;
}

function shortId(value: string) {
  return value ? value.slice(0, 8) : "-";
}

function formatTime(value?: string) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN");
}
