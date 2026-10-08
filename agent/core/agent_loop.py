import time
from dataclasses import dataclass

from agent.analysis.context_builder import build_initial_message, compact_history, truncate
from agent.core.stopping_criteria import check_stop
from agent.llm.prompts import SYSTEM_PROMPT
from agent.tools.registry import TOOL_SCHEMAS, execute_tool


@dataclass
class RunOutcome:
    reason: str
    steps: int


def run_agent(issue, ctx, llm, cost, logger, strategy, repo_map_text: str = "") -> RunOutcome:
    cfg, state = ctx.config, ctx.state
    started = time.time()
    messages = [{"role": "user", "content": build_initial_message(issue, repo_map_text, cfg)}]
    logger.log("start", issue=issue.title, model=cfg.model)
    idle_turns = 0

    while True:
        decision = check_stop(state, cost, cfg, started)
        if decision.stop:
            logger.log("stop", reason=decision.reason)
            return RunOutcome(decision.reason, state.step)

        state.step += 1
        compact_history(messages, cfg.keep_recent_turns)
        resp = llm.create(SYSTEM_PROMPT, messages, TOOL_SCHEMAS)
        messages.append({"role": "assistant", "content": resp.content})

        text = "\n".join(b.text for b in resp.content if b.type == "text")
        logger.log("assistant", step=state.step, text=text, cost=round(cost.total_cost, 4))

        calls = [b for b in resp.content if b.type == "tool_use"]
        if not calls:
            idle_turns += 1
            if idle_turns >= 2:
                logger.log("stop", reason="no_tool_calls")
                return RunOutcome("no_tool_calls", state.step)
            messages.append({"role": "user",
                             "content": "Continue using tools, or call `finish` if you are done."})
            continue
        idle_turns = 0

        results = []
        for call in calls:
            output = execute_tool(call.name, call.input, ctx)
            logger.log("tool", step=state.step, name=call.name, input=call.input, output=output[:3000])
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id,
                "content": truncate(output, cfg.tool_output_limit),
            })

        nudge = strategy.nudge(state)
        if nudge:
            logger.log("nudge", step=state.step, text=nudge)
            results.append({"type": "text", "text": nudge})
        messages.append({"role": "user", "content": results})