import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path


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
    lines = [f"FROM {base_image}", "WORKDIR /workspace", "COPY . /workspace"]
    if (repo / "requirements.txt").exists():
        lines.append("RUN pip install -r requirements.txt || echo 'requirements install failed'")
    if (repo / "setup.py").exists() or (repo / "pyproject.toml").exists():
        lines.append('RUN pip install -e ".[test,tests,dev]" || pip install -e . || echo "editable install failed"')
    lines.append("RUN pip install pytest")
    return "\n".join(lines) + "\n"


def build_image(repo_path, cfg) -> EnvSpec:
    """Build (or reuse) an image with the repo's dependencies. Network is available at build time only."""
    repo_path = Path(repo_path).resolve()
    language = detect_language(repo_path)
    dockerfile = render_dockerfile(repo_path, cfg.base_image)

    sha = subprocess.run(["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    key = hashlib.sha1(f"{repo_path}{sha}{dockerfile}".encode()).hexdigest()[:12]
    tag = f"coding-agent-env:{key}"

    if subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0:
        return EnvSpec(language, tag)

    proc = subprocess.run(["docker", "build", "-f", "-", "-t", tag, str(repo_path)],
                          input=dockerfile, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"docker build failed:\n{proc.stderr[-2000:]}")
    return EnvSpec(language, tag)