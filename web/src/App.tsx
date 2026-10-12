import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Clock,
  FileText,
  GitBranch,
  Play,
  RefreshCw,
  Send,
  Settings,
  ShieldCheck,
  WalletCards,
  Wrench
} from "lucide-react";
import { Agent, Approval, AuditEvent, getJson, Overview, postJson, putJson, Run, Session } from "./api";
import "./styles.css";

type PageKey = "overview" | "config" | "tools" | "dispatch" | "sessions" | "agents" | "runs" | "approvals" | "audit" | "topology" | "queue" | "security";
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
};
type SessionDetail = {
  session: Session | null;
  runs: Run[];
  steps: AuditEvent[];
  messages: Array<Record<string, unknown>>;
  model_calls: Array<Record<string, unknown>>;
  tool_calls: Array<Record<string, unknown>>;
  action_intents?: Array<Record<string, unknown>>;
  observations?: Array<Record<string, unknown>>;
  budget_ledger: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  artifacts?: Array<Record<string, unknown>>;
  matching_reports?: Array<Record<string, unknown>>;
  team_snapshot?: Record<string, unknown> | null;
};
type PlatformConfigResponse = { path: string; config: Record<string, unknown>; note: string };
type AgentForm = {
  id: string;
  name: string;
  provider: string;
  model: string;
  tools: string[];
  sandbox: string;
  policies: string[];
  system_prompt: string;
};

const navItems: Array<{ key: PageKey; label: string }> = [
  { key: "overview", label: "总览" },
  { key: "config", label: "配置中心" },
  { key: "tools", label: "工具中心" },
  { key: "dispatch", label: "任务发配" },
  { key: "sessions", label: "Session 复盘" },
  { key: "agents", label: "Agent 视角" },
  { key: "runs", label: "Run 审计" },
  { key: "approvals", label: "人工审批" },
  { key: "audit", label: "事件日志" },
  { key: "topology", label: "协作拓扑" },
  { key: "queue", label: "队列" },
  { key: "security", label: "安全策略" }
];

const knownTools = ["repo_search", "repo_read", "repo_list", "file_read", "file_write", "local_command"];

