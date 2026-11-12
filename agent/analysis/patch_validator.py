import configparser
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from agent.utils.git import run_git

TEST_PATTERNS = [
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)test_[^/]*\.py$"),
    re.compile(r"[^/]*_test\.py$"),
    re.compile(r"(^|/)conftest\.py$"),
]
REPRO_PREFIX = "repro_"
EXCLUDE_REPRO = ":(exclude,glob)**/repro_*"

# Files that only configure pytest: treated like test files (never editable).
PYTEST_ONLY_CONFIGS = {"pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml"}
# Shared config files: editable, but their pytest section must not change (e.g. adding
# `addopts = -k "not test_that_fails"` would hide failures without touching a test file).
SHARED_CONFIGS = {"setup.cfg", "pyproject.toml", "tox.ini"}
_UNPARSEABLE = object()


def is_test_path(path: str) -> bool:
    path = str(path).replace("\\", "/")
    return Path(path).name in PYTEST_ONLY_CONFIGS or any(p.search(path) for p in TEST_PATTERNS)


def pytest_settings(path: str, text: str):
    """The pytest section of a shared config file, as comparable data (None if absent)."""
    name = Path(str(path)).name
    if not text:
        return None
    try:
        if name == "pyproject.toml":
            return tomllib.loads(text).get("tool", {}).get("pytest")
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read_string(text)
        section = "tool:pytest" if name == "setup.cfg" else "pytest"
        return dict(parser[section]) if parser.has_section(section) else None
    except (tomllib.TOMLDecodeError, configparser.Error):
        return _UNPARSEABLE


def changes_pytest_config(path: str, old_text: str, new_text: str) -> bool:
    if Path(str(path)).name not in SHARED_CONFIGS:
        return False
    old, new = pytest_settings(path, old_text), pytest_settings(path, new_text)
    if new is _UNPARSEABLE:
        return old is not _UNPARSEABLE
    return old != new


def is_repro_path(path: str) -> bool:
    return Path(str(path)).name.startswith(REPRO_PREFIX)


def _git(repo, *args) -> str:
    return run_git(*args, repo=repo).stdout


def get_diff(repo) -> str:
    _git(repo, "add", "-N", ".")   # make new files show up in the diff
    # --no-ext-diff/--no-textconv: never run external diff programs from (untrusted) repo config.
    return _git(repo, "diff", "--no-ext-diff", "--no-textconv", "--", ".", EXCLUDE_REPRO)


def changed_files(repo) -> list[str]:
    out = _git(repo, "diff", "--no-ext-diff", "--name-only", "--", ".", EXCLUDE_REPRO)
    return [l for l in out.splitlines() if l]


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
        if Path(f).name in SHARED_CONFIGS:
            old = run_git("show", f"HEAD:{f}", repo=repo)
            new_path = Path(repo) / f
            new = new_path.read_text(encoding="utf-8", errors="replace") if new_path.is_file() else ""
            if changes_pytest_config(f, old.stdout if old.returncode == 0 else "", new):
                problems.append(f"changes pytest configuration in {f}")
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