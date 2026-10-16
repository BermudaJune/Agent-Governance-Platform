import React, { useEffect, useState } from "react";
import { Archive, ArrowRight, CheckCircle2, FileText, Search } from "lucide-react";
import { getJson, postJson } from "./api";

type CaseRecord = {
  id: string;
  session_id: string;
  snapshot_key: string;
  outcome: "accepted" | "failed" | "cancelled";
  notes: string;
  satisfaction: number | null;
  reusable_guidance: string;
  share_scope: string;
  tags: string[];
  created_at: string;
  case_data: {
    title: string;
    objective: string;
    metrics: { model_calls: number; failed_model_calls: number; agent_messages: number; input_tokens: number; output_tokens: number; cost_usd: number };
    requirements: Array<{ id: string; version: number; change_reason: string }>;
    plans: Array<{ id: string; version: number }>;
    corrections: Array<{ id: string; message: string; reason_type: string }>;
    artifact_refs: Array<{ id: string; path: string; summary: string }>;
    artifact_version_refs: Array<{ id: string; path: string; version: number }>;
    audit_step_ids: string[];
    decision_refs: Array<{ id: string; event_type: string }>;
  };
};

type ReviewState = {
  snapshot_key: string;
  execution_status: string;
  can_accept: boolean;
  can_close: boolean;
  current_case: CaseRecord | null;
  cases: CaseRecord[];
  recalled_cases: Array<{ case_id: string; source_session_id: string; guidance: string; outcome: string; tags: string[] }>;
};

const outcomes: Record<string, string> = { accepted: "已验收", failed: "失败归档", cancelled: "取消归档" };
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error);

function CaseFacts({ record, openSession }: { record: CaseRecord; openSession?: (id: string) => void }) {
  const data = record.case_data;
  return <div className="caseFacts">
    <div className="caseFactsHeading"><span className="caseOutcome">{outcomes[record.outcome]}</span><time>{new Date(record.created_at).toLocaleString()}</time><code title={record.id}>{record.id.slice(0, 8)}</code></div>
    {record.notes && <p>{record.notes}</p>}
    <dl className="caseMetrics">
      <div><dt>模型调用</dt><dd>{data.metrics.model_calls}</dd></div>
      <div><dt>通信</dt><dd>{data.metrics.agent_messages}</dd></div>
      <div><dt>Token</dt><dd>{data.metrics.input_tokens + data.metrics.output_tokens}</dd></div>
      <div><dt>模型费用</dt><dd>${data.metrics.cost_usd.toFixed(4)}</dd></div>
      <div><dt>满意度</dt><dd>{record.satisfaction ? `${record.satisfaction} / 5` : "未评分"}</dd></div>
    </dl>
    <div className="caseVersions"><span>需求 {data.requirements.map(item => `v${item.version}`).join(" / ") || "无"}</span><span>计划 {data.plans.map(item => `v${item.version}`).join(" / ") || "无"}</span><span>{data.audit_step_ids.length} 条审计引用</span><span>{data.artifact_version_refs.length} 个产物版本</span></div>
    {data.corrections.length > 0 && <details><summary>需求校正 · {data.corrections.length}</summary>{data.corrections.map(item => <p key={item.id}>{item.message}</p>)}</details>}
    {data.artifact_refs.length > 0 && <details><summary>交付产物 · {data.artifact_refs.length}</summary>{data.artifact_refs.map(item => <p key={item.id}><FileText size={14} /><code>{item.path}</code><span>{item.summary}</span></p>)}</details>}
    <details><summary>版本与审计来源</summary><div className="caseSourceRefs">{data.requirements.map(item => <span key={item.id}>需求 v{item.version} <code>{item.id}</code></span>)}{data.plans.map(item => <span key={item.id}>计划 v{item.version} <code>{item.id}</code></span>)}{data.decision_refs.map(item => <span key={item.id}>{item.event_type} <code>{item.id}</code></span>)}</div></details>
    {record.reusable_guidance && <blockquote><strong>{record.share_scope === "shared_methods" ? "已允许后续任务参考的方法" : "仅此案例保存的方法"}</strong><p>{record.reusable_guidance}</p></blockquote>}
    {openSession && <button onClick={() => openSession(record.session_id)}><ArrowRight size={14} />打开来源 Session</button>}
  </div>;
}

