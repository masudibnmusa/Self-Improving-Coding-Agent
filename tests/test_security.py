import os
import subprocess
from types import SimpleNamespace as NS

import pytest

from agent.analysis.patch_validator import validate_patch
from agent.config import Config
from agent.core.state import AgentState
from agent.github import repo_cloner
from agent.sandbox.docker_manager import DockerSandbox
from agent.tools.file_editor import create_file, str_replace_edit
from agent.tools.file_viewer import view_file
from agent.tools.registry import ToolContext
from agent.utils.cost_tracker import CostTracker


def git_repo(tmp_path):
    def g(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    g("init", "-q")
    g("config", "user.email", "t@t")
    g("config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    g("add", ".")
    g("commit", "-qm", "init")
    return tmp_path


def ctx(repo):
    return ToolContext(repo_path=repo, sandbox=None, state=AgentState(), config=Config())


# --- .git is off-limits to the agent's file tools ----------------------------------------

def test_cannot_edit_git_config(tmp_path):
    repo = git_repo(tmp_path)
    before = (repo / ".git" / "config").read_text()
    out = str_replace_edit(ctx(repo), ".git/config", "[core]", "[core]\n\tfsmonitor = touch PWNED")
    assert out.startswith("ERROR") and ".git" in out
    assert (repo / ".git" / "config").read_text() == before


def test_cannot_create_git_hook(tmp_path):
    repo = git_repo(tmp_path)
    out = create_file(ctx(repo), ".git/hooks/post-checkout", "#!/bin/sh\ntouch PWNED\n")
    assert out.startswith("ERROR")
    assert not (repo / ".git" / "hooks" / "post-checkout").exists()


def test_symlink_into_git_is_blocked(tmp_path):
    repo = git_repo(tmp_path)
    os.symlink(repo / ".git" / "config", repo / "innocent.cfg")
    assert str_replace_edit(ctx(repo), "innocent.cfg", "[core]", "[core]\n\tx = y").startswith("ERROR")
    assert view_file(ctx(repo), "innocent.cfg").startswith("ERROR")


def test_host_git_ignores_tampered_fsmonitor(tmp_path):
    """Even if .git/config is tampered with by other means, host-side git must not execute it."""
    repo = git_repo(tmp_path)
    marker = tmp_path / "PWNED"
    with (repo / ".git" / "config").open("a") as f:
        f.write(f"[core]\n\tfsmonitor = touch {marker}\n")
    (repo / "a.py").write_text("x = 2\n")
    validate_patch(repo)
    assert not marker.exists()


def test_host_git_ignores_hooks(tmp_path):
    """create_pr commits on the host; a planted pre-commit hook must not run."""
    from agent.github.pr_creator import _git as pr_git
    repo = git_repo(tmp_path)
    marker = tmp_path / "PWNED"
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    (repo / "a.py").write_text("x = 2\n")
    pr_git(repo, "tok", "commit", "-qam", "fix")
    assert not marker.exists()


def test_sandbox_mounts_nothing_from_host():
    """The host repo (and its .git) must not be reachable from the container."""
    import inspect
    src = inspect.getsource(DockerSandbox.start)
    assert "volumes" not in src and "mounts" not in src


# --- secrets ----------------------------------------------------------------------------

def test_clone_error_does_not_leak_token(monkeypatch):
    def fake_run_git(*args, repo=None):
        return NS(returncode=128, stdout="", stderr=f"fatal: could not read {args[1]}")
    monkeypatch.setattr(repo_cloner, "run_git", fake_run_git)

    with pytest.raises(RuntimeError) as e:
        repo_cloner._git(["clone", "https://x-access-token:SECRET123@github.com/o/r.git", "/tmp/x"],
                         token="SECRET123")
    assert "SECRET123" not in str(e.value)
    assert "***" in str(e.value)


# --- cost tracking ----------------------------------------------------------------------

def test_cost_tracker_prices_all_token_kinds():
    cfg = Config()
    c = CostTracker(cfg)
    c.add(NS(input_tokens=1_000_000, output_tokens=100_000,
             cache_creation_input_tokens=None, cache_read_input_tokens=None))
    c.add(NS(input_tokens=0, output_tokens=0,
             cache_creation_input_tokens=1_000_000, cache_read_input_tokens=1_000_000))
    # Default claude-sonnet-5-5 prices: 2.00 input + 1.00 output + 2.50 cache write + 0.10 cache read
    assert c.total_cost == pytest.approx(5.60)
    s = c.summary()
    assert s["calls"] == 2 and s["total_cost_usd"] == 5.6


def test_cost_tracker_uses_configured_prices():
    cfg = Config()
    cfg.price_input_per_mtok, cfg.price_output_per_mtok = 4.0, 20.0
    cfg.price_cache_write_per_mtok, cfg.price_cache_read_per_mtok = 5.0, 0.20
    c = CostTracker(cfg)
    c.add(NS(input_tokens=500_000, output_tokens=50_000,
             cache_creation_input_tokens=200_000, cache_read_input_tokens=1_000_000))
    assert c.total_cost == pytest.approx(2.0 + 1.0 + 1.0 + 0.2)
