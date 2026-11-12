"""Regression tests for the correctness fixes (PR gating, CRLF, reproduction/verification rules,
repo_map paths, sandbox sync, pytest-config protection, resolved status)."""
import io
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from agent import main as main_mod
from agent.analysis.patch_validator import Validation, validate_patch
from agent.analysis.test_output_parser import PytestResult, parse_pytest_output
from agent.config import Config
from agent.core.state import AgentState
from agent.sandbox.docker_manager import DockerSandbox
from agent.sandbox.resource_limits import ResourceLimits
from agent.tools.file_editor import create_file, revert_changes, str_replace_edit
from agent.tools.registry import ToolContext
from agent.tools.repo_map import repo_map


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


def make_repo(path, files):
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@t")
    git(path, "config", "user.name", "t")
    for name, content in files.items():
        (path / name).parent.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(content if isinstance(content, bytes) else content.encode())
    git(path, "add", ".")
    git(path, "commit", "-qm", "init")
    return path


def ctx(repo, sandbox=None, state=None):
    return ToolContext(repo_path=repo, sandbox=sandbox, state=state or AgentState(), config=Config())


def res(exit_code, scope="targeted", failed=0, errors=0, failed_ids=()):
    return PytestResult(exit_code=exit_code, scope=scope, failed=failed, errors=errors,
                        failed_ids=list(failed_ids),
                        failures=[{"name": "t", "error": ["E x"], "locations": []}] if exit_code else [])


# --- 4 / 12: status and PR gating --------------------------------------------------------

@pytest.mark.parametrize("finish_status,verified,valid,expected_status,pr", [
    ("give_up", False, True, "unresolved", False),   # gave up but left a valid diff: no PR
    ("", False, True, "unresolved", False),          # hit max_steps
    ("done", False, True, "unverified", False),      # claimed done without test evidence
    ("done", True, True, "resolved", True),
    ("done", True, False, "unresolved", False),      # verified but patch rejected
])
def test_status_and_pr_gating(tmp_path, monkeypatch, finish_status, verified, valid, expected_status, pr):
    created = []

    def fake_run_agent(issue, tool_ctx, *a, **k):
        tool_ctx.state.finish_status = finish_status
        tool_ctx.state.verified = lambda: verified
        return NS(reason="x")

    monkeypatch.setattr(main_mod, "build_image", lambda *a: NS(image_tag="img"))
    monkeypatch.setattr(main_mod, "DockerSandbox", lambda *a: NS(start=lambda: None, stop=lambda: None))
    monkeypatch.setattr(main_mod, "LLMClient", lambda *a: None)
    monkeypatch.setattr(main_mod, "run_agent", fake_run_agent)
    monkeypatch.setattr(main_mod, "validate_patch", lambda repo: Validation(
        ok=valid, diff="diff --git a/x b/x\n+1\n", problems=[] if valid else ["bad"]))
    monkeypatch.setattr(main_mod, "create_pr", lambda *a: created.append(1) or "https://pr")

    cfg = Config()
    for attr in ("trajectories_dir", "patches_dir"):
        setattr(cfg, attr, tmp_path / attr)
    (tmp_path / "repo").mkdir()
    issue = NS(repo="r", number=1)
    r = main_mod.run_task(issue, tmp_path / "repo", cfg, open_pr=True, run_id="t")
    assert r.status == expected_status
    assert bool(created) == pr


# --- 5: CRLF -------------------------------------------------------------------------------

