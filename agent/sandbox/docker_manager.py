import hashlib
import io
import tarfile
from pathlib import Path

from agent.utils.git import run_git

WORKDIR = "/workspace"
DELETED = "<deleted>"


class DockerSandbox:
    """One container per task, working on its OWN copy of the repo.

    The image already contains the repo at /workspace (env_builder COPYs it in and installs it), so
    in-place build output such as compiled C extensions stays visible. Nothing from the host is
    mounted: the host repo is the source of truth and the agent's edits (made on the host by the
    edit tools) are pushed into the container before every command. Consequences:
      * files created by tests never land on the host (no root-owned files there);
      * .git on the host is unreachable from the sandbox;
      * changes made inside the sandbox (e.g. `python -c` via run_shell) are NOT part of the patch,
        and `fresh=True` (used for test runs) discards them so tests see exactly the host state.
    """

    def __init__(self, image: str, repo_path, limits, container=None):
        self.image = image
        self.repo_path = Path(repo_path).resolve()
        self.limits = limits
        self.client = None
        self.container = container        # injectable for tests
        self._pushed: dict[str, str] = {}  # path -> digest of the host content last pushed
        self._image_untracked: set[str] = set()
        if container is not None:
            self._image_untracked = self._container_untracked()

    def start(self):
        import docker   # lazy: lets the sync logic be tested without the docker SDK/daemon

        self.client = docker.from_env()
        self.container = self.client.containers.run(
            self.image,
            command="sleep infinity",
            detach=True,
            working_dir=WORKDIR,
            environment={"PYTHONDONTWRITEBYTECODE": "1"},
            **self.limits.container_kwargs(),
        )
        # Untracked files that came with the image (build output not covered by .gitignore).
        self._image_untracked = self._container_untracked()

    # --- command execution -------------------------------------------------------------------

    def exec(self, cmd, timeout: int | None = None, fresh: bool = False) -> tuple[int, str]:
        """Run cmd in the container after syncing host edits. fresh=True first discards any
        changes made inside the container, so the run reflects exactly the host working tree."""
        self.sync(fresh=fresh)
        timeout = timeout or self.limits.command_timeout
        argv = list(cmd) if isinstance(cmd, (list, tuple)) else ["bash", "-lc", cmd]
        code, out = self._raw(["timeout", "-k", "5", str(timeout), *argv])
        if code == 124:
            out += f"\n[command timed out after {timeout}s]"
        return code, out

    def _raw(self, argv) -> tuple[int, str]:
        result = self.container.exec_run(list(argv), workdir=WORKDIR)
        return result.exit_code, result.output.decode("utf-8", errors="replace")

    # --- host -> container sync --------------------------------------------------------------

    def _host_changed(self) -> set[str]:
        """Paths differing from HEAD on the host: modified, deleted and untracked (not ignored)."""
        out = run_git("ls-files", "-z", "--modified", "--others", "--exclude-standard",
                      repo=self.repo_path).stdout
        return {p for p in out.split("\0") if p}

    def _container_untracked(self) -> set[str]:
        code, out = self._raw(["git", "ls-files", "-z", "--others", "--exclude-standard"])
        if code != 0:
            raise RuntimeError(f"sandbox has no usable git repo at {WORKDIR}: {out[-300:]}")
        return {p for p in out.split("\0") if p}

    def _digest(self, p: Path) -> str | None:
        if p.is_symlink():
            return "link:" + str(p.readlink())
        if p.is_file():
            return hashlib.sha1(p.read_bytes()).hexdigest()
        return None   # missing (deleted) or a directory

    def sync(self, fresh: bool = False):
        if fresh:
            # Undo in-container modifications: restore tracked files, drop new untracked files
            # (keeping those the image shipped with), then push every host change again.
            self._raw(["git", "checkout", "--", "."])
            extra = sorted(self._container_untracked() - self._image_untracked)
            if extra:
                self._raw(["rm", "-rf", "--", *extra])
            self._pushed.clear()

        to_push, to_delete = {}, []
        for rel in sorted(self._host_changed() | set(self._pushed)):
            digest = self._digest(self.repo_path / rel) or DELETED
            if self._pushed.get(rel) == digest:
                continue
            if digest == DELETED:
                to_delete.append(rel)
            else:
                to_push[rel] = digest

        if to_delete:
            self._raw(["rm", "-rf", "--", *to_delete])
            self._pushed.update({rel: DELETED for rel in to_delete})
        if to_push:
            parents = sorted({str(Path(r).parent) for r in to_push} - {"."})
            if parents:
                self._raw(["mkdir", "-p", "--", *parents])
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for rel in to_push:
                    info = tar.gettarinfo(str(self.repo_path / rel), arcname=rel)
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    if info.isfile():
                        with open(self.repo_path / rel, "rb") as f:
                            tar.addfile(info, f)
                    else:
                        tar.addfile(info)
            self.container.put_archive(WORKDIR, buf.getvalue())
            self._pushed.update(to_push)

    def stop(self):
        if self.container is not None:
            try:
                self.container.remove(force=True)
            finally:
                self.container = None
