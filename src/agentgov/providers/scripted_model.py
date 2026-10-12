from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelResponse:
    content: str
    input_tokens: int
    output_tokens: int
    tool_intent: dict | None = None


class ScriptedModelProvider:
    def __init__(self, script: str = "default"):
        self.script = script

    def complete(self, prompt: str, agent_id: str, tools: list[dict] | None = None, system_prompt: str = "") -> ModelResponse:
        if agent_id == "story_writer":
            story = (
                "《雨夜的灯》\n\n"
                "小镇停电的夜晚，林安守着修表铺里最后一盏油灯。门外传来敲门声，一个迷路的孩子抱着坏掉的怀表，"
                "说那是母亲留下的礼物。林安本想明早再修，可孩子说，钟声停了，他就记不清回家的路。林安拆开表壳，"
                "发现里面夹着一张旧车票，终点正是孩子家的方向。他修好怀表，把油灯借给孩子。第二天清晨，孩子送回油灯，"
                "也带来一封信：原来林安多年前失散的妹妹，正住在那座终点站旁。那盏灯照亮的，不只是孩子的路。"
            )
            return ModelResponse(
                story,
                80,
                110,
                {"tool": "file_write", "path": "story.md", "content": story},
            )
        if agent_id == "story_reviewer":
            review = (
                "故事评价\n\n"
                "优点：故事有明确场景、人物目标和情感反转，油灯与怀表形成了不错的线索呼应。\n"
                "问题：孩子“钟声停了就记不清路”的设定略抽象，可以补一句解释增强可信度。\n"
                "修改建议：增加林安看到旧车票时的心理反应，让结尾的亲情线更自然。\n"
                "总体评分：8/10，适合作为短篇温情故事的初稿。"
            )
            return ModelResponse(
                review,
                120,
                90,
                {
                    "calls": [
                        {"tool": "file_read", "path": "story.md", "max_chars": 4000},
                        {"tool": "file_write", "path": "review.md", "content": review},
                    ]
                },
            )
        if agent_id == "evidence":
            return ModelResponse("Evidence collected via repo_search.", 30, 20, {"tool": "repo_search", "query": "audit"})
        if agent_id == "execution":
            return ModelResponse("Execution check should use sandbox.", 28, 18, {"tool": "local_command", "command": ["python", "--version"]})
        return ModelResponse(f"{agent_id} scripted response for: {prompt[:80]}", 25, 25)
