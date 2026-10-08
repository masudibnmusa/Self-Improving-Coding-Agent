import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

TEST_PATTERNS = [
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)test_[^/]*\.py$"),
    re.compile(r"[^/]*_test\.py$"),
    re.compile(r"(^|/)conftest\.py$"),
]
REPRO_PREFIX = "repro_"
EXCLUDE_REPRO = ":(exclude,glob)**/repro_*"


def is_test_path(path: str) -> bool:
    path = str(path).replace("\\", "/")
    return any(p.search(path) for p in TEST_PATTERNS)


def is_repro_path(path: str) -> bool:
    return Path(str(path)).name.startswith(REPRO_PREFIX)


def _git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout


def get_diff(repo) -> str:
    _git(repo, "add", "-N", ".")   # make new files show up in the diff
    return _git(repo, "diff", "--", ".", EXCLUDE_REPRO)


def changed_files(repo) -> list[str]:
    return [l for l in _git(repo, "diff", "--name-only", "--", ".", EXCLUDE_REPRO).splitlines() if l]


@dataclass
class Validation:
    ok: bool
    diff: str
    files: list = field(default_factory=list)
    problems: list = field(default_factory=list)


def validate_patch(repo, max_changed_lines: int = 400) -> Validation:
    """The real safety net: even if the agent bypasses the edit tool, bad patches are rejected here."""
    diff = get_diff(repo)
    files = changed_files(repo)
    problems = []

    if not diff.strip():
        problems.append("empty patch")

    for f in files:
        if is_test_path(f):
            problems.append(f"modifies test file: {f}")
        if f.endswith(".py"):
            try:
                compile((Path(repo) / f).read_text(encoding="utf-8"), f, "exec")
            except SyntaxError as e:
                problems.append(f"syntax error in {f}: {e.msg} (line {e.lineno})")
            except FileNotFoundError:
                pass   # deleted file

    changed = sum(1 for l in diff.splitlines()
                  if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    if changed > max_changed_lines:
        problems.append(f"patch too large ({changed} changed lines)")

    return Validation(ok=not problems, diff=diff, files=files, problems=problems)