def test_crlf_file_keeps_line_endings_and_diff_is_minimal(tmp_path):
    body = b"".join(b"x%d = %d\r\n" % (i, i) for i in range(300))
    repo = make_repo(tmp_path / "r", {"crlf.py": body})
    out = str_replace_edit(ctx(repo), "crlf.py", "x5 = 5\nx6 = 6", "x5 = 50\nx6 = 6")
    assert out.startswith("OK"), out
    data = (repo / "crlf.py").read_bytes()
    assert b"x5 = 50\r\nx6 = 6\r\n" in data
    assert data.count(b"\r\n") == 300 and data.count(b"\n") == 300
    v = validate_patch(repo)
    assert v.ok, v.problems
    assert sum(1 for l in v.diff.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")) == 2


def test_lf_and_mixed_files_untouched_elsewhere(tmp_path):
    repo = make_repo(tmp_path / "r", {"m.py": b"a = 1\r\nb = 2\nc = 3\n"})
    assert str_replace_edit(ctx(repo), "m.py", "c = 3", "c = 4").startswith("OK")
    assert (repo / "m.py").read_bytes() == b"a = 1\r\nb = 2\nc = 4\n"


# --- 6: what counts as a reproduction ----------------------------------------------------------

@pytest.mark.parametrize("result,reproduced", [
    (res(1, failed=1), True),                  # genuine test failure
    (res(4), False),                           # usage error: file not found
    (res(2, errors=1), False),                 # collection error, e.g. syntax error in repro
    (res(5), False),                           # no tests collected
    (res(124), False),                         # timeout
    (res(1, errors=1), False),                 # only a fixture/setup error
])
def test_reproduction_requires_real_failure(result, reproduced):
    s = AgentState()
    s.record_test(result, ["repro_bug.py"])
    assert s.reproduced is reproduced
    assert s.repro_targets == (["repro_bug.py"] if reproduced else [])


def test_parser_exit_codes_from_real_output():
    out = "ERROR: file or directory not found: repro_nope.py\n\nno tests ran in 0.01s\n"
    assert not parse_pytest_output(out, 4).reproduces_bug


# --- 7: verification re-checks the repro ---------------------------------------------------

def reproduce_and_edit(state):
    state.record_test(res(1, failed=1), ["repro_bug.py"])
    state.record_edit("src/x.py", "str_replace")


def test_not_verified_until_repro_passes_after_edit():
    s = AgentState()
    reproduce_and_edit(s)
    s.record_test(res(0, scope="full"))
    assert not s.verified()                                      # repro never re-run
    s.record_test(res(0), ["repro_bug.py::test_it"])            # narrower than the target: no
    assert not s.verified()
    s.record_test(res(0), ["repro_bug.py"])
    assert s.verified()


def test_repro_pass_before_last_edit_does_not_count():
    s = AgentState()
    reproduce_and_edit(s)
    s.record_test(res(0), ["repro_bug.py"])
    s.record_test(res(0, scope="full"))
    s.record_edit("src/x.py", "str_replace")
    s.record_test(res(0, scope="full"))
    assert not s.verified()


def test_preexisting_failures_tolerated_new_ones_not():
    s = AgentState()
    s.record_test(res(1, scope="full", failed=1, failed_ids=["tests/t.py::old"]))   # baseline
    reproduce_and_edit(s)
    s.record_test(res(0), ["repro_bug.py"])
    s.record_test(res(1, scope="full", failed=1, failed_ids=["tests/t.py::old"]))
    assert s.verified()
    s.record_test(res(1, scope="full", failed=2, failed_ids=["tests/t.py::old", "tests/t.py::new"]))
    assert not s.verified()


def test_incomplete_full_run_never_verifies():
    s = AgentState()
    s.record_test(res(1, scope="full", failed=1, failed_ids=["a::x"]))
    reproduce_and_edit(s)
    s.record_test(res(0), ["repro_bug.py"])
    s.record_test(res(1, scope="full", failed=2, failed_ids=["a::x"]))   # one failure unidentified
    assert not s.verified()


def test_parser_reads_failed_ids_only_from_short_summary():
    out = """\
=================================== FAILURES ===================================
___________________________________ test_a ____________________________________
------------------------------ Captured log call -------------------------------
ERROR    root:mod.py:3 something logged
E       assert 1 == 2
tests/test_m.py:4: AssertionError
=========================== short test summary info ============================
FAILED tests/test_m.py::test_a - assert 1 == 2
FAILED tests/test_m.py::test_p[a - b] - boom
ERROR tests/test_broken.py
2 failed, 1 error in 0.10s
"""
    r = parse_pytest_output(out, 1)
    assert r.failed_ids == ["tests/test_m.py::test_a", "tests/test_m.py::test_p[a", "tests/test_broken.py"]
    assert r.complete


# --- 8: repo_map paths -----------------------------------------------------------------------

def test_repo_map_accepts_workspace_paths(tmp_path):
    repo = make_repo(tmp_path / "r", {"pkg/mod.py": "def f(x):\n    return x\n"})
    for p in ("/workspace", "/workspace/", "/workspace/pkg", "pkg", ""):
        out = repo_map(ctx(repo), p)
        assert "pkg/mod.py" in out and "def f(x)" in out, (p, out)
    assert repo_map(ctx(repo), "../").startswith("ERROR")
    assert repo_map(ctx(repo), ".git").startswith("ERROR")


# --- 9 / 10 / 13: sandbox works on its own copy ---------------------------------------------

class LocalContainer:
    """Stands in for a docker container: runs commands in a local directory."""

    def __init__(self, root: Path):
        self.root = root

    def exec_run(self, argv, workdir=None):
        p = subprocess.run(argv, cwd=self.root, capture_output=True)
        return NS(exit_code=p.returncode, output=p.stdout + p.stderr)

    def put_archive(self, path, data):
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(self.root, filter="tar")
        return True

    def remove(self, force=False):
        pass


@pytest.fixture
def sandbox_env(tmp_path):
    host = make_repo(tmp_path / "host", {"pkg/mod.py": "VALUE = 1\n", ".gitignore": "*.so\n"})
    image = tmp_path / "image"
    subprocess.run(["git", "clone", "-q", str(host), str(image)], check=True)   # == COPY . /workspace
    (image / "pkg" / "_ext.so").write_text("compiled")          # in-place build output (ignored)
    (image / "pkg" / "generated.py").write_text("GEN = 1\n")    # build output not in .gitignore
    sb = DockerSandbox("img", host, ResourceLimits(), container=LocalContainer(image))
    return host, image, sb, ctx(host, sandbox=sb)


def test_host_edits_reach_sandbox_and_build_output_survives(sandbox_env):
    host, image, sb, c = sandbox_env
    assert str_replace_edit(c, "pkg/mod.py", "VALUE = 1", "VALUE = 2").startswith("OK")
    assert create_file(c, "pkg/sub/new.py", "NEW = 1\n").startswith("OK")
    code, out = sb.exec(["cat", "pkg/mod.py", "pkg/sub/new.py"], fresh=True)
    assert code == 0 and "VALUE = 2" in out and "NEW = 1" in out
    assert (image / "pkg" / "_ext.so").exists()          # 9: not hidden or removed
    assert (image / "pkg" / "generated.py").exists()


def test_sandbox_changes_never_reach_host_and_fresh_discards_them(sandbox_env):
    host, image, sb, c = sandbox_env
    sb.exec(["python", "-c", "open('pkg/mod.py','w').write('HACKED = 1\\n'); open('junk.txt','w').write('x')"])
    assert (host / "pkg" / "mod.py").read_text() == "VALUE = 1\n"   # 10/13: host untouched
    assert not (host / "junk.txt").exists()
    _, out = sb.exec(["cat", "pkg/mod.py"], fresh=True)              # what tests would see
    assert "VALUE = 1" in out and not (image / "junk.txt").exists()


def test_deletes_and_reverts_propagate(sandbox_env):
    host, image, sb, c = sandbox_env
    str_replace_edit(c, "pkg/mod.py", "VALUE = 1", "VALUE = 2")
    (host / ".gitignore").unlink()
    sb.exec(["true"])
    assert "VALUE = 2" in (image / "pkg" / "mod.py").read_text()
    assert not (image / ".gitignore").exists()
    revert_changes(c)
    sb.exec(["true"])
    assert (image / "pkg" / "mod.py").read_text() == "VALUE = 1\n"
    assert (image / ".gitignore").exists()


# --- 11: pytest configuration is protected ----------------------------------------------------

SETUP_CFG = "[metadata]\nname = pkg\n\n[tool:pytest]\ntestpaths = tests\n"
PYPROJECT = '[project]\nname = "pkg"\ndependencies = []\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'


def test_edit_tool_blocks_pytest_config_changes(tmp_path):
    repo = make_repo(tmp_path / "r", {"setup.cfg": SETUP_CFG, "pyproject.toml": PYPROJECT, "tox.ini": "[tox]\n"})
    c = ctx(repo)
    assert str_replace_edit(c, "setup.cfg", "testpaths = tests", "testpaths = tests\naddopts = -k 'not x'").startswith("ERROR")
    assert str_replace_edit(c, "pyproject.toml", 'testpaths = ["tests"]', 'addopts = "-p no:x"').startswith("ERROR")
    assert str_replace_edit(c, "tox.ini", "[tox]", "[tox]\n\n[pytest]\naddopts = -x").startswith("ERROR")
    assert create_file(c, "pytest.ini", "[pytest]\naddopts = -k 'not x'\n").startswith("ERROR")
    assert create_file(c, "sub/setup.cfg", "[tool:pytest]\naddopts = -x\n").startswith("ERROR")
    # Non-pytest edits to the same files are fine.
    assert str_replace_edit(c, "setup.cfg", "name = pkg", "name = pkg2").startswith("OK")
    assert str_replace_edit(c, "pyproject.toml", "dependencies = []", 'dependencies = ["x"]').startswith("OK")


def test_validator_catches_pytest_config_changes_made_any_way(tmp_path):
    repo = make_repo(tmp_path / "r", {"setup.cfg": SETUP_CFG, "pkg.py": "x = 1\n"})
    (repo / "setup.cfg").write_text(SETUP_CFG + "addopts = -k 'not slow'\n")
    (repo / "pytest.ini").write_text("[pytest]\n")
    problems = validate_patch(repo).problems
    assert any("pytest configuration in setup.cfg" in p for p in problems)
    assert any("modifies test file: pytest.ini" in p for p in problems)


def test_validator_allows_non_pytest_config_change(tmp_path):
    repo = make_repo(tmp_path / "r", {"setup.cfg": SETUP_CFG})
    (repo / "setup.cfg").write_text(SETUP_CFG.replace("name = pkg", "name = other"))
    assert validate_patch(repo).ok
