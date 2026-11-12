import subprocess

# Applied to every git call made on the HOST. Command-line `-c` overrides repo config, so even a
# tampered .git/config cannot make the host run hook scripts or an fsmonitor command.
# Primary defense is that .git is never writable by the agent (see file_viewer.safe_path and the
# read-only .git mount in docker_manager); this is the second layer.
HARDENING = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"]


def run_git(*args: str, repo=None) -> subprocess.CompletedProcess:
    cmd = ["git", *HARDENING]
    if repo is not None:
        cmd += ["-C", str(repo)]
    return subprocess.run([*cmd, *args], capture_output=True, text=True)


def redact(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text
