import hashlib
import re
from dataclasses import dataclass, field

SECTION_RE = re.compile(r"^=+ (.+?) =+$")
CASE_RE = re.compile(r"^_{2,} (.+?) _{2,}$")
COUNT_RE = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|warnings?|deselected)")
LOC_RE = re.compile(r"^\S+\.py:\d+")
TIME_RE = re.compile(r"\bin [\d.]+s")


@dataclass
class PytestResult:
    exit_code: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    failures: list = field(default_factory=list)
    summary: str = ""
    tail: str = ""
    scope: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

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

    # FAILURES / ERRORS sections
    in_section, current = False, None
    for line in lines:
        m = SECTION_RE.match(line)
        if m:
            if m.group(1) in ("FAILURES", "ERRORS"):
                in_section, current = True, None
                continue
            if in_section:
                in_section, current = False, None
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