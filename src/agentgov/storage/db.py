from __future__ import annotations

import sqlite3
from pathlib import Path


def normalize_sqlite_url(database: str) -> Path:
    if database.startswith("sqlite+aiosqlite:///"):
        raw = database.removeprefix("sqlite+aiosqlite:///")
    elif database.startswith("sqlite:///"):
        raw = database.removeprefix("sqlite:///")
    else:
        raise ValueError(f"only sqlite URLs are supported in MVP: {database}")
    return Path(raw)


def connect(database: str) -> sqlite3.Connection:
    path = normalize_sqlite_url(database)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_versions (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  spec_snapshot TEXT NOT NULL,
  memory_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  reason TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  root_agent_id TEXT,
  team_id TEXT,
  status TEXT NOT NULL,
  context_summary TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  parent_run_id TEXT,
  agent_id TEXT NOT NULL,
  agent_version_id TEXT,
  run_type TEXT NOT NULL,
  status TEXT NOT NULL,
  input_summary TEXT NOT NULL,
  output_summary TEXT,
  error TEXT,
  estimated_cost_usd REAL NOT NULL DEFAULT 0,
  actual_cost_usd REAL NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  started_at TEXT,
  completed_at TEXT,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_knowledge_sources (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  name TEXT NOT NULL,
  locator TEXT,
  content TEXT NOT NULL DEFAULT '',
  trust_level TEXT NOT NULL DEFAULT 'session_input',
  required_citation INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS knowledge_access_grants (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  plan_id TEXT,
  task_node_id TEXT,
  run_id TEXT,
  agent_id TEXT NOT NULL,
  source_ids TEXT NOT NULL DEFAULT '[]',
  access_mode TEXT NOT NULL DEFAULT 'read',
  granted_by TEXT NOT NULL,
  rationale TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'planned',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS knowledge_access_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT,
  agent_id TEXT NOT NULL,
  source_id TEXT,
  action TEXT NOT NULL,
  query TEXT,
  result_refs TEXT NOT NULL DEFAULT '[]',
  decision TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS run_steps (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  parent_step_id TEXT,
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  actor_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  input_tokens INTEGER,
  output_tokens INTEGER,
  cost_usd REAL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, seq),
  FOREIGN KEY(run_id) REFERENCES runs(id),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS model_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  request_summary TEXT NOT NULL,
  response_summary TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  estimated_cost_usd REAL NOT NULL DEFAULT 0,
  actual_cost_usd REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  caller_agent_id TEXT NOT NULL,
  args_summary TEXT NOT NULL DEFAULT '{}',
  result_summary TEXT,
  status TEXT NOT NULL,
  approval_id TEXT,
  duration_ms INTEGER,
  error TEXT
);

CREATE TABLE IF NOT EXISTS action_intents (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  tool_name TEXT,
  arguments TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  policy_decision_id TEXT,
  observation_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  action_intent_id TEXT,
  agent_id TEXT NOT NULL,
  content TEXT NOT NULL,
  data TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sandbox_actions (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT NOT NULL,
  sandbox_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  command_summary TEXT,
  filesystem_policy TEXT NOT NULL,
  network_policy TEXT NOT NULL,
  status TEXT NOT NULL,
  output_summary TEXT,
  error TEXT,
  duration_ms INTEGER
);

CREATE TABLE IF NOT EXISTS policy_decisions (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT,
  policy_id TEXT NOT NULL,
  policy_type TEXT NOT NULL,
  subject TEXT NOT NULL,
  action TEXT NOT NULL,
  resource TEXT NOT NULL,
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delegation_grants (
  id TEXT PRIMARY KEY,
  parent_run_id TEXT NOT NULL,
  grantee_agent_id TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  allowed_actions TEXT NOT NULL DEFAULT '[]',
  allowed_resources TEXT NOT NULL DEFAULT '[]',
  expires_at TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT,
  requested_by TEXT NOT NULL,
  approver_id TEXT,
  status TEXT NOT NULL,
  action_summary TEXT NOT NULL DEFAULT '{}',
  reason TEXT,
  decided_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_ledger (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  amount_usd REAL NOT NULL,
  estimated_input_tokens INTEGER,
  estimated_output_tokens INTEGER,
  actual_input_tokens INTEGER,
  actual_output_tokens INTEGER,
  provider TEXT,
  model TEXT,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS budget_snapshots (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  scope TEXT NOT NULL,
  max_budget_usd REAL,
  current_spend_usd REAL NOT NULL DEFAULT 0,
  reserved_spend_usd REAL NOT NULL DEFAULT 0,
  data TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS span_records (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  parent_span_id TEXT,
  span_type TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  attributes TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS evidence_refs (
  id TEXT PRIMARY KEY,
  ref_type TEXT NOT NULL,
  ref_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  step_id TEXT,
  path TEXT,
  line_start INTEGER,
  line_end INTEGER,
  summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reasoning_traces (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  step_id TEXT,
  agent_id TEXT NOT NULL,
  decision_summary TEXT NOT NULL,
  evidence_refs TEXT NOT NULL DEFAULT '[]',
  alternatives_considered TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0,
  risk_flags TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_messages (
  id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  parent_run_id TEXT,
  source_agent_id TEXT NOT NULL,
  target_agent_id TEXT NOT NULL,
  message_type TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collaboration_tasks (
  id TEXT PRIMARY KEY,
  parent_run_id TEXT NOT NULL,
  assigned_agent_id TEXT NOT NULL,
  task_type TEXT NOT NULL,
  instruction TEXT NOT NULL,
  status TEXT NOT NULL,
  result_summary TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS session_plans (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  requirement_id TEXT,
  parent_plan_id TEXT,
  change_reason TEXT NOT NULL DEFAULT '',
  approval_status TEXT NOT NULL DEFAULT 'pending',
  objective TEXT NOT NULL,
  strategy TEXT NOT NULL,
  planner_agent_id TEXT NOT NULL,
  status TEXT NOT NULL,
  raw_plan TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_requirements (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  objective TEXT NOT NULL,
  contract TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT 'user',
  parent_id TEXT,
  change_reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  created_by TEXT NOT NULL DEFAULT 'operator',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_feedback (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  message TEXT NOT NULL,
  requested_action TEXT NOT NULL DEFAULT 'replan',
  impact TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'submitted',
  requirement_id TEXT,
  plan_id TEXT,
  created_by TEXT NOT NULL DEFAULT 'operator',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS task_nodes (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  node_key TEXT NOT NULL,
  assigned_agent_id TEXT NOT NULL,
  run_id TEXT,
  node_type TEXT NOT NULL,
  title TEXT NOT NULL,
  instruction TEXT NOT NULL,
  required_capabilities TEXT NOT NULL DEFAULT '[]',
  required_tools TEXT NOT NULL DEFAULT '[]',
  input_refs TEXT NOT NULL DEFAULT '[]',
  output_contract TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS task_edges (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL,
  source_node_id TEXT NOT NULL,
  target_node_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  payload_key TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_queue (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_id TEXT,
  status TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 100,
  lease_owner TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  available_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_leases (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  worker_id TEXT NOT NULL,
  lease_until TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_items (
  id TEXT PRIMARY KEY,
  agent_id TEXT,
  content TEXT NOT NULL,
  source_run_id TEXT,
  source_evidence_refs TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experience_candidates (
  id TEXT PRIMARY KEY,
  source_run_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  evidence_refs TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_cases (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  owner_id TEXT NOT NULL,
  snapshot_key TEXT NOT NULL,
  outcome TEXT NOT NULL,
  reviewer_id TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT '',
  satisfaction INTEGER,
  reusable_guidance TEXT NOT NULL DEFAULT '',
  share_scope TEXT NOT NULL DEFAULT 'private',
  tags TEXT NOT NULL DEFAULT '[]',
  case_data TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  UNIQUE(session_id, snapshot_key),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_session_cases_owner ON session_cases(owner_id, share_scope, created_at);

CREATE TABLE IF NOT EXISTS agent_health_snapshots (
  agent_id TEXT PRIMARY KEY,
  version TEXT NOT NULL,
  status TEXT NOT NULL,
  health_score INTEGER NOT NULL DEFAULT 100,
  active_runs INTEGER NOT NULL DEFAULT 0,
  queued_runs INTEGER NOT NULL DEFAULT 0,
  success_rate REAL NOT NULL DEFAULT 0,
  avg_latency_ms INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  budget_used_usd REAL NOT NULL DEFAULT 0,
  budget_limit_usd REAL,
  last_event_type TEXT,
  last_event_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_dependency_edges (
  id TEXT PRIMARY KEY,
  source_agent_id TEXT NOT NULL,
  target_agent_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  call_count INTEGER NOT NULL DEFAULT 0,
  avg_latency_ms INTEGER NOT NULL DEFAULT 0,
  failure_rate REAL NOT NULL DEFAULT 0,
  last_call_at TEXT
);

CREATE TABLE IF NOT EXISTS team_matching_reports (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  team_id TEXT,
  score REAL NOT NULL,
  decision TEXT NOT NULL,
  covered_capabilities TEXT NOT NULL DEFAULT '[]',
  missing_capabilities TEXT NOT NULL DEFAULT '[]',
  redundant_agents TEXT NOT NULL DEFAULT '[]',
  suggested_agents TEXT NOT NULL DEFAULT '[]',
  risk_items TEXT NOT NULL DEFAULT '[]',
  token_waste_warnings TEXT NOT NULL DEFAULT '[]',
  checker TEXT NOT NULL,
  explanation TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  leader_agent_id TEXT NOT NULL,
  member_agent_ids TEXT NOT NULL DEFAULT '[]',
  collaboration_strategy TEXT NOT NULL,
  capability_ids TEXT NOT NULL DEFAULT '[]',
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_team_snapshots (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  source_team_template_id TEXT,
  leader_agent_id TEXT NOT NULL,
  member_agent_ids TEXT NOT NULL DEFAULT '[]',
  agent_capabilities TEXT NOT NULL DEFAULT '{}',
  collaboration_strategy TEXT NOT NULL,
  matching_report_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  created_by_agent_id TEXT NOT NULL,
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  summary TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_versions (
  id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(artifact_id) REFERENCES artifacts(id),
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_agents (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  parent_agent_id TEXT,
  role TEXT NOT NULL,
  origin TEXT NOT NULL,
  depth INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  spec_snapshot TEXT NOT NULL DEFAULT '{}',
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  retired_at TEXT,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS delegation_requests (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT,
  requester_agent_id TEXT NOT NULL,
  parent_agent_id TEXT NOT NULL,
  requested_agent_id TEXT,
  requested_role TEXT NOT NULL,
  objective TEXT NOT NULL,
  requested_skills TEXT NOT NULL DEFAULT '[]',
  requested_tools TEXT NOT NULL DEFAULT '[]',
  budget_usd REAL NOT NULL DEFAULT 0,
  risk_level TEXT NOT NULL DEFAULT 'low',
  status TEXT NOT NULL DEFAULT 'pending',
  approval_id TEXT,
  reason TEXT,
  created_at TEXT NOT NULL,
  decided_at TEXT,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_skill_grants (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  source TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_tool_grants (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  tool_id TEXT NOT NULL,
  granted_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS agent_lifecycle_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS session_checkpoints (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  run_id TEXT,
  label TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  snapshot TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS rollback_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  checkpoint_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(session_id) REFERENCES sessions(id),
  FOREIGN KEY(checkpoint_id) REFERENCES session_checkpoints(id)
);

CREATE INDEX IF NOT EXISTS idx_runs_session_created ON runs(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_session ON session_knowledge_sources(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_grants_session ON knowledge_access_grants(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_grants_run ON knowledge_access_grants(run_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_events_session ON knowledge_access_events(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_parent ON runs(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_run_steps_run_seq ON run_steps(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_run_steps_session_created ON run_steps(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_policy_run_policy ON policy_decisions(run_id, policy_id);
CREATE INDEX IF NOT EXISTS idx_action_intents_run_created ON action_intents(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_observations_run_created ON observations(run_id, created_at);
CREATE INDEX IF NOT EXISTS idx_approvals_run_status ON approvals(run_id, status);
CREATE INDEX IF NOT EXISTS idx_span_trace_run ON span_records(trace_id, run_id);
CREATE INDEX IF NOT EXISTS idx_messages_trace_created ON agent_messages(trace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_plans_session ON session_plans(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_session_requirements_session ON session_requirements(session_id, version);
CREATE INDEX IF NOT EXISTS idx_session_feedback_session ON session_feedback(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_nodes_plan_status ON task_nodes(plan_id, status);
CREATE INDEX IF NOT EXISTS idx_task_nodes_run ON task_nodes(run_id);
CREATE INDEX IF NOT EXISTS idx_task_edges_target ON task_edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_queue_status_priority ON run_queue(status, priority, available_at);
CREATE INDEX IF NOT EXISTS idx_leases_run_until ON run_leases(run_id, lease_until);
CREATE INDEX IF NOT EXISTS idx_matching_session ON team_matching_reports(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_team_templates_status ON team_templates(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_team_snapshots_session ON session_team_snapshots(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_artifact_versions_path ON artifact_versions(session_id, path, version);
CREATE INDEX IF NOT EXISTS idx_session_agents_session ON session_agents(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_delegation_requests_session ON delegation_requests(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_delegation_requests_status ON delegation_requests(status, created_at);
CREATE INDEX IF NOT EXISTS idx_skill_grants_session ON session_skill_grants(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tool_grants_session ON session_tool_grants(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_session ON agent_lifecycle_events(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON session_checkpoints(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_rollbacks_session ON rollback_events(session_id, created_at);
"""


MIGRATIONS_SQL = [
    "ALTER TABLE session_feedback ADD COLUMN reason_type TEXT NOT NULL DEFAULT 'unspecified'",
    "ALTER TABLE experience_candidates ADD COLUMN source_case_id TEXT",
    "ALTER TABLE experience_candidates ADD COLUMN target_type TEXT NOT NULL DEFAULT 'unspecified'",
    "ALTER TABLE experience_candidates ADD COLUMN operation TEXT NOT NULL DEFAULT 'add'",
    "ALTER TABLE run_queue ADD COLUMN session_id TEXT",
    "ALTER TABLE run_queue ADD COLUMN lease_owner TEXT",
    "ALTER TABLE run_queue ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE run_queue ADD COLUMN last_error TEXT",
    "ALTER TABLE session_plans ADD COLUMN version INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE session_plans ADD COLUMN requirement_id TEXT",
    "ALTER TABLE session_plans ADD COLUMN parent_plan_id TEXT",
    "ALTER TABLE session_plans ADD COLUMN change_reason TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE session_plans ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'pending'",
]


def init_db(database: str) -> None:
    with connect(database) as conn:
        conn.executescript(SCHEMA_SQL)
        for statement in MIGRATIONS_SQL:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        conn.commit()
