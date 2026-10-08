from dataclasses import dataclass

from agent.github.issue_fetcher import Issue

DATASETS = {
    "swebench-lite": "princeton-nlp/SWE-bench_Lite",
    "swebench-verified": "princeton-nlp/SWE-bench_Verified",
}


@dataclass
class Instance:
    instance_id: str
    repo: str            # "owner/name"
    base_commit: str
    problem_statement: str

    def to_issue(self) -> Issue:
        owner, name = self.repo.split("/")
        # The agent only sees the problem statement. Hidden tests are never shown to it.
        return Issue(owner, name, 0, self.instance_id, self.problem_statement, [])


def load_instances(dataset: str = "swebench-lite", limit: int | None = None, ids: list[str] | None = None):
    from datasets import load_dataset   # imported lazily so the agent runs without it

    ds = load_dataset(DATASETS[dataset], split="test")
    out = []
    for row in ds:
        if ids and row["instance_id"] not in ids:
            continue
        out.append(Instance(row["instance_id"], row["repo"], row["base_commit"], row["problem_statement"]))
        if limit and len(out) >= limit:
            break
    return out

# NOTE: for accurate scores, evaluate predictions with the official SWE-bench harness (see benchmark_runner).
# Old SWE-bench repos often need specific Python/dependency versions; the generic env_builder may fail on
# some of them. For serious runs, use SWE-bench's prebuilt per-instance images instead.