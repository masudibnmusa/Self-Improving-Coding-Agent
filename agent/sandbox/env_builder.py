import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent.config import ROOT
from agent.utils.git import run_git

BASE_DOCKERFILE = ROOT / "docker" / "Dockerfile.base"


@dataclass
class EnvSpec:
    language: str
    image_tag: str


def detect_language(repo) -> str:
    repo = Path(repo)
    if any((repo / f).exists() for f in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")):
        return "python"
    raise NotImplementedError("Only Python repositories are supported right now.")


def render_dockerfile(repo, base_image: str) -> str:
    repo = Path(repo)
    lines = [
        f"FROM {base_image}", "WORKDIR /workspace", "COPY . /workspace",
        # The sandbox resets its working tree with git (see DockerSandbox.sync). If the repo's
        # .dockerignore dropped .git, snapshot the copied tree as the baseline commit instead.
        # This must happen BEFORE installing, so build output stays untracked.
        "RUN [ -d .git ] || (git init -q && git add -A && "
        "git -c user.name=sandbox -c user.email=sandbox@localhost commit -qm baseline)",
    ]
    if (repo / "requirements.txt").exists():
        lines.append("RUN pip install -r requirements.txt || echo 'requirements install failed'")
    if (repo / "setup.py").exists() or (repo / "pyproject.toml").exists():
        lines.append('RUN pip install -e ".[test,tests,dev]" || pip install -e . || echo "editable install failed"')
    lines.append("RUN pip install pytest")
    return "\n".join(lines) + "\n"


def _image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def ensure_base_image(cfg) -> None:
    """Build the base sandbox image from docker/Dockerfile.base if it is not present yet.
    Called by build_image, so every entry point (CLI, benchmark runner, run_task) gets it."""
    if _image_exists(cfg.base_image):
        return
    dockerfile = BASE_DOCKERFILE
    if not dockerfile.is_file():
        raise RuntimeError(f"base image '{cfg.base_image}' is missing and {dockerfile} was not found; "
                           "install the project from a checkout (`pip install -e .`) or build the image manually")
    print(f"Building base sandbox image '{cfg.base_image}' (first run only) ...")
    proc = subprocess.run(["docker", "build", "-f", str(dockerfile), "-t", cfg.base_image, str(dockerfile.parent)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"building base image '{cfg.base_image}' failed:\n{proc.stderr[-2000:]}")


def build_image(repo_path, cfg) -> EnvSpec:
    """Build (or reuse) an image with the repo's dependencies. Network is available at build time only."""
    ensure_base_image(cfg)
    repo_path = Path(repo_path).resolve()
    language = detect_language(repo_path)
    dockerfile = render_dockerfile(repo_path, cfg.base_image)

    sha = run_git("rev-parse", "HEAD", repo=repo_path).stdout.strip()
    key = hashlib.sha1(f"{repo_path}{sha}{dockerfile}".encode()).hexdigest()[:12]
    tag = f"coding-agent-env:{key}"

    if _image_exists(tag):
        return EnvSpec(language, tag)

    proc = subprocess.run(["docker", "build", "-f", "-", "-t", tag, str(repo_path)],
                          input=dockerfile, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"docker build failed:\n{proc.stderr[-2000:]}")
    return EnvSpec(language, tag)