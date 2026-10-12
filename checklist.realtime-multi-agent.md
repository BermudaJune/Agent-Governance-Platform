# Realtime Multi-Agent Governance Checklist

> Each item must be verified by running code or observing behavior.

## Implementation Completeness

- [ ] Capability, Skill and Tool definitions are loadable from config.
  Verification: run `pytest tests/unit/test_capability_matching.py`; expect registry tests pass.

- [ ] Task requirements can be analyzed without calling a real LLM.
  Verification: run `pytest tests/unit/test_capability_matching.py`; expect non-programming and programming task examples map to required capabilities.

- [ ] Team Matching Report is generated before multi-agent execution.
  Verification: call `POST /tasks/dispatch-ad-hoc-team` with `execute_mode=manual`; expect response includes matching report or a block/adjust decision.

- [ ] Matching report includes score, decision, covered capabilities, missing capabilities, redundant agents, risk items and token waste warnings.
  Verification: inspect API response from `POST /teams/match`; expect all fields present.

- [ ] Low-score team can be blocked before enqueue unless `force=true`.
  Verification: use a team missing required file/write capability; expect no queued runs unless forced.

- [ ] Ad-hoc team can be saved as reusable Team Template.
  Verification: call `POST /teams/templates/from-session/{session_id}`; expect new template appears in `GET /teams/templates`.

- [ ] Session Team Snapshot is saved for each accepted team session.
  Verification: open `/dashboard/sessions/{session_id}`; expect snapshot data remains stable after editing template.

- [ ] Team Run History records actual team use.
  Verification: call `GET /teams/history`; expect entry with session id, team/template id, cost and status.

- [ ] DB-backed Run Queue supports enqueue, lease, complete, fail, retry and cancel.
  Verification: run `pytest tests/unit/test_run_queue.py`; expect all queue tests pass.

- [ ] Worker can execute queued scripted runs.
  Verification: run `pytest tests/integration/test_worker_sse_flow.py`; expect queued run reaches completed.

- [ ] SSE session stream emits persisted events.
  Verification: subscribe to `GET /events/sessions/{session_id}` during scripted run; expect queued/running/model/tool/completed events.

- [ ] Skill Gateway denies unauthorized skill loads.
  Verification: run `pytest tests/integration/test_skill_tool_governance.py`; expect denied skill creates policy/event record.

- [ ] Tool Gateway records capability metadata and artifacts.
  Verification: run file-producing scripted tool; expect artifact appears in `/dashboard/sessions/{session_id}`.

- [ ] Collaboration Runtime records assignments, messages and results.
  Verification: run `pytest tests/e2e/test_custom_team_task.py`; expect agent_messages include assignment and result events.

- [ ] Session Cockpit shows matching report, team snapshot, event stream, runs, messages, artifacts and controls.
  Verification: open frontend, create custom ad-hoc team session, observe cockpit sections.

## Integration

- [ ] Dispatch flow supports `manual`, `enqueue` and `sync` execution modes.
  Verification: call task dispatch endpoint with each mode; expect manual creates pending runs, enqueue creates queued items, sync preserves existing behavior.

- [ ] Existing single-agent dispatch still works.
  Verification: call `POST /tasks/dispatch`; expect session/run created and existing run detail pages still load.

- [ ] Existing story demo still works.
  Verification: run story demo from frontend or API; expect `story.md` and `review.md` artifacts still appear.

- [ ] Team matching integrates with ad-hoc team dispatch.
  Verification: create ad-hoc team from UI; expect matching report appears before execution.

- [ ] Team matching integrates with predefined Team Template dispatch.
  Verification: dispatch using saved template; expect template id and snapshot id appear in session details.

- [ ] Pause/cancel controls update queued work.
  Verification: create enqueued multi-agent session, pause/cancel before worker tick; expect queue items no longer execute.

- [ ] Retry control re-enqueues eligible failed runs.
  Verification: force a scripted failure, click retry or call retry endpoint; expect new queue item and retry event.

- [ ] SSE and persisted timeline agree.
  Verification: compare live SSE events with `/dashboard/sessions/{session_id}` timeline after refresh; expect same event facts.

- [ ] Artifact references can be traced to run, agent and tool call.
  Verification: inspect session artifact payload; expect run id, agent id and tool call metadata.

- [ ] Agent view includes participation history.
  Verification: open Agent view after custom team task; expect related team/session participation shown or available in dashboard payload.

## Build And Test

- [ ] Python source compiles.
  Verification: run `python -m compileall src`; expect exit code 0.

