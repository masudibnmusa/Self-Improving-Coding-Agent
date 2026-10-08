import argparse
import json
import time

from agent.config import Config
from agent.github.repo_cloner import clone_repo
from agent.main import run_task
from evaluation.swebench_adapter import load_instances


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="swebench-lite")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--ids", nargs="*", default=None)
    p.add_argument("--run-name", default=time.strftime("run-%Y%m%d-%H%M%S"))
    p.add_argument("--max-steps", type=int, default=40)
    p.add_argument("--max-cost", type=float, default=2.0)
    p.add_argument("--no-reproduce", action="store_true")
    args = p.parse_args()

    cfg = Config()
    cfg.max_steps, cfg.max_cost_usd = args.max_steps, args.max_cost
    cfg.reproduce_first = not args.no_reproduce

    out_dir = cfg.results_dir / args.run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path, preds_path = out_dir / "results.jsonl", out_dir / "predictions.jsonl"

    done = set()
    if results_path.exists():   # resume support
        done = {json.loads(l)["instance_id"] for l in results_path.read_text().splitlines() if l}

    for inst in load_instances(args.dataset, args.limit, args.ids):
        if inst.instance_id in done:
            continue
        print(f"\n=== {inst.instance_id} ===")
        patch = ""
        try:
            owner, name = inst.repo.split("/")
            repo_path, _ = clone_repo(owner, name, cfg.repos_dir / inst.instance_id,
                                      cfg.github_token, inst.base_commit)
            r = run_task(inst.to_issue(), repo_path, cfg, run_id=f"{args.run_name}-{inst.instance_id}")
            patch = r.patch
            row = {"instance_id": inst.instance_id, "status": r.status, "reason": r.reason,
                   "verified": r.verified, "steps": r.steps, "cost": r.cost,
                   "patch_chars": len(r.patch), "problems": r.problems}
        except Exception as e:
            row = {"instance_id": inst.instance_id, "status": "error", "reason": str(e)[:500],
                   "verified": False, "steps": 0, "cost": 0.0, "patch_chars": 0, "problems": []}

        with results_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        with preds_path.open("a") as f:
            f.write(json.dumps({"instance_id": inst.instance_id,
                                "model_name_or_path": cfg.model, "model_patch": patch}) + "\n")
        print(row["status"], row["reason"])

    print(f"\nPredictions: {preds_path}")
    print("Score with the official harness, e.g.:\n"
          f"  python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Lite "
          f"--predictions_path {preds_path} --max_workers 4 --run_id {args.run_name}")


if __name__ == "__main__":
    main()