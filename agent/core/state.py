from dataclasses import dataclass, field


@dataclass
class AgentState:
    require_repro: bool = True
    step: int = 0
    attempts: int = 1
    edits: list = field(default_factory=list)
    test_runs: list = field(default_factory=list)
    source_edits: int = 0
    reproduced: bool = False
    finished: bool = False
    finish_status: str = ""
    finish_summary: str = ""
    _seq: int = 0
    _last_source_edit_seq: int = -1
    _baseline: int = 0   # test_runs index where the current attempt starts

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def record_edit(self, path: str, kind: str, is_source: bool = True):
        seq = self._next()
        self.edits.append({"step": self.step, "seq": seq, "path": path, "kind": kind, "source": is_source})
        if is_source:
            self.source_edits += 1
            self._last_source_edit_seq = seq

    def record_test(self, result):
        # A failing targeted run before any source edit counts as a reproduction.
        if not result.ok and result.scope == "targeted" and self.source_edits == 0:
            self.reproduced = True
        self.test_runs.append({
            "step": self.step, "seq": self._next(), "scope": result.scope,
            "ok": result.ok, "passed": result.passed, "failed": result.failed,
            "errors": result.errors, "signature": result.signature(),
        })

    def consecutive_same_failure(self) -> int:
        count, last = 0, None
        for run in reversed(self.test_runs[self._baseline:]):
            if run["ok"]:
                break
            if last is None:
                last = run["signature"]
            if run["signature"] != last:
                break
            count += 1
        return count

    def verified(self) -> bool:
        """Full suite passed after the most recent source edit."""
        if self.source_edits == 0:
            return False
        if self.require_repro and not self.reproduced:
            return False
        full = [r for r in self.test_runs if r["scope"] == "full"]
        return bool(full) and full[-1]["ok"] and full[-1]["seq"] > self._last_source_edit_seq

    def reset_for_new_attempt(self):
        self.attempts += 1
        self.source_edits = 0
        self._last_source_edit_seq = -1
        self._baseline = len(self.test_runs)