- [ ] Unit tests pass.
  Verification: run `pytest tests/unit`; expect all unit tests pass.

- [ ] Integration tests pass.
  Verification: run `pytest tests/integration`; expect all integration tests pass.

- [ ] End-to-end scripted custom team task passes without real LLM.
  Verification: run `pytest tests/e2e/test_custom_team_task.py`; expect pass.

- [ ] Full test suite passes.
  Verification: run `pytest`; expect all tests pass.

- [ ] Frontend builds.
  Verification: run `npm run build` in `web`; expect TypeScript and Vite build pass.

- [ ] Backend starts with scripted config.
  Verification: start API with `config/examples/local.scripted.yaml`; call `/health`; expect `{"status":"ok"}`.

- [ ] Backend starts with OpenAI-compatible config when API key env is present.
  Verification: set `XINGWAN_API_KEY`, start API with `config/examples/local.openai.yaml`, call `/health`; expect `{"status":"ok"}`.

## End-To-End Scenarios

- [ ] Scenario 1: Custom non-programming capability task can be matched.
  Verification: register or use scripted capabilities for external info, writing and review; submit a task like “查询天气、写一首诗到文件、让另一个 Agent 鉴赏”; expect matching report covers network/write/review/artifact capabilities.

- [ ] Scenario 2: Matching prevents wasteful team execution.
  Verification: submit the same task to a team without network/weather capability; expect matching report flags missing capability and recommends adjust/block before enqueue.

- [ ] Scenario 3: Forced execution records mismatch.
  Verification: force continue despite low score; expect Session stores matching report and events show forced execution decision.

- [ ] Scenario 4: Ad-hoc team runs through worker and SSE.
  Verification: create valid ad-hoc team with `execute_mode=enqueue`; observe Session Cockpit events until completion.

- [ ] Scenario 5: Agent communication is visible.
  Verification: during custom team task, observe TaskAssignment, AgentMessage, result submission and final result in event stream and after refresh.

- [ ] Scenario 6: Artifact output is traceable.
  Verification: run a file-producing task; open Session artifact list; verify artifact links back to Agent, Run and tool call.

- [ ] Scenario 7: Pause and resume session.
  Verification: enqueue a multi-agent task, click pause, verify queue stops; click resume/execute pending, verify queued work continues.

- [ ] Scenario 8: Cancel session.
  Verification: enqueue a multi-agent task, click cancel before completion; expect remaining queue items cancelled and event timeline records cancellation.

- [ ] Scenario 9: Save successful ad-hoc team as template.
  Verification: complete a custom team session, save as template, dispatch a new task using that template; expect new session references template and has its own snapshot.

- [ ] Scenario 10: Frontend refresh recovery.
  Verification: refresh browser during or after task; expect Session Cockpit restores historical events, topology, matching report, snapshot, runs and artifacts.

## Regression Checks

- [ ] Existing dashboard overview loads.
  Verification: open frontend total overview; expect metrics render without API errors.

- [ ] Existing configuration center loads and saves valid config.
  Verification: open config page, validate/save unchanged config; expect success notice.

- [ ] Existing Agent Builder still shows provider, model, tools, sandbox and policies.
  Verification: open config page builder; expect existing agents render.

- [ ] Existing Run Audit page still shows model calls, tool calls, sandbox actions, policies and budget ledger.
  Verification: select a historical run; expect sections render.

- [ ] Existing Session Review page still shows session runs, messages, artifacts and timeline.
  Verification: select a historical session; expect sections render.

- [ ] Existing approvals page still handles pending approvals.
  Verification: create demo approval and approve/reject; expect status updates.

## Acceptance Mapping

- AC1: Covered by Implementation Completeness queue/worker items and E2E Scenario 4.
- AC2: Covered by SSE items and E2E Scenarios 4, 5 and 10.
- AC3: Covered by Collaboration Runtime and E2E Scenario 5.
- AC4: Covered by pause/resume/cancel integration and E2E Scenarios 7, 8.
- AC5: Covered by run retry/control integration checks.
- AC6: Covered by Skill Gateway and Tool Gateway governance tests.
- AC7: Covered by Team Matching Report items.
- AC8: Covered by low-score, cancel/adjust/force matching checks.
- AC9: Covered by save-template items and E2E Scenario 9.
- AC10: Covered by Team Run History and Agent participation checks.
- AC11: Covered by E2E Scenario 1.
- AC12: Covered by artifact traceability items and E2E Scenario 6.
- AC13: Covered by scripted unit, integration and e2e tests.
- AC14: Covered by frontend refresh recovery.
- AC15: Covered by regression checks.

