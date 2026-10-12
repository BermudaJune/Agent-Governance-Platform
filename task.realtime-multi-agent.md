# Realtime Multi-Agent Governance Tasks

## File List

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/agentgov/capabilities/__init__.py` | Capability package exports |
| Create | `src/agentgov/capabilities/models.py` | Capability, Skill, Tool, TaskRequirement models |
| Create | `src/agentgov/capabilities/registry.py` | Load/query capability, skill and tool metadata |
| Create | `src/agentgov/capabilities/requirements.py` | Rule-first task requirement analysis |
| Create | `src/agentgov/teams/__init__.py` | Team package exports |
| Create | `src/agentgov/teams/models.py` | Team matching/template/snapshot models |
| Create | `src/agentgov/teams/matching.py` | Team-task capability matching |
| Create | `src/agentgov/teams/snapshots.py` | Team template and session snapshot service |
| Create | `src/agentgov/event_stream/sse.py` | Session SSE stream helper |
| Create | `src/agentgov/gateway/skill.py` | Skill governance gateway |
| Create | `src/agentgov/runtime/collaboration.py` | Task/message/result collaboration protocol |
| Create | `src/agentgov/api/routes_events.py` | SSE API route |
| Create | `src/agentgov/api/routes_teams.py` | Team matching/template/history API |
| Modify | `src/agentgov/config/schema.py` | Add capability/skill/team metadata fields |
| Modify | `src/agentgov/storage/db.py` | Add queue, capability, matching, team snapshot, artifact tables |
| Modify | `src/agentgov/storage/repositories.py` | Add repository helpers for new tables |
| Modify | `src/agentgov/scheduler/queue.py` | Implement DB-backed run queue |
| Modify | `src/agentgov/scheduler/worker.py` | Implement background worker tick loop |
| Modify | `src/agentgov/event_stream/events.py` | Add realtime and collaboration event constants |
| Modify | `src/agentgov/event_stream/stream.py` | Query session events for SSE |
| Modify | `src/agentgov/gateway/tool.py` | Route calls through capability metadata and artifact registration |
| Modify | `src/agentgov/runtime/agent_loop.py` | Emit model/tool lifecycle events |
| Modify | `src/agentgov/runtime/run_service.py` | Add manual/enqueue/sync execution modes and retry |
| Modify | `src/agentgov/api/routes_tasks.py` | Add matching/snapshot/enqueue dispatch flow |
| Modify | `src/agentgov/api/routes_runs.py` | Add retry and queue-aware controls |
| Modify | `src/agentgov/api/routes_dashboard.py` | Surface matching reports, artifacts, team snapshots |
| Modify | `src/agentgov/app.py` | Wire registries, matcher, queue, worker, SSE/team routes |
| Modify | `config/examples/local.openai.yaml` | Add sample capabilities, skills and reusable team metadata |
| Modify | `config/examples/local.scripted.yaml` | Add deterministic test capabilities and skills |
| Modify | `web/src/api.ts` | Add SSE, team matching and template API helpers |
| Modify | `web/src/App.tsx` | Add Session Cockpit, Team Matching Report and save-template UI |
| Modify | `web/src/styles.css` | Style cockpit, event stream, matching report and artifacts |
| Create | `tests/unit/test_capability_matching.py` | Unit tests for requirement analysis and matching |
| Create | `tests/unit/test_team_snapshots.py` | Unit tests for template/snapshot/history behavior |
| Create | `tests/unit/test_run_queue.py` | Unit tests for queue lease/cancel/retry |
| Create | `tests/integration/test_worker_sse_flow.py` | Worker + persisted events integration test |
| Create | `tests/integration/test_skill_tool_governance.py` | Skill/tool permission and artifact integration test |
| Create | `tests/e2e/test_custom_team_task.py` | End-to-end scripted custom multi-agent task |

## T1: Define Capability Models

**Files:** `src/agentgov/capabilities/__init__.py`, `src/agentgov/capabilities/models.py`, `src/agentgov/teams/models.py`

**Dependencies:** None

**Steps:**
1. Add Pydantic/dataclass models for `CapabilityDefinition`, `SkillDefinition`, `ToolDefinition`, `TaskRequirement`.
2. Add models for `TeamMatchingReport`, `TeamTemplate`, `SessionTeamSnapshot`.
3. Include JSON serialization helpers where needed.

**Validation:** Run `python -m compileall src`; expect no compile errors.

## T2: Extend Config Schema

**Files:** `src/agentgov/config/schema.py`, `config/examples/local.openai.yaml`, `config/examples/local.scripted.yaml`

**Dependencies:** T1

**Steps:**
1. Add optional `capabilities`, `skills`, and richer `teams` metadata to config schema.
2. Keep existing config files backward compatible.
3. Add sample capability/skill definitions for repository tools, file tools, coordination tools and scripted test abilities.

**Validation:** Run `pytest tests/unit/test_config.py`; expect config tests pass.

## T3: Add Storage Schema

**Files:** `src/agentgov/storage/db.py`

**Dependencies:** T1

**Steps:**
1. Add tables for `run_queue`, `team_matching_reports`, `team_templates`, `session_team_snapshots`, `artifacts`.
2. Ensure `init_db` remains idempotent.
3. Store structured payload fields as JSON text.

**Validation:** Run `python -m compileall src`; initialize a test DB through existing tests; expect no schema errors.

## T4: Add Repository Helpers

**Files:** `src/agentgov/storage/repositories.py`

**Dependencies:** T3

**Steps:**
1. Add insert/list/get helpers for queue items.
2. Add helpers for matching reports, team templates, snapshots and artifacts.
3. Keep existing generic query helpers intact.

**Validation:** Run `pytest tests/unit/test_storage_event_budget.py`; expect existing storage tests pass.

## T5: Implement Capability Registry

**Files:** `src/agentgov/capabilities/registry.py`

**Dependencies:** T1, T2

**Steps:**
1. Load capability and skill definitions from config.
2. Infer capabilities for existing tools where explicit definitions are missing.
3. Provide `list_agent_capabilities(agent_id)` using agent tools, skills and policies.

**Validation:** Add and run `pytest tests/unit/test_capability_matching.py`; expect registry can load scripted config.

## T6: Implement Requirement Analyzer

**Files:** `src/agentgov/capabilities/requirements.py`

**Dependencies:** T5

**Steps:**
1. Implement deterministic keyword/rule analyzer for task text.
2. Detect common requirements such as file read, file write, external network, command execution, review, artifact output.
3. Return `TaskRequirement` without calling LLM by default.
4. Add placeholder interface for optional LLM analyzer.

**Validation:** Run `pytest tests/unit/test_capability_matching.py`; expect custom tasks map to required capabilities.

## T7: Implement Team Matcher

**Files:** `src/agentgov/teams/matching.py`

**Dependencies:** T5, T6

**Steps:**
1. Compare `TaskRequirement` against selected Agent capabilities.
2. Produce score, decision, covered/missing capabilities, redundant agents and risk items.
3. Detect likely token waste when agents have no relevant capabilities or duplicate the same role.
4. Keep optional LLM matching as an interface, not required for tests.

**Validation:** Run `pytest tests/unit/test_capability_matching.py`; expect high score for matching teams and low score for missing capability teams.

## T8: Implement Team Snapshot Service

**Files:** `src/agentgov/teams/snapshots.py`

**Dependencies:** T4, T7

**Steps:**
1. Create `SessionTeamSnapshot` from ad-hoc team or Team Template.
2. Save template from a Session snapshot.
3. Query template history and agent participation history.

**Validation:** Run `pytest tests/unit/test_team_snapshots.py`; expect snapshots remain unchanged after template edits.

## T9: Implement DB Run Queue

**Files:** `src/agentgov/scheduler/queue.py`

**Dependencies:** T4

**Steps:**
1. Implement enqueue, lease, complete, fail, retry and cancel operations.
2. Use DB status fields for local deterministic behavior.
3. Preserve extension boundary for Redis replacement.

**Validation:** Run `pytest tests/unit/test_run_queue.py`; expect lease/cancel/retry behavior works.

## T10: Implement Worker Tick Loop

**Files:** `src/agentgov/scheduler/worker.py`, `src/agentgov/runtime/run_service.py`

**Dependencies:** T9

**Steps:**
1. Add `RunWorker.tick()` to lease one item and execute its Run.
2. Mark queue item completed/failed based on RunService result.
3. Respect paused/cancelled runs before and after execution.
4. Add `enqueue` execution mode to RunService.

**Validation:** Run `pytest tests/integration/test_worker_sse_flow.py`; expect a queued scripted Run completes through worker tick.

## T11: Add Realtime Event Query And SSE

**Files:** `src/agentgov/event_stream/events.py`, `src/agentgov/event_stream/stream.py`, `src/agentgov/event_stream/sse.py`, `src/agentgov/api/routes_events.py`

**Dependencies:** T4

**Steps:**
1. Add event type constants for queue, matching, team snapshot, agent message, artifact and worker events.
2. Add session event query with optional `after_id`.
3. Implement SSE formatter for persisted events.
4. Add `GET /events/sessions/{session_id}`.

**Validation:** Run `pytest tests/integration/test_worker_sse_flow.py`; expect emitted events can be read in SSE format.

## T12: Add Skill Gateway

**Files:** `src/agentgov/gateway/skill.py`

**Dependencies:** T5

**Steps:**
1. Implement `load_skill` that checks agent authorization.
2. Emit skill loaded/denied events.
3. Return prompt body and recommended tools without executing tools directly.

**Validation:** Run `pytest tests/integration/test_skill_tool_governance.py`; expect unauthorized skill is denied and logged.

## T13: Extend Tool Gateway

**Files:** `src/agentgov/gateway/tool.py`

**Dependencies:** T5, T12

**Steps:**
1. Attach capability metadata to tool calls.
2. Check agent allowlist and risk policy before execution.
3. Register artifact records for file-producing tools.
4. Preserve current `repo_*`, `file_*`, `local_command` behavior.

**Validation:** Run `pytest tests/integration/test_skill_tool_governance.py`; expect allowed tools execute and denied tools create policy decisions.

## T14: Implement Collaboration Runtime

**Files:** `src/agentgov/runtime/collaboration.py`, `src/agentgov/runtime/run_service.py`

**Dependencies:** T9, T11

**Steps:**
1. Add helpers for task assignment, agent message and result submission.
2. Ensure each message is persisted and emitted as event.
3. Enqueue child runs when assigned.
4. Keep current parent/child Run model compatible.

**Validation:** Run `pytest tests/e2e/test_custom_team_task.py`; expect a scripted leader assigns work and receives results.

## T15: Update Task Dispatch Flow

**Files:** `src/agentgov/api/routes_tasks.py`

**Dependencies:** T7, T8, T10, T14

**Steps:**
1. Add request fields `execute_mode`, `use_llm_matching`, `force`.
2. Analyze task requirements before creating or executing team runs.
3. Generate Team Matching Report.
4. If report blocks and `force` is false, return report without enqueue.
5. Create Session Team Snapshot for accepted teams.
6. Enqueue runs when `execute_mode` is `enqueue`; preserve `manual` and `sync`.

**Validation:** Run `pytest tests/e2e/test_custom_team_task.py`; expect dispatch returns matching report and session when accepted.

## T16: Add Team API

**Files:** `src/agentgov/api/routes_teams.py`, `src/agentgov/app.py`

**Dependencies:** T8, T15

**Steps:**
1. Add endpoints for team matching, listing templates, creating templates and saving template from session.
2. Add team history endpoint.
3. Wire route in app.

**Validation:** Run `pytest tests/unit/test_team_snapshots.py`; call API through integration test if available.

## T17: Update Run Controls

**Files:** `src/agentgov/api/routes_runs.py`, `src/agentgov/runtime/run_service.py`

**Dependencies:** T9, T10

**Steps:**
1. Add retry endpoint for failed/cancelled runs when retry is allowed.
2. Ensure pause/cancel also updates queue items.
3. Emit queue/control events.

**Validation:** Run `pytest tests/unit/test_run_queue.py`; expect cancelled session queue items do not execute.

## T18: Update Dashboard Data

**Files:** `src/agentgov/api/routes_dashboard.py`, `src/agentgov/dashboard/service.py`, `src/agentgov/dashboard/topology.py`

**Dependencies:** T4, T8, T11, T13

**Steps:**
1. Include matching reports, artifacts and team snapshot in session details.
2. Include artifact and capability events in run details.
3. Enhance topology nodes/edges to show capabilities, team snapshots and agent messages.

**Validation:** Run existing API tests plus `pytest tests/e2e/test_custom_team_task.py`; expect dashboard payload includes new fields.

## T19: Add Frontend API Helpers

**Files:** `web/src/api.ts`

**Dependencies:** T11, T16

**Steps:**
1. Add helpers for team matching/templates/history.
2. Add SSE subscription helper with reconnect support.
3. Add TypeScript types for matching report, team template, artifact and event.

**Validation:** Run `npm run build`; expect TypeScript passes.

## T20: Add Session Cockpit UI

**Files:** `web/src/App.tsx`, `web/src/styles.css`

**Dependencies:** T18, T19

**Steps:**
1. Add Session Cockpit page or enhance Session page with live event stream.
2. Show matching report, team snapshot, topology, current runs, messages, artifacts and controls.
3. Subscribe to SSE when a Session is selected.
4. Keep manual refresh available.

**Validation:** Run `npm run build`; manually open console and confirm page renders.

## T21: Add Team Matching UI

**Files:** `web/src/App.tsx`, `web/src/styles.css`

**Dependencies:** T16, T19

**Steps:**
1. Show pre-execution matching report in task dispatch.
2. Allow cancel, adjust, force continue.
3. Add save-as-template action from Session snapshot.
4. Add Team Template list with history summary.

**Validation:** Run `npm run build`; use browser to create an ad-hoc team and observe matching report.

## T22: Update Config Examples

**Files:** `config/examples/local.openai.yaml`, `config/examples/local.scripted.yaml`

**Dependencies:** T2, T5

**Steps:**
1. Add capabilities for file read/write, repo search, local command, coordination, artifact writing and review.
2. Add skills for simple writing, review, repository analysis and scripted custom task.
3. Ensure examples do not include secrets.

**Validation:** Run `pytest tests/unit/test_config.py`; expect both configs validate.

## T23: Add Unit Tests

**Files:** `tests/unit/test_capability_matching.py`, `tests/unit/test_team_snapshots.py`, `tests/unit/test_run_queue.py`

**Dependencies:** T5, T7, T8, T9

**Steps:**
1. Test requirement analysis for non-programming and programming task classes.
2. Test team matching score and missing/redundant capability detection.
3. Test template/snapshot/history behavior.
4. Test queue lease/cancel/retry.

**Validation:** Run `pytest tests/unit`; expect all unit tests pass.

## T24: Add Integration Tests

**Files:** `tests/integration/test_worker_sse_flow.py`, `tests/integration/test_skill_tool_governance.py`

**Dependencies:** T10, T11, T12, T13

**Steps:**
1. Test queued scripted Run executes through worker.
2. Test SSE event stream includes queued/running/completed events.
3. Test skill authorization and denied tool events.
4. Test artifact registration from file tool.

**Validation:** Run `pytest tests/integration`; expect all integration tests pass without real LLM.

## T25: Add End-To-End Custom Team Test

**Files:** `tests/e2e/test_custom_team_task.py`

**Dependencies:** T14, T15, T18

**Steps:**
1. Use scripted model/tools to create a custom multi-agent task.
2. Verify matching report is created.
3. Verify worker executes queued runs.
4. Verify agent messages, tool calls, artifacts and final status are visible in dashboard payload.

**Validation:** Run `pytest tests/e2e/test_custom_team_task.py`; expect pass without real LLM.

## T26: Full Verification

**Files:** all modified files

**Dependencies:** T1-T25

**Steps:**
1. Run Python compilation.
2. Run all pytest tests.
3. Run frontend build.
4. Restart local backend and verify `/health`.
5. Open frontend and verify task dispatch, matching report and Session Cockpit.

**Validation:**
1. `python -m compileall src` exits 0.
2. `pytest` exits 0.
3. `npm run build` exits 0.
4. `Invoke-WebRequest http://127.0.0.1:8000/health` returns `{"status":"ok"}`.

## Execution Order

```text
T1 -> T2 -> T3 -> T4
T2 -> T5 -> T6 -> T7 -> T8
T4 -> T9 -> T10
T4 -> T11
T5 -> T12 -> T13
T9 + T11 -> T14
T7 + T8 + T10 + T14 -> T15
T8 + T15 -> T16
T9 + T10 -> T17
T4 + T8 + T11 + T13 -> T18
T11 + T16 -> T19
T18 + T19 -> T20
T16 + T19 -> T21
T2 + T5 -> T22
T5 + T7 + T8 + T9 -> T23
T10 + T11 + T12 + T13 -> T24
T14 + T15 + T18 -> T25
T1..T25 -> T26
```