export function SessionReviewPanel({ sessionId, revision, openSession, continueEditing }: {
  sessionId: string; revision: string; openSession: (id: string) => void; continueEditing: () => void;
}) {
  const [state, setState] = useState<ReviewState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState("");
  const [guidance, setGuidance] = useState("");
  const [sharing, setSharing] = useState(false);
  const [tags, setTags] = useState("");
  const [satisfaction, setSatisfaction] = useState("");
  const [target, setTarget] = useState("");
  useEffect(() => {
    let active = true;
    getJson<ReviewState>(`/sessions/${sessionId}/review`).then(data => { if (active) { setState(data); setError(""); } }).catch(err => { if (active) setError(errorText(err)); });
    return () => { active = false; };
  }, [sessionId, revision]);

  async function archive() {
    if (!state) return;
    setBusy(true); setError("");
    try {
      await postJson(`/sessions/${sessionId}/review`, {
        snapshot_key: state.snapshot_key,
        outcome: state.can_accept ? "accepted" : state.execution_status,
        notes, reusable_guidance: guidance, share_scope: sharing ? "shared_methods" : "private",
        satisfaction: satisfaction ? Number(satisfaction) : null,
        tags: tags.split(/[,，]/).map(tag => tag.trim()).filter(Boolean), proposal_target: target || null
      });
      setState(await getJson<ReviewState>(`/sessions/${sessionId}/review`));
    } catch (err) {
      setError(errorText(err));
      // A stale snapshot must be refreshed before the user can submit again.
      try { setState(await getJson<ReviewState>(`/sessions/${sessionId}/review`)); } catch { /* Keep the original error visible. */ }
    } finally { setBusy(false); }
  }

  return <section className="panel sessionReviewPanel" aria-label="交付验收与经验">
    <div className="panelHeader"><h2>交付验收与经验</h2><Archive size={18} /></div>
    {error && <p role="alert" className="learningError">{error}</p>}
    {!state ? <p className="muted">正在读取当前交付版本...</p> : <>
      {state.current_case ? <><CaseFacts record={state.current_case} /><button onClick={continueEditing}><ArrowRight size={15} />继续调整</button></> : state.can_accept || state.can_close ? <div className="reviewForm">
        <div className="reviewHeading"><strong>{state.can_accept ? "执行完成，等待你的验收" : "任务已结束，可保留失败或取消记录"}</strong><code title={state.snapshot_key}>版本 {state.snapshot_key.slice(0, 8)}</code></div>
        <label>验收备注<textarea aria-label="验收备注" disabled={busy} rows={2} value={notes} maxLength={5000} onChange={event => setNotes(event.target.value)} /></label>
        <div className="reviewOptions"><label>满意度<select aria-label="满意度" disabled={busy} value={satisfaction} onChange={event => setSatisfaction(event.target.value)}><option value="">未评分</option>{[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value} / 5</option>)}</select></label><label>任务标签<input aria-label="任务标签" disabled={busy} value={tags} onChange={event => setTags(event.target.value)} placeholder="如：写作，天气" /></label></div>
        <details><summary>沉淀可复用方法（可选）</summary><div className="reviewMethod">
          <label>方法与适用边界<textarea aria-label="可复用方法" disabled={busy} rows={3} maxLength={1500} value={guidance} onChange={event => setGuidance(event.target.value)} /></label>
          <label className="reviewShare"><input type="checkbox" disabled={busy || !guidance.trim()} checked={sharing} onChange={event => setSharing(event.target.checked)} />允许新的 Session 参考这段方法</label>
          <label>提出进化候选<select aria-label="进化候选类型" disabled={busy || !guidance.trim()} value={target} onChange={event => setTarget(event.target.value)}><option value="">仅保存案例</option><option value="leader_general">Leader 通用规则</option><option value="task_strategy">分类任务策略</option><option value="agent_template">Agent 模板</option><option value="skill">Skill 使用方法</option><option value="tool">Tool 使用方法</option><option value="policy">治理策略</option></select></label>
        </div></details>
        <div className="reviewActions"><button className="primaryButton" disabled={busy || (sharing && !guidance.trim())} onClick={archive}><CheckCircle2 size={15} />{busy ? "正在归档..." : state.can_accept ? "确认验收并归档" : "归档结束记录"}</button><button disabled={busy} onClick={continueEditing}><ArrowRight size={15} />继续调整</button></div>
      </div> : <p className="muted">{state.cases.length ? "任务已更新，上次验收仅对应历史版本。" : "等待执行与审批完成。"}</p>}
      {state.cases.filter(record => record.id !== state.current_case?.id).length > 0 && <details className="reviewHistory"><summary>历史验收 · {state.cases.filter(record => record.id !== state.current_case?.id).length}</summary>{state.cases.filter(record => record.id !== state.current_case?.id).map(record => <CaseFacts key={record.id} record={record} />)}</details>}
      {state.recalled_cases.length > 0 && <div className="recalledMethods"><h3>Leader 收到的历史方法</h3>{state.recalled_cases.map(record => <article key={record.case_id}><p>{record.guidance}</p><span>{outcomes[record.outcome]} · {record.tags.join("、")} · <code>{record.case_id.slice(0, 8)}</code></span><button onClick={() => openSession(record.source_session_id)}><ArrowRight size={14} />查看来源</button></article>)}</div>}
    </>}
  </section>;
}

export function CaseLibrary({ ownerId, openSession }: { ownerId: string; openSession: (id: string) => void }) {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      getJson<{ cases: CaseRecord[] }>(`/memory/cases?owner_id=${encodeURIComponent(ownerId)}&q=${encodeURIComponent(query)}`).then(data => { if (active) { setCases(data.cases); setError(""); } }).catch(err => { if (active) setError(errorText(err)); }).finally(() => { if (active) setLoading(false); });
    }, 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [ownerId, query]);
  async function toggleSharing(record: CaseRecord) {
    setBusy(record.id); setError("");
    try {
      const updated = await postJson<CaseRecord>(`/memory/cases/${record.id}/sharing`, { share_scope: record.share_scope === "private" ? "shared_methods" : "private" });
      setCases(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (err) { setError(errorText(err)); } finally { setBusy(""); }
  }
  return <section className="panel caseLibrary">
    <div className="panelHeader"><h2>历史案例</h2><label className="caseSearch"><Search size={16} /><input aria-label="搜索历史案例" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索任务、标签或方法" maxLength={200} /></label></div>
    {error && <p role="alert" className="learningError">{error}</p>}
    {loading ? <p className="muted">正在检索案例...</p> : cases.length ? <div className="caseLibraryList">{cases.map(record => <details key={record.id}><summary><span><strong>{record.case_data.title}</strong><small>{record.tags.join(" · ") || "未分类"}</small></span><span>{outcomes[record.outcome]}</span><span>{record.share_scope === "private" ? "私有" : "共享方法"}</span></summary><CaseFacts record={record} openSession={openSession} />{record.reusable_guidance && <label className="reviewShare"><input type="checkbox" checked={record.share_scope === "shared_methods"} disabled={!!busy} onChange={() => toggleSharing(record)} />允许后续新 Session 参考方法{busy === record.id ? " · 保存中" : ""}</label>}</details>)}</div> : <p className="emptyState">{query ? "没有匹配的案例。" : "暂无归档案例。"}</p>}
  </section>;
}
