import argparse
import json
from collections import Counter
from pathlib import Path


def load_results(path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def summarize(rows: list[dict], resolved_ids: set[str] | None = None) -> dict:
    n = len(rows) or 1
    summary = {
        "instances": len(rows),
        "self_verified_rate": round(sum(r["verified"] for r in rows) / n, 3),
        "avg_cost_usd": round(sum(r["cost"] for r in rows) / n, 4),
        "avg_steps": round(sum(r["steps"] for r in rows) / n, 1),
        "stop_reasons": dict(Counter(r["reason"] for r in rows)),
    }
    if resolved_ids is not None:   # from the official harness report
        resolved = sum(r["instance_id"] in resolved_ids for r in rows)
        summary["resolve_rate"] = round(resolved / n, 3)
        summary["resolved"] = resolved
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_dir")
    p.add_argument("--report", help="Harness report JSON containing 'resolved_ids'")
    args = p.parse_args()

    rows = load_results(Path(args.run_dir) / "results.jsonl")
    resolved = None
    if args.report:
        resolved = set(json.loads(Path(args.report).read_text()).get("resolved_ids", []))
    print(json.dumps(summarize(rows, resolved), indent=2))


if __name__ == "__main__":
    main()