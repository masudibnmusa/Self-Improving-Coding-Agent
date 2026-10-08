from agent.llm.prompts import LOW_BUDGET_NUDGE, NO_REPRO_NUDGE, STUCK_NUDGE


class StrategyManager:
    """Decides what guidance to inject between steps (reproduce-first, retry, backtrack)."""

    def __init__(self, cfg):
        self.cfg = cfg

    def phase(self, state) -> str:
        if self.cfg.reproduce_first and not state.reproduced and state.source_edits == 0:
            return "reproduce"
        if state.verified():
            return "done"
        return "fix"

    def nudge(self, state) -> str | None:
        same = state.consecutive_same_failure()
        if same >= self.cfg.stuck_threshold:
            return STUCK_NUDGE.format(n=same)
        if self.phase(state) == "reproduce" and state.step >= 8:
            return NO_REPRO_NUDGE
        remaining = self.cfg.max_steps - state.step
        if remaining <= 5:
            return LOW_BUDGET_NUDGE.format(n=remaining)
        return None