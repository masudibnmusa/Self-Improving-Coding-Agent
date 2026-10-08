import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@dataclass
class Config:
    # model
    model: str = "claude-sonnet-5-5"
    max_output_tokens: int = 4096

    # budgets
    max_steps: int = 40
    max_cost_usd: float = 2.00
    timeout_seconds: int = 1800
    stuck_threshold: int = 3          # nudge at N identical failures, stop at 2N

    # context management
    tool_output_limit: int = 8000     # max chars returned from any tool call
    keep_recent_turns: int = 6        # older tool outputs get compacted

    # pricing, USD per million tokens (UPDATE to match your model's pricing)
    price_input_per_mtok: float = 3.0
    price_output_per_mtok: float = 15.0

    # sandbox
    base_image: str = "coding-agent-base"
    sandbox_cpus: float = 2.0
    sandbox_memory: str = "4g"
    sandbox_pids: int = 512
    sandbox_network: str = "none"     # "none" = no network at all
    command_timeout: int = 300

    # behavior
    reproduce_first: bool = True

    # paths
    repos_dir: Path = DATA / "repos"
    trajectories_dir: Path = DATA / "trajectories"
    patches_dir: Path = DATA / "patches"
    results_dir: Path = DATA / "benchmark_results"

    # secrets (host only, never passed into the container)
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))