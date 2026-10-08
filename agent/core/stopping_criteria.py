import time
from dataclasses import dataclass


@dataclass
class StopDecision:
    stop: bool = False
    reason: str = ""


def check_stop(state, cost, cfg, started_at: float) -> StopDecision:
    if state.finished:
        return StopDecision(True, "agent_finished")
    if state.verified():
        return StopDecision(True, "verified")
    if state.step >= cfg.max_steps:
        return StopDecision(True, "max_steps")
    if cost.total_cost >= cfg.max_cost_usd:
        return StopDecision(True, "max_cost")
    if time.time() - started_at >= cfg.timeout_seconds:
        return StopDecision(True, "timeout")
    if state.consecutive_same_failure() >= cfg.stuck_threshold * 2:
        return StopDecision(True, "stuck")
    return StopDecision(False)