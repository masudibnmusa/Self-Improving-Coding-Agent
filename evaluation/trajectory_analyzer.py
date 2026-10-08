import argparse
import json
from collections import Counter
from pathlib import Path


def classify(traj: dict) -> str:
    meta, events = traj.get("meta", {}), traj.get("events", [])
    reason = meta.get("reason", "")

    if meta.get("verified"):
        return "resolved_verified"
    if reason == "stuck":
        return "stuck_loop"
    if reason in ("max_steps", "max_cost", "timeout"):
        return "out_of_budget"
    if meta.get("finish_status") == "give_up":
        return "gave_up"

    tools = [e for e in events if e["kind"] == "tool"]
    edits = [e for e in tools if e["name"] in ("str_replace", "create_file")]
    if edits and sum(e["output"].startswith("ERROR") for e in edits) / len(edits) >= 0.3:
        return "edit_failures"

    runs = meta.get("test_runs", [])
    if runs and runs[-1]["scope"] == "full" and not runs[-1]["ok"] and any(
        r["scope"] == "targeted" and r["ok"] for r in runs
    ):
        return "regression"
    if not meta.get("reproduced"):
        return "never_reproduced"
    return "other"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("trajectories_dir", nargs="?", default="data/trajectories")
    p.add_argument("--prefix", default="", help="Only analyze files starting with this run name")
    args = p.parse_args()

    counts = Counter()
    for path in sorted(Path(args.trajectories_dir).glob(f"{args.prefix}*.json")):
        counts[classify(json.loads(path.read_text()))] += 1
    print(json.dumps(dict(counts.most_common()), indent=2))


if __name__ == "__main__":
    main()