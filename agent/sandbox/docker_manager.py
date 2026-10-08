from pathlib import Path

import docker


class DockerSandbox:
    """One container per task. The repo is bind-mounted at /workspace."""

    def __init__(self, image: str, repo_path, limits):
        self.image = image
        self.repo_path = Path(repo_path).resolve()
        self.limits = limits
        self.client = None
        self.container = None

    def start(self):
        self.client = docker.from_env()
        self.container = self.client.containers.run(
            self.image,
            command="sleep infinity",
            detach=True,
            working_dir="/workspace",
            volumes={str(self.repo_path): {"bind": "/workspace", "mode": "rw"}},
            environment={"PYTHONDONTWRITEBYTECODE": "1"},
            **self.limits.container_kwargs(),
        )

    def exec(self, cmd, timeout: int | None = None) -> tuple[int, str]:
        timeout = timeout or self.limits.command_timeout
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else ["bash", "-lc", cmd]
        result = self.container.exec_run(["timeout", "-k", "5", str(timeout), *argv], workdir="/workspace")
        out = result.output.decode("utf-8", errors="replace")
        if result.exit_code == 124:
            out += f"\n[command timed out after {timeout}s]"
        return result.exit_code, out

    def stop(self):
        if self.container is not None:
            try:
                self.container.remove(force=True)
            finally:
                self.container = None