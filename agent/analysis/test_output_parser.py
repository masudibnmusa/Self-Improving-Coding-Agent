import hashlib
import re
from dataclasses import dataclass, field

SECTION_RE = re.compile(r"^=+ (.+?) =+$")
CASE_RE = re.compile(r"^_{2,} (.+?) _{2,}$")
COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected)")
LOC_RE = re.compile(r"^\S+\.py:\d+")
TIME_RE = re.compile(r"\bin [\d.]+s")
PYTEST_TESTS_FAILED = 1   # pytest exit code: tests ran, some failed


@dataclass
class PytestResult:
    exit_code: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list = field(default_factory=list)
    failed_ids: list = field(default_factory=list)   # node ids from "short test summary info"
    summary: str = ""
    tail: str = ""
    scope: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def reproduces_bug(self) -> bool:
        """Tests ran and at least one FAILED. Excludes exit 2 (interrupted / collection error, e.g. a
        syntax error in the repro), 4 (usage error, e.g. file not found), 5 (no tests collected),
        timeouts, and runs where only setup/fixture ERRORs occurred."""
        return self.exit_code == PYTEST_TESTS_FAILED and self.failed > 0

    @property
    def complete(self) -> bool:
        """The run finished normally and every failure/error is identified by node id."""
        if self.exit_code == 0:
            return True
        return (self.exit_code == PYTEST_TESTS_FAILED
                and len(self.failed_ids) == self.failed + self.errors > 0)

    def signature(self) -> str:
        if self.ok:
            return "ok"
        key = "|".join(sorted(
            f["name"] + (f["error"][0] if f["error"] else "") for f in self.failures
        )) or self.tail[-300:]
        return hashlib.md5(key.encode()).hexdigest()[:10]

    def render(self, limit: int = 8000) -> str:
        status = "PASSED" if self.ok else "FAILED"
        out = [f"[{self.scope or 'tests'}] {status}: {self.summary or 'exit code ' + str(self.exit_code)}"]
        for f in self.failures[:10]:
            out.append(f"\n--- {f['name']}")
            out += f["error"]
            out += f["locations"]
        if len(self.failures) > 10:
            out.append(f"\n... and {len(self.failures) - 10} more failures")
        if not self.ok and not self.failures:
            out.append("\nRaw output tail:\n" + self.tail)
        return "\n".join(out)[:limit]


def parse_pytest_output(output: str, exit_code: int) -> PytestResult:
    lines = output.splitlines()
    res = PytestResult(exit_code=exit_code, tail="\n".join(lines[-40:]))

    # final summary line (with -q it has no '=' decoration)
    for line in reversed(lines):
        m = SECTION_RE.match(line)
        text = m.group(1) if m else line.strip()
        if TIME_RE.search(text) and (COUNT_RE.search(text) or "no tests ran" in text):
            res.summary = text
            for n, kind in COUNT_RE.findall(text):
                if kind == "passed":
                    res.passed = int(n)
                elif kind == "failed":
                    res.failed = int(n)
                elif kind.startswith("error"):
                    res.errors = int(n)
            break

    # FAILURES / ERRORS sections, and node ids from the short summary
    in_section, in_short, current = False, False, None
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            in_short = m.group(1) == "short test summary info"
            if m.group(1) in ("FAILURES", "ERRORS"):
                in_section, current = True, None
                continue
            if in_section:
                in_section, current = False, None
        if in_short:
            # "FAILED path::test[param] - message"; only read inside this section, because captured
            # log output elsewhere can also start with "ERROR ".
            for kind in ("FAILED ", "ERROR "):
                if line.startswith(kind):
                    node = line[len(kind):].split(" - ", 1)[0].strip()
                    if node not in res.failed_ids:
                        res.failed_ids.append(node)
            continue
        if not in_section:
            continue
        c = CASE_RE.match(line)
        if c:
            current = {"name": c.group(1), "lines": []}
            res.failures.append(current)
        elif current is not None:
            current["lines"].append(line)

    for f in res.failures:
        body = f.pop("lines")
        f["error"] = [l.rstrip() for l in body if l.startswith("E ")][:12]
        f["locations"] = [l for l in body if LOC_RE.match(l)][-3:]
    return res