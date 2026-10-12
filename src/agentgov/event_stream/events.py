from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    RUN_STATUS_CHANGED = "run.status_changed"
    MODEL_CALL_STARTED = "model.call.started"
    MODEL_CALL_FINISHED = "model.call.finished"
    MODEL_CALL_FAILED = "model.call.failed"
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_FINISHED = "tool.call.finished"
    TOOL_CALL_FAILED = "tool.call.failed"
    SANDBOX_ACTION_STARTED = "sandbox.action.started"
    SANDBOX_ACTION_FINISHED = "sandbox.action.finished"
    POLICY_DECISION = "policy.decision"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_DECIDED = "approval.decided"
    COLLABORATION_DELEGATED = "collaboration.delegated"
    COLLABORATION_RESULT = "collaboration.result"
    MEMORY_EXPERIENCE_CREATED = "memory.experience_candidate_created"
    RUN_FINAL = "run.final"


class ActorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"


class StepStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"
    DENIED = "denied"
