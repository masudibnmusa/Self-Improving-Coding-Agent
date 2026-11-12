from dataclasses import dataclass, field


def _covers(run_path: str, target: str) -> bool:
    """Whether running `run_path` (file, dir or node id) also runs `target`."""
    run_path = run_path.rstrip("/")
    return target == run_path or target.startswith((run_path + "::", run_path + "/"))


@dataclass
class AgentState:
    require_repro: bool = True
    step: int = 0
    attempts: int = 1
    edits: list = field(default_factory=list)
    test_runs: list = field(default_factory=list)
    source_edits: int = 0
    reproduced: bool = False
    repro_targets: list = field(default_factory=list)   # test paths that reproduced the bug
    baseline_failures: set | None = None   # failing node ids of the unmodified code (full suite)
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

    def record_test(self, result, paths=()):
        paths = [str(p) for p in paths]
        unmodified = self.source_edits == 0   # source is at the original commit (or reverted to it)

        # Only genuine test failures reproduce a bug: not "file not found", collection/syntax
        # errors, "no tests collected", timeouts or fixture errors (see PytestResult.reproduces_bug).
        if unmodified and result.scope == "targeted" and result.reproduces_bug:
            self.reproduced = True
            self.repro_targets += [p for p in paths if p not in self.repro_targets]
        if unmodified and result.scope == "full" and result.complete:
            self.baseline_failures = set(result.failed_ids)

        self.test_runs.append({
            "step": self.step, "seq": self._next(), "scope": result.scope, "paths": paths,
            "ok": result.ok, "complete": result.complete, "passed": result.passed,
            "failed": result.failed, "errors": result.errors,
            "failed_ids": list(result.failed_ids), "signature": result.signature(),
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

    def _no_new_failures(self, run) -> bool:
        """Full run passed, or it failed only on tests that already failed before any edit."""
        if run["ok"]:
            return True
        return (self.baseline_failures is not None and run["complete"]
                and set(run["failed_ids"]) <= self.baseline_failures)

    def verified(self) -> bool:
        """After the most recent source edit: every test that reproduced the bug passes, and the full
        suite shows no failures beyond those present on the unmodified code."""
        if self.source_edits == 0:
            return False
        if self.require_repro and not self.reproduced:
            return False
        after = [r for r in self.test_runs if r["seq"] > self._last_source_edit_seq]
        for target in self.repro_targets:
            if not any(r["scope"] == "targeted" and r["ok"] and any(_covers(p, target) for p in r["paths"])
                       for r in after):
                return False
        full = [r for r in after if r["scope"] == "full"]
        return bool(full) and self._no_new_failures(full[-1])

    def reset_for_new_attempt(self):
        self.attempts += 1
        self.source_edits = 0
        self._last_source_edit_seq = -1
        self._baseline = len(self.test_runs)
