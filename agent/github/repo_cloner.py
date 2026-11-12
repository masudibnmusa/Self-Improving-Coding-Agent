import shutil
from pathlib import Path

from agent.utils.git import redact, run_git


def _git(args: list[str], token: str = "") -> str:
    proc = run_git(*args)
    if proc.returncode != 0:
        # Redact the whole message: args can contain the authenticated clone URL.
        msg = f"git {' '.join(args[:3])} failed: {proc.stderr[-1000:]}"
        raise RuntimeError(redact(msg, token))
    return proc.stdout.strip()


def clone_repo(owner: str, repo: str, dest, token: str = "", commit: str | None = None):
    """Clone into dest (replacing it), optionally checkout a commit. Returns (path, head_sha)."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    clean_url = f"https://github.com/{owner}/{repo}.git"
    auth_url = clean_url.replace("https://", f"https://x-access-token:{token}@") if token else clean_url

    _git(["clone", auth_url, str(dest)], token)
    # Remove the token from .git/config: the repo is mounted into the sandbox.
    _git(["-C", str(dest), "remote", "set-url", "origin", clean_url])
    if commit:
        _git(["-C", str(dest), "checkout", "--detach", commit])

    _git(["-C", str(dest), "config", "user.name", "coding-agent"])
    _git(["-C", str(dest), "config", "user.email", "coding-agent@example.com"])
    sha = _git(["-C", str(dest), "rev-parse", "HEAD"])
    return dest, sha