export default function App() {
  const [page, setPage] = useState<PageKey>("overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tools, setTools] = useState<ToolSpec[]>([]);
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

  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) ?? runs[0], [runs, selectedRunId]);
  const selectedSession = useMemo(() => sessions.find((item) => item.id === selectedSessionId) ?? sessions[0], [sessions, selectedSessionId]);

  async function refresh() {
    const [overviewData, agentData, toolData, sessionData, runData, approvalData, auditData, topologyData, queueData, securityData, configData] = await Promise.all([
      getJson<Overview>("/dashboard/overview"),
      getJson<Agent[]>("/agents"),
      getJson<ToolSpec[]>("/tools"),
      getJson<Session[]>("/sessions"),
      getJson<Run[]>("/runs"),
      getJson<Approval[]>("/approvals"),
      getJson<AuditEvent[]>("/dashboard/audit"),
      getJson<Topology>("/dashboard/topology"),
      getJson<QueueData>("/dashboard/queue"),
      getJson<SecurityData>("/dashboard/security"),
      getJson<PlatformConfigResponse>("/config")
    ]);
    setOverview(overviewData);
    setAgents(agentData);
    setTools(toolData);
    setSessions(sessionData);
    setRuns(runData);
    setApprovals(approvalData);
    setAudit(auditData);
    setTopology(topologyData);
    setQueue(queueData);
    setSecurity(securityData);
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
    const sessionId = selectedSessionId ?? sessionData[0]?.id;
    if (sessionId) {
      setSelectedSessionId(sessionId);
      setSessionDetail(await getJson<SessionDetail>(`/dashboard/sessions/${sessionId}`));
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
    getJson<SessionDetail>(`/dashboard/sessions/${selectedSession.id}`).then(setSessionDetail).catch(() => undefined);
  }, [selectedSession?.id]);

  useEffect(() => {
    if (!selectedSession?.id) return;
    setLiveSessionEvents([]);
    const source = new EventSource(`/events/sessions/${selectedSession.id}`);
    source.onmessage = (event) => {
      if (!event.data) return;
      try {
        const parsed = JSON.parse(event.data) as AuditEvent;
        setLiveSessionEvents((current) => current.some((item) => item.id === parsed.id) ? current : [...current, parsed].slice(-120));
      } catch {
        // SSE heartbeat; persisted history is still loaded through session detail.
      }
    };
    source.addEventListener("run.final", () => {
      getJson<SessionDetail>(`/dashboard/sessions/${selectedSession.id}`).then(setSessionDetail).catch(() => undefined);
    });
    source.onerror = () => source.close();
    return () => source.close();
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

  async function controlSession(sessionId: string, action: "pause" | "cancel" | "resume" | "execute-pending") {
    const label = action === "pause" ? "暂停" : action === "cancel" ? "取消" : action === "resume" ? "恢复" : "执行待处理 Run";
    setNotice(`正在${label} Session...`);
    const result = await postJson<Record<string, unknown>>(
      `/sessions/${sessionId}/${action}`,
      action === "execute-pending" ? {} : { reason: `控制台${label}`, execute_now: false }
    );
    await refresh();
    setNotice(`Session 操作完成：${String(result.status ?? result.executed ?? "ok")}`);
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

  async function dispatchTask(agentId: string, title: string, inputSummary: string, executeNow: boolean) {
    setNotice("正在发配任务...");
    const result = await postJson<{ run_id: string; session_id: string; status: string; result?: { error?: string } }>("/tasks/dispatch", {
      title,
      owner_id: "operator",
      agent_id: agentId,
      input_summary: inputSummary,
      execute_now: executeNow
    });
    await refresh();
    setSelectedRunId(result.run_id);
    setSelectedSessionId(result.session_id);
    setPage("runs");
    setNotice(result.status === "failed" ? `任务执行失败：${result.result?.error ?? "请查看 Run 详情"}` : "任务已创建，审计记录已生成");
  }

  async function dispatchTeamTask(teamId: string, strategy: string, title: string, inputSummary: string, executeNow: boolean) {
    setNotice("正在发配多 Agent Team 任务...");
    const result = await postJson<{ session_id?: string; parent_run_id?: string; run_ids?: string[]; status: string; matching?: MatchingReport; report?: MatchingReport; blocked?: boolean }>("/tasks/dispatch-team", {
      title,
      owner_id: "operator",
      team_id: teamId,
      strategy,
      input_summary: inputSummary,
      execute_mode: executeNow ? "enqueue" : "manual"
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

  async function dispatchAdHocTeamTask(leader: string, members: string[], strategy: string, title: string, inputSummary: string, executeNow: boolean) {
    setNotice("正在创建临时多 Agent Session...");
    const result = await postJson<{ session_id?: string; parent_run_id?: string; run_ids?: string[]; status: string; matching?: MatchingReport; report?: MatchingReport; blocked?: boolean }>("/tasks/dispatch-ad-hoc-team", {
      title,
      owner_id: "operator",
      leader,
      members,
      strategy,
      input_summary: inputSummary,
      execute_mode: executeNow ? "enqueue" : "manual"
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
    await postJson(`/approvals/${approval.id}/decide`, {
      approved,
      approver_id: "operator",
      reason: approved ? "控制台审批通过" : "控制台审批拒绝"
    });
    await refresh();
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

  return (
    <main className="shell">
      <aside className="nav">
        <div className="brand"><ShieldCheck size={22} /> AgentGov</div>
        {navItems.map((item) => (
          <button className={page === item.key ? "active" : ""} key={item.key} onClick={() => setPage(item.key)}>{item.label}</button>
        ))}
      </aside>
      <section className="content">
        <header className="topbar">
          <div>
            <h1>Agent 治理控制台</h1>
            <p>配置 Agent 能力，发配任务，按 Session 和 Run 追踪模型调用、工具调用、文件产物、预算和审批。</p>
          </div>
          <button className="iconButton" onClick={() => refresh()} title="刷新数据"><RefreshCw size={18} /></button>
        </header>
        <div className="notice">{notice}</div>

        {page === "overview" && <OverviewPage overview={overview} agents={agents} sessions={sessions} runs={runs} approvals={approvals} audit={audit} runStoryDemo={runStoryDemo} />}
        {page === "config" && <ConfigPage configText={configText} setConfigText={setConfigText} saveConfig={saveConfig} configPath={configPath} tools={tools} />}
        {page === "tools" && <ToolsPage tools={tools} registerTool={registerTool} />}
        {page === "dispatch" && <DispatchPage agents={agents} teams={teams} latestMatching={latestMatching} dispatchTask={dispatchTask} dispatchTeamTask={dispatchTeamTask} dispatchAdHocTeamTask={dispatchAdHocTeamTask} runStoryDemo={runStoryDemo} />}
        {page === "sessions" && <SessionCockpitPage sessions={sessions} selectedSessionId={selectedSession?.id ?? null} setSelectedSessionId={setSelectedSessionId} detail={sessionDetail} liveEvents={liveSessionEvents} setSelectedRunId={setSelectedRunId} setPage={setPage} controlSession={controlSession} saveTeamTemplate={saveTeamTemplate} />}
        {page === "agents" && <AgentsPage agents={agents} runs={runs} security={security} />}
        {page === "runs" && <RunsPage runs={runs} selectedRunId={selectedRun?.id ?? null} setSelectedRunId={setSelectedRunId} runDetail={runDetail} executeRun={executeRun} controlRun={controlRun} />}
        {page === "approvals" && <ApprovalsPage approvals={approvals} decideApproval={decideApproval} createDemoApproval={createDemoApproval} />}
        {page === "audit" && <AuditPage audit={audit} />}
        {page === "topology" && <TopologyPage topology={topology} sessions={sessions} selectedSessionId={selectedSession?.id ?? null} teams={teams} />}
        {page === "queue" && <QueuePage queue={queue} workerTick={workerTick} />}
        {page === "security" && <SecurityPage security={security} />}
      </section>
    </main>
  );
}

function OverviewPage({ overview, agents, sessions, runs, approvals, audit, runStoryDemo }: { overview: Overview | null; agents: Agent[]; sessions: Session[]; runs: Run[]; approvals: Approval[]; audit: AuditEvent[]; runStoryDemo: () => void }) {
  return (
    <section className="pageStack">
      <section className="metrics">
        <Metric icon={<Bot />} label="Agent 数量" value={agents.length} />
        <Metric icon={<GitBranch />} label="Session 数量" value={sessions.length} />
        <Metric icon={<Activity />} label="Run 总数" value={overview?.runs ?? 0} />
        <Metric icon={<Clock />} label="运行中" value={overview?.running ?? 0} />
        <Metric icon={<CheckCircle2 />} label="已完成" value={overview?.completed ?? 0} />
        <Metric icon={<WalletCards />} label="成本 USD" value={(overview?.cost_usd ?? 0).toFixed(4)} />
      </section>
      <section className="grid">
        <Panel title="最近运行"><RunTable runs={runs.slice(0, 8)} compact /></Panel>
        <Panel title="合格线演示">
          <p className="muted">创建一个 Session：故事写作 Agent 写入 `story.md`，故事评价 Agent 读取它并写入 `review.md`，全程可追踪。</p>
          <div className="panelToolbar left"><button className="primaryButton" onClick={runStoryDemo}><FileText size={16} />运行故事 Session</button></div>
          <Signal label="待审批" value={approvals.length} />
          <Signal label="审计事件" value={audit.length} />
          <Signal label="失败 Run" value={overview?.failed ?? 0} />
        </Panel>
      </section>
    </section>
  );
}

function ConfigPage({ configText, setConfigText, saveConfig, configPath, tools }: { configText: string; setConfigText: (value: string) => void; saveConfig: () => void; configPath: string; tools: ToolSpec[] }) {
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
      sandbox: sandboxOptions[0] ?? "",
      policies: policyOptions[0] ? [policyOptions[0]] : [],
      system_prompt: "你是受治理平台约束的编程 Agent。所有文件写入必须进入当前 Session 工作区，所有结论必须可追溯。"
    });
  }

  function toggleList(field: "tools" | "policies", value: string) {
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
        <div className="toolGrid">
          {tools.map((tool) => (
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

function DispatchPage({
  agents,
  teams,
  latestMatching,
  dispatchTask,
  dispatchTeamTask,
  dispatchAdHocTeamTask,
  runStoryDemo
}: {
  agents: Agent[];
  teams: TeamConfig[];
  latestMatching: MatchingReport | null;
  dispatchTask: (agentId: string, title: string, inputSummary: string, executeNow: boolean) => void;
  dispatchTeamTask: (teamId: string, strategy: string, title: string, inputSummary: string, executeNow: boolean) => void;
  dispatchAdHocTeamTask: (leader: string, members: string[], strategy: string, title: string, inputSummary: string, executeNow: boolean) => void;
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

  return (
    <section className="pageStack">
      <Panel title="临时选择多个 Agent 组队">
        <div className="explain"><GitBranch size={18} /><span>这里创建的是一次性的协作 Session：先生成父 Run 和子 Run，再到 Session 复盘 / 协作拓扑里执行、暂停、审计和介入。</span></div>
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
          <button className="primaryButton" disabled={selectedMembers.length < 2 || !leaderId} onClick={() => dispatchAdHocTeamTask(leaderId, selectedMembers, adHocStrategy, adHocTitle, adHocInput, adHocExecuteNow)}>
            <GitBranch size={16} />创建临时 Team Session
          </button>
          <Signal label="已选 Agent" value={selectedMembers.length} />
        </div>
        {latestMatching && <MatchingReportView report={latestMatching} />}
      </Panel>
      <section className="grid">
      <Panel title="发配单 Agent 任务">
        <div className="formGrid">
          <label>目标 Agent</label>
          <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>{agents.map((agent) => <option value={agent.id} key={agent.id}>{displayText(agent.name)} ({agent.id})</option>)}</select>
          <label>任务标题</label><input value={title} onChange={(event) => setTitle(event.target.value)} />
          <label>任务输入</label><textarea value={input} onChange={(event) => setInput(event.target.value)} />
          <label className="checkLine"><input type="checkbox" checked={executeNow} onChange={(event) => setExecuteNow(event.target.checked)} />创建后立即执行</label>
        </div>
        <div className="panelToolbar"><button className="primaryButton" onClick={() => dispatchTask(agentId, title, input, executeNow)}><Send size={16} />发配任务</button></div>
      </Panel>
      <Panel title="按预定义 Team 模板发配">
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
          <button className="primaryButton" disabled={!teamId} onClick={() => dispatchTeamTask(teamId, strategy, teamTitle, teamInput, teamExecuteNow)}><GitBranch size={16} />创建 Team Session</button>
          <button className="primaryButton" onClick={runStoryDemo}><Play size={16} />运行故事示例</button>
        </div>
        <Signal label="Team 定义" value="静态协作拓扑" />
        <Signal label="Session 图" value="本次任务真实流转" />
        <Signal label="Run / Step" value="可审计执行明细" />
      </Panel>
      </section>
    </section>
  );
}

function SessionCockpitPage({
  sessions,
  selectedSessionId,
  setSelectedSessionId,
  detail,
  liveEvents,
  setSelectedRunId,
  setPage,
  controlSession,
  saveTeamTemplate
}: {
  sessions: Session[];
  selectedSessionId: string | null;
  setSelectedSessionId: (id: string) => void;
  detail: SessionDetail | null;
  liveEvents: AuditEvent[];
  setSelectedRunId: (id: string) => void;
  setPage: (page: PageKey) => void;
  controlSession: (sessionId: string, action: "pause" | "cancel" | "resume" | "execute-pending") => void;
  saveTeamTemplate: (sessionId: string) => void;
}) {
  const report = detail?.matching_reports?.[0] as MatchingReport | undefined;
  const events = liveEvents.length ? liveEvents : detail?.steps ?? [];
  return (
    <section className="split cockpit">
      <Panel title="Session 列表">
        <table><thead><tr><th>标题</th><th>状态</th><th>Root Agent</th><th>创建时间</th></tr></thead><tbody>{sessions.map((session) => (
          <tr className={selectedSessionId === session.id ? "selected" : ""} key={session.id} onClick={() => setSelectedSessionId(session.id)}>
            <td>{displayText(session.title)}</td><td><Badge value={session.status} /></td><td>{session.root_agent_id || "-"}</td><td>{formatTime(session.created_at)}</td>
          </tr>
        ))}</tbody></table>
      </Panel>
      <section className="pageStack">
        <Panel title="Session 驾驶舱">
          {detail?.session ? (
            <div className="detail">
              <div className="detailHead">
                <div><h3>{displayText(detail.session.title)}</h3><p>{displayText(detail.session.context_summary || "暂无上下文摘要")}</p></div>
                <div className="actions">
                  <button onClick={() => controlSession(detail.session!.id, "execute-pending")}><Play size={15} />执行待处理</button>
                  <button onClick={() => controlSession(detail.session!.id, "pause")}>暂停</button>
                  <button onClick={() => controlSession(detail.session!.id, "resume")}>恢复</button>
                  <button onClick={() => controlSession(detail.session!.id, "cancel")}>取消</button>
                  <button onClick={() => saveTeamTemplate(detail.session!.id)}>保存团队</button>
                </div>
              </div>
              <div className="signalGrid">
                <Signal label="Session ID" value={shortId(detail.session.id)} />
                <Signal label="状态" value={detail.session.status} />
                <Signal label="Team" value={detail.session.team_id || "临时/单 Agent"} />
                <Signal label="Run 数量" value={detail.runs.length} />
                <Signal label="模型调用" value={detail.model_calls.length} />
                <Signal label="工具调用" value={detail.tool_calls.length} />
                <Signal label="产物" value={detail.artifacts?.length ?? 0} />
                <Signal label="Agent 消息" value={detail.messages.length} />
              </div>
            </div>
          ) : <p>请选择一个 Session。</p>}
        </Panel>
        {detail?.session && (
          <section className="grid">
            <Panel title="能力匹配 / 团队快照">
              {report ? <MatchingReportView report={report} /> : <p>暂无匹配报告。</p>}
              <h3>本次团队快照</h3>
              <JsonList rows={detail.team_snapshot ? [detail.team_snapshot] : []} />
            </Panel>
            <Panel title="实时事件流">
              <Timeline events={events} />
            </Panel>
          </section>
        )}
        {detail?.session && (
          <section className="grid">
            <Panel title="本 Session 的 Run">
              <RunTable runs={detail.runs} onSelect={(id) => { setSelectedRunId(id); setPage("runs"); }} compact />
            </Panel>
            <Panel title="Agent 通信">
              <JsonList rows={detail.messages} />
            </Panel>
          </section>
        )}
        {detail?.session && (
          <section className="grid">
            <Panel title="文件产物">
              <JsonList rows={detail.artifacts ?? []} />
            </Panel>
            <Panel title="模型 / 工具 / 预算">
              <JsonList rows={[...detail.model_calls, ...detail.tool_calls, ...(detail.action_intents ?? []), ...(detail.observations ?? []), ...detail.budget_ledger]} />
            </Panel>
          </section>
        )}
      </section>
    </section>
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
  controlRun
}: {
  runs: Run[];
  selectedRunId: string | null;
  setSelectedRunId: (id: string) => void;
  runDetail: RunDetail | null;
  executeRun: (id: string) => void;
  controlRun: (id: string, action: "pause" | "cancel" | "resume") => void;
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
          <div className="graph">
            {visibleGraph.nodes.map((node) => (
              <button className={`node ${node.type} ${node.status ?? ""}`} key={node.id} onClick={() => setSelectedNode(node)}>
                <span>{node.type}</span>
                <strong>{displayText(node.label ?? node.id)}</strong>
                {node.status && <em>{node.status}</em>}
              </button>
            ))}
          </div>
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

function parseConfig(text: string): Record<string, unknown> | null {
  try { return JSON.parse(text) as Record<string, unknown>; } catch { return null; }
}

function asList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value as Array<Record<string, unknown>> : [];
}

function emptyAgentForm(): AgentForm {
  return { id: "", name: "", provider: "", model: "", tools: [], sandbox: "", policies: [], system_prompt: "" };
}

function agentToForm(agent: Record<string, unknown>): AgentForm {
  return {
    id: String(agent.id ?? ""),
    name: String(agent.name ?? ""),
    provider: String(agent.provider ?? ""),
    model: String(agent.model ?? ""),
    tools: Array.isArray(agent.tools) ? agent.tools.map(String) : [],
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
