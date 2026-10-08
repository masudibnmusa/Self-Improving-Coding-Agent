import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from agent.analysis.patch_validator import validate_patch
from agent.config import Config
from agent.core.agent_loop import run_agent
from agent.core.state import AgentState
from agent.core.strategy_manager import StrategyManager
from agent.github.issue_fetcher import fetch_issue
from agent.github.pr_creator import create_pr
from agent.github.repo_cloner import clone_repo
from agent.llm.llm_client import LLMClient
from agent.sandbox.docker_manager import DockerSandbox
from agent.sandbox.env_builder import build_image
from agent.sandbox.resource_limits import ResourceLimits
from agent.tools.registry import ToolContext
from agent.tools.repo_map import build_repo_map
from agent.utils.cost_tracker import CostTracker
from agent.utils.trajectory_logger import TrajectoryLogger


@dataclass
class TaskResult:
    run_id: str
    status: str                 # "resolved" | "unresolved"
    reason: str
    verified: bool
    steps: int
    cost: float
    patch: str = ""
    patch_path: str = ""
    summary: str = ""
    problems: list = field(default_factory=list)
    pr_url: str = ""


def run_task(issue, repo_path, cfg: Config, open_pr: bool = False, run_id: str | None = None) -> TaskResult:
    """Run the agent on an already-cloned repo. Reused by the benchmark runner."""
    repo_path = Path(repo_path)
    run_id = run_id or f"{issue.repo}-{issue.number}-{int(time.time())}"

    cost = CostTracker(cfg)
    logger = TrajectoryLogger(cfg.trajectories_dir / f"{run_id}.json")
    state = AgentState(require_repro=cfg.reproduce_first)

    spec = build_image(repo_path, cfg)
    sandbox = DockerSandbox(spec.image_tag, repo_path, ResourceLimits.from_config(cfg))
    sandbox.start()
    try:
        ctx = ToolContext(repo_path=repo_path, sandbox=sandbox, state=state, config=cfg)
        outcome = run_agent(
            issue, ctx, LLMClient(cfg, cost), cost, logger,
            StrategyManager(cfg), build_repo_map(repo_path, 12000),
        )
    finally:
        sandbox.stop()

    validation = validate_patch(repo_path)
    patch_path = ""
    if validation.diff.strip():
        cfg.patches_dir.mkdir(parents=True, exist_ok=True)
        patch_path = str(cfg.patches_dir / f"{run_id}.diff")
        Path(patch_path).write_text(validation.diff)

    verified = state.verified()
    resolved = validation.ok and (verified or state.finish_status == "done")
    summary = state.finish_summary or f"Stopped: {outcome.reason}"

    pr_url = ""
    if open_pr and validation.ok:
        try:
            pr_url = create_pr(issue, repo_path, summary, cfg.github_token)
        except Exception as e:  # PR failure shouldn't lose the result
            validation.problems.append(f"PR creation failed: {e}")

    logger.meta.update({
        "run_id": run_id, "reason": outcome.reason, "verified": verified,
        "reproduced": state.reproduced, "finish_status": state.finish_status,
        "steps": state.step, "attempts": state.attempts,
        "test_runs": state.test_runs, "problems": validation.problems,
        "cost": cost.summary(),
    })
    logger.save()

    return TaskResult(
        run_id=run_id, status="resolved" if resolved else "unresolved",
        reason=outcome.reason, verified=verified, steps=state.step,
        cost=round(cost.total_cost, 4), patch=validation.diff, patch_path=patch_path,
        summary=summary, problems=validation.problems, pr_url=pr_url,
    )


def solve(args) -> int:
    cfg = Config()
    cfg.max_steps = args.max_steps
    cfg.max_cost_usd = args.max_cost
    cfg.timeout_seconds = args.timeout
    cfg.reproduce_first = not args.no_reproduce

    if not cfg.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set (see .env.example)")
        return 1

    print(f"Fetching issue: {args.issue_url}")
    issue = fetch_issue(args.issue_url, cfg.github_token)

    print(f"Cloning {issue.owner}/{issue.repo} ...")
    dest = cfg.repos_dir / f"{issue.owner}__{issue.repo}__{issue.number}"
    repo_path, sha = clone_repo(issue.owner, issue.repo, dest, cfg.github_token, args.commit)
    print(f"Checked out {sha[:10]}")

    result = run_task(issue, repo_path, cfg, open_pr=args.open_pr)

    print("\n" + "=" * 60)
    print(f"Status:   {result.status} ({result.reason})")
    print(f"Verified: {result.verified}   Steps: {result.steps}   Cost: ${result.cost}")
    print(f"Summary:  {result.summary}")
    if result.problems:
        print("Problems: " + "; ".join(result.problems))
    if result.patch_path:
        print(f"Patch:    {result.patch_path}")
    if result.pr_url:
        print(f"PR:       {result.pr_url}")
    return 0 if result.status == "resolved" else 2


def cli():
    parser = argparse.ArgumentParser(prog="agent")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="Resolve a GitHub issue")
    s.add_argument("issue_url")
    s.add_argument("--commit", default=None, help="Checkout this commit instead of default branch HEAD")
    s.add_argument("--max-steps", type=int, default=40)
    s.add_argument("--max-cost", type=float, default=2.0)
    s.add_argument("--timeout", type=int, default=1800)
    s.add_argument("--open-pr", action="store_true")
    s.add_argument("--no-reproduce", action="store_true")

    args = parser.parse_args()
    sys.exit(solve(args))


if __name__ == "__main__":
    cli()