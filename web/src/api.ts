export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    throw new Error(`接口没有返回 JSON：${text.slice(0, 80)}`);
  }
  return response.json() as Promise<T>;
}

export type Overview = {
  runs: number;
  running: number;
  completed: number;
  failed: number;
  rejected: number;
  pending_approvals: number;
  cost_usd: number;
  agent_messages: number;
  policy_decisions: number;
};

export type Agent = {
  id: string;
  name: string;
  provider: string;
  model: string;
  tools: string[];
  sandbox?: string;
};

export type Run = {
  id: string;
  session_id: string;
  parent_run_id?: string | null;
  agent_id: string;
  status: string;
  input_summary: string;
  output_summary?: string | null;
  error?: string | null;
  created_at: string;
};

export type Session = {
  id: string;
  title: string;
  owner_id: string;
  root_agent_id?: string | null;
  team_id?: string | null;
  status: string;
  context_summary?: string | null;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: string;
  run_id: string;
  event_type: string;
  actor_id: string;
  actor_type: string;
  status: string;
  seq: number;
  payload?: Record<string, unknown>;
  created_at: string;
};

export type Approval = {
  id: string;
  run_id: string;
  status: string;
  requested_by: string;
  approver_id?: string | null;
  reason?: string | null;
  created_at: string;
};

export async function postJson<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text.slice(0, 200)}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    throw new Error(`接口没有返回 JSON：${text.slice(0, 80)}`);
  }
  return response.json() as Promise<T>;
}

export async function putJson<T>(path: string, body: unknown = {}): Promise<T> {
  const response = await fetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${text.slice(0, 200)}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const text = await response.text();
    throw new Error(`接口没有返回 JSON：${text.slice(0, 80)}`);
  }
  return response.json() as Promise<T>;
}
