from __future__ import annotations

from agentgov.event_stream.stream import EventStream
from agentgov.runtime.agent_loop import AgentLoop
from agentgov.runtime.state_machine import ensure_transition
from agentgov.scheduler.queue import RunQueue
from agentgov.storage.models import RunRecord, SessionRecord, now_iso
from agentgov.storage.repositories import Repository


class RunService:
    def __init__(self, repo: Repository, events: EventStream, loop: AgentLoop, queue: RunQueue | None = None):
        self.repo = repo
        self.events = events
        self.loop = loop
        self.queue = queue

    def create_session(self, title: str, owner_id: str, root_agent_id: str | None = None, team_id: str | None = None) -> SessionRecord:
        return self.repo.create_session(SessionRecord(title=title, owner_id=owner_id, root_agent_id=root_agent_id, team_id=team_id))

    def create_run(self, session_id: str, agent_id: str, input_summary: str, parent_run_id: str | None = None) -> RunRecord:
        run = self.repo.create_run(RunRecord(session_id=session_id, agent_id=agent_id, parent_run_id=parent_run_id, input_summary=input_summary))
        self.events.append(run.id, session_id, "run.started", "agent", agent_id, "started", {"input": input_summary})
        return run

    def enqueue_run(self, run_id: str, priority: int = 100) -> dict:
        if self.queue is None:
            return {"status": "unavailable", "reason": "queue is not configured"}
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        queue_id = self.queue.enqueue(run_id, run["session_id"], priority)
        self.events.append(run_id, run["session_id"], "queue.item.created", "system", "run_queue", "queued", {"queue_id": queue_id})
        return {"status": "queued", "queue_id": queue_id, "run_id": run_id}

    def execute(self, run_id: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {
                "status": run["status"],
                "response": run.get("output_summary") or "",
                "error": run.get("error"),
                "already_terminal": True,
            }
        if run["status"] == "paused":
            return {"status": "paused", "response": run.get("output_summary") or "", "error": "run is paused"}
        ensure_transition(run["status"], "running")
        self.repo.update_run_status(run_id, "running")
        self.events.append(run_id, run["session_id"], "run.status_changed", "system", "run_service", "completed", {"from": run["status"], "to": "running"})
        try:
            result = self.loop.run_once(run_id, run["session_id"], run["agent_id"], run["input_summary"])
        except Exception as exc:
            message = str(exc)
            self.repo.update_run_status(run_id, "failed", error=message)
            self.repo.update_session_status(run["session_id"], "failed", message)
            self.events.append(
                run_id,
                run["session_id"],
                "run.failed",
                "system",
                "run_service",
                "failed",
                {"status": "failed", "error": message},
            )
            return {"status": "failed", "response": "", "error": message}
        latest = self.repo.get_run(run_id)
        if result.get("requires_approval"):
            self.repo.update_run_status(run_id, "paused", output_summary=result.get("response", ""), error="waiting for tool approval")
            self.events.append(
                run_id,
                run["session_id"],
                "run.awaiting_approval",
                "system",
                "run_service",
                "paused",
                {"status": "paused", "result": result},
            )
            return {"status": "paused", **result}
        if latest and latest["status"] in {"paused", "cancelled"}:
            self.events.append(
                run_id,
                run["session_id"],
                "run.execution_deferred",
                "system",
                "run_service",
                latest["status"],
                {"status": latest["status"], "reason": "operator changed run state during execution"},
            )
            return {"status": latest["status"], "response": result.get("response", ""), "error": latest.get("error")}
        self.repo.update_run_status(run_id, "completed", output_summary=result["response"])
        self._record_child_result_message(run_id, result)
        self._finalize_session_after_run(run["session_id"])
        self.events.append(run_id, run["session_id"], "run.final", "system", "run_service", "completed", {"status": "completed", "result": result})
        return {"status": "completed", **result}

    def pause_run(self, run_id: str, reason: str = "operator requested pause") -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {"status": run["status"], "already_terminal": True}
        ensure_transition(run["status"], "paused")
        self.repo.update_run_status(run_id, "paused")
        self.events.append(run_id, run["session_id"], "run.paused", "operator", "operator", "paused", {"reason": reason})
        return {"status": "paused", "run_id": run_id}

    def cancel_run(self, run_id: str, reason: str = "operator cancelled run") -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {"status": run["status"], "already_terminal": True}
        ensure_transition(run["status"], "cancelled")
        self.repo.update_run_status(run_id, "cancelled", error=reason)
        self.events.append(run_id, run["session_id"], "run.cancelled", "operator", "operator", "cancelled", {"reason": reason})
        return {"status": "cancelled", "run_id": run_id}

    def resume_run(self, run_id: str, execute_now: bool = False) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] != "paused":
            return {"status": run["status"], "run_id": run_id, "unchanged": True}
        ensure_transition(run["status"], "pending")
        self.repo.update_run_status(run_id, "pending")
        self.events.append(run_id, run["session_id"], "run.resumed", "operator", "operator", "pending", {"execute_now": execute_now})
        if execute_now:
            return self.execute(run_id)
        return {"status": "pending", "run_id": run_id}

    def pause_session(self, session_id: str, reason: str = "operator requested pause") -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        changed = [self.pause_run(run["id"], reason) for run in runs if run["status"] not in {"completed", "failed", "rejected", "cancelled", "timeout", "paused"}]
        if self.queue:
            self.queue.cancel_session(session_id)
        self.repo.update_session_status(session_id, "paused", reason)
        return {"status": "paused", "session_id": session_id, "changed": changed}

    def cancel_session(self, session_id: str, reason: str = "operator cancelled session") -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        changed = [self.cancel_run(run["id"], reason) for run in runs if run["status"] not in {"completed", "failed", "rejected", "cancelled", "timeout"}]
        if self.queue:
            self.queue.cancel_session(session_id)
        self.repo.update_session_status(session_id, "cancelled", reason)
        return {"status": "cancelled", "session_id": session_id, "changed": changed}

    def resume_session(self, session_id: str, execute_now: bool = False) -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        changed = [self.resume_run(run["id"], execute_now=False) for run in runs if run["status"] == "paused"]
        self.repo.update_session_status(session_id, "pending", "operator resumed session")
        result: dict[str, object] = {"status": "pending", "session_id": session_id, "changed": changed}
        if execute_now:
            result["execution"] = self.execute_session_pending(session_id)
        return result

    def execute_session_pending(self, session_id: str) -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        results: dict[str, dict] = {}
        for run in runs:
            if run["status"] == "pending":
                results[run["id"]] = self.execute(run["id"])
        if results:
            self._finalize_session_after_run(session_id)
        return {"session_id": session_id, "executed": len(results), "results": results}

    def create_story_session(self, owner_id: str = "operator", execute_now: bool = True) -> dict:
        session = self.create_session(
            title="双 Agent 写作与评价 Session",
            owner_id=owner_id,
            root_agent_id="story_writer",
            team_id="story_team",
        )
        self.repo.update_session_status(session.id, "running", "story_writer writes a story, story_reviewer reviews it")

        writer = self.create_run(session.id, "story_writer", "写一个 300 字以内的小故事，并保存为 story.md")
        reviewer = self.create_run(
            session.id,
            "story_reviewer",
            "阅读 story.md，写一份结构化故事评价，并保存为 review.md",
            parent_run_id=writer.id,
        )
        if not execute_now:
            return {"session_id": session.id, "run_ids": [writer.id, reviewer.id], "executed": False}

        writer_result = self._execute_story_writer(writer.id)
        reviewer_result = self._execute_story_reviewer(reviewer.id)
        final_status = "completed" if writer_result["status"] == reviewer_result["status"] == "completed" else "failed"
        self.repo.update_session_status(
            session.id,
            final_status,
            "story.md and review.md created" if final_status == "completed" else "story demo failed; inspect run errors",
        )
        return {
            "session_id": session.id,
            "run_ids": [writer.id, reviewer.id],
            "executed": True,
            "status": final_status,
            "writer": writer_result,
            "reviewer": reviewer_result,
        }

    def create_team_task(
        self,
        *,
        title: str,
        owner_id: str,
        team_id: str,
        leader: str,
        members: list[str],
        input_summary: str,
        strategy: str,
        execute_now: bool = True,
    ) -> dict:
        session = self.create_session(title=title, owner_id=owner_id, root_agent_id=leader, team_id=team_id)
        self.repo.update_session_status(session.id, "running" if execute_now else "pending", f"{strategy}: {input_summary}")
        parent = self.create_run(session.id, leader, input_summary)
        self.repo.insert_generic(
            "collaboration_tasks",
            {
                "parent_run_id": parent.id,
                "assigned_agent_id": leader,
                "task_type": "lead",
                "instruction": input_summary,
                "status": "running" if execute_now else "pending",
                "created_at": now_iso(),
            },
        )

        child_ids: list[str] = []
        for member in [item for item in members if item != leader]:
            instruction = self._member_instruction(strategy, input_summary, member)
            self.repo.insert_generic(
                "agent_messages",
                {
                    "trace_id": parent.id,
                    "session_id": session.id,
                    "parent_run_id": parent.id,
                    "source_agent_id": leader,
                    "target_agent_id": member,
                    "message_type": "task.assigned",
                    "payload": {"strategy": strategy, "instruction": instruction},
                    "status": "sent",
                    "created_at": now_iso(),
                },
            )
            child = self.create_run(session.id, member, instruction, parent_run_id=parent.id)
            child_ids.append(child.id)
            self.repo.insert_generic(
                "collaboration_tasks",
                {
                    "parent_run_id": parent.id,
                    "assigned_agent_id": member,
                    "task_type": "worker",
                    "instruction": instruction,
                    "status": "pending",
                    "created_at": now_iso(),
                },
            )

        results: dict[str, dict] = {}
        if execute_now:
            parent_result = self.execute(parent.id)
            for child_id in child_ids:
                result = self.execute(child_id)
                child_run = self.repo.get_run(child_id)
                if child_run:
                    self.repo.insert_generic(
                        "agent_messages",
                        {
                            "trace_id": parent.id,
                            "session_id": session.id,
                            "parent_run_id": parent.id,
                            "source_agent_id": child_run["agent_id"],
                            "target_agent_id": leader,
                            "message_type": "task.result",
                            "payload": {"child_run_id": child_id, "status": result.get("status"), "summary": result.get("response", "")[:500]},
                            "status": "sent",
                            "created_at": now_iso(),
                        },
                    )
                results[child_id] = result
            final_status = "failed" if parent_result.get("status") == "failed" or any(item.get("status") == "failed" for item in results.values()) else "completed"
            self.repo.update_session_status(session.id, final_status, "team task completed" if final_status == "completed" else "team task failed")

        return {
            "session_id": session.id,
            "parent_run_id": parent.id,
            "child_run_ids": child_ids,
            "run_ids": [parent.id, *child_ids],
            "team_id": team_id,
            "strategy": strategy,
            "executed": execute_now,
            "status": self.repo.get_session(session.id)["status"],
            "results": results,
        }

    def _record_child_result_message(self, run_id: str, result: dict) -> None:
        run = self.repo.get_run(run_id)
        if not run or not run.get("parent_run_id"):
            return
        parent = self.repo.get_run(run["parent_run_id"])
        if not parent:
            return
        self.repo.insert_generic(
            "agent_messages",
            {
                "trace_id": parent["id"],
                "session_id": run["session_id"],
                "parent_run_id": parent["id"],
                "source_agent_id": run["agent_id"],
                "target_agent_id": parent["agent_id"],
                "message_type": "task.result",
                "payload": {
                    "child_run_id": run_id,
                    "status": "completed",
                    "summary": result.get("response", "")[:500],
                    "tool_results": result.get("tool_results", []),
                },
                "status": "sent",
                "created_at": now_iso(),
            },
        )
        self.events.append(
            run_id,
            run["session_id"],
            "agent.message.sent",
            "agent",
            run["agent_id"],
            "completed",
            {"target_agent_id": parent["agent_id"], "message_type": "task.result"},
        )

    def _finalize_session_after_run(self, session_id: str) -> None:
        runs = self.repo.list_runs_for_session(session_id)
        if not runs:
            return
        statuses = {run["status"] for run in runs}
        terminal = {"completed", "failed", "rejected", "cancelled", "timeout"}
        if any(status in {"failed", "rejected", "timeout"} for status in statuses):
            self.repo.update_session_status(session_id, "failed", "one or more runs failed")
            return
        if all(status in terminal for status in statuses):
            if any(status == "cancelled" for status in statuses):
                self.repo.update_session_status(session_id, "cancelled", "one or more runs were cancelled")
            else:
                self.repo.update_session_status(session_id, "completed", "all runs completed")
            return
        if any(status == "running" for status in statuses):
            self.repo.update_session_status(session_id, "running", "runs are still executing")
        else:
            self.repo.update_session_status(session_id, "pending", "waiting for remaining runs")

    def _member_instruction(self, strategy: str, input_summary: str, member: str) -> str:
        if strategy == "parallel_review":
            return f"从 {member} 的专业视角独立评审这个任务，输出风险、证据和建议：{input_summary}"
        if strategy == "planner_executor_reviewer":
            role_hint = {
                "evidence": "收集证据和上下文",
                "execution": "执行受限检查或验证",
                "policy_auditor": "审查权限、预算、HITL 和审计链",
                "reviewer": "评审最终结论是否有证据支撑",
            }.get(member, "完成分配给你的子任务")
            return f"{role_hint}。总任务：{input_summary}"
        return f"按 {strategy} 策略完成你的子任务。总任务：{input_summary}"

    def _execute_story_writer(self, run_id: str) -> dict:
        return self._execute_model_then_file(
            run_id,
            agent_id="story_writer",
            prompt=(
                "请写一个 300 字以内的小故事。要求：有标题、人物、冲突和结尾；"
                "直接输出故事正文，不要解释你将如何写。"
            ),
            output_path="story.md",
        )

    def _execute_story_reviewer(self, run_id: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        story = self.loop.tool_gateway.call(run_id, run["session_id"], "story_reviewer", "file_read", {"path": "story.md"})
        if story.get("status") != "completed":
            message = story.get("error") or "file_read failed for story.md"
            self.repo.update_run_status(run_id, "failed", error=message)
            self.events.append(run_id, run["session_id"], "run.failed", "system", "run_service", "failed", {"status": "failed", "error": message})
            return {"status": "failed", "response": "", "error": message}
        story_text = story.get("content", "")
        return self._execute_model_then_file(
            run_id,
            agent_id="story_reviewer",
            prompt=(
                "请评价下面这个小故事，输出：优点、问题、可修改建议、总体评分。\n\n"
                f"故事：\n{story_text}"
            ),
            output_path="review.md",
        )

    def _execute_model_then_file(self, run_id: str, agent_id: str, prompt: str, output_path: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {"status": run["status"], "response": run.get("output_summary") or "", "error": run.get("error")}
        ensure_transition(run["status"], "running")
        self.repo.update_run_status(run_id, "running")
        self.events.append(run_id, run["session_id"], "run.status_changed", "system", "run_service", "completed", {"from": run["status"], "to": "running"})
        try:
            response = self.loop.model_gateway.complete(run_id, run["session_id"], agent_id, prompt)
            tool_result = self.loop.tool_gateway.call(
                run_id,
                run["session_id"],
                agent_id,
                "file_write",
                {"path": output_path, "content": response.content},
            )
            if tool_result.get("status") != "completed":
                raise RuntimeError(tool_result.get("error") or f"file_write failed for {output_path}")
        except Exception as exc:
            message = str(exc)
            self.repo.update_run_status(run_id, "failed", error=message)
            self.repo.update_session_status(run["session_id"], "failed", message)
            self.events.append(run_id, run["session_id"], "run.failed", "system", "run_service", "failed", {"status": "failed", "error": message})
            return {"status": "failed", "response": "", "error": message}
        self.repo.update_run_status(run_id, "completed", output_summary=response.content)
        result = {"response": response.content, "tool_result": tool_result}
        self.events.append(run_id, run["session_id"], "run.final", "system", "run_service", "completed", {"status": "completed", "result": result})
        return {"status": "completed", **result}

