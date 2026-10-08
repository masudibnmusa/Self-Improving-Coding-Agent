from types import SimpleNamespace as NS

from agent.config import Config
from agent.core.agent_loop import run_agent
from agent.core.state import AgentState
from agent.core.strategy_manager import StrategyManager
from agent.github.issue_fetcher import Issue
from agent.tools.registry import ToolContext
from agent.utils.cost_tracker import CostTracker
from agent.utils.trajectory_logger import TrajectoryLogger


def tool_call(id, name, **inp):
    return NS(type="tool_use", id=id, name=name, input=inp)


def reply(*blocks, stop="tool_use"):
    return NS(content=list(blocks), stop_reason=stop)


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)

    def create(self, system, messages, tools):
        return self.replies.pop(0)


def build(tmp_path, replies):
    (tmp_path / "a.py").write_text("x = 1\n")
    cfg = Config()
    state = AgentState()
    ctx = ToolContext(repo_path=tmp_path, sandbox=None, state=state, config=cfg)
    cost = CostTracker(cfg)
    logger = TrajectoryLogger(tmp_path / "traj" / "t.json")
    issue = Issue("o", "r", 1, "title", "body")
    return ctx, state, cost, logger, issue, FakeLLM(replies)


def test_loop_runs_tool_then_finishes(tmp_path):
    replies = [
        reply(NS(type="text", text="Let me look."), tool_call("1", "view_file", path="a.py")),
        reply(tool_call("2", "finish", status="done", summary="ok")),
    ]
    ctx, state, cost, logger, issue, llm = build(tmp_path, replies)
    outcome = run_agent(issue, ctx, llm, cost, logger, StrategyManager(ctx.config))
    assert outcome.reason == "agent_finished"
    assert state.step == 2
    assert state.finish_summary == "ok"
    assert any(e["kind"] == "tool" and e["name"] == "view_file" for e in logger.events)


def test_loop_stops_when_model_never_calls_tools(tmp_path):
    text_only = reply(NS(type="text", text="thinking..."), stop="end_turn")
    ctx, state, cost, logger, issue, llm = build(tmp_path, [text_only, text_only])
    outcome = run_agent(issue, ctx, llm, cost, logger, StrategyManager(ctx.config))
    assert outcome.reason == "no_tool_calls"


def test_unknown_tool_returns_error_and_loop_continues(tmp_path):
    replies = [
        reply(tool_call("1", "does_not_exist")),
        reply(tool_call("2", "finish", status="give_up", summary="nope")),
    ]
    ctx, state, cost, logger, issue, llm = build(tmp_path, replies)
    outcome = run_agent(issue, ctx, llm, cost, logger, StrategyManager(ctx.config))
    assert outcome.reason == "agent_finished"
    assert state.finish_status == "give_up"