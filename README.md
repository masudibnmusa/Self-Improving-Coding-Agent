<img alt="Self-Improving Coding Agent: an autonomous GitHub issue resolver that reproduces the bug, fixes it in a Docker sandbox, and proves it with tests before opening a PR. Install with pip install -e . and run agent solve on an issue URL; an example run plans, reproduces the failure, edits the code, tests with no new failures, and ends resolved with a PR opened." src="assets/banners/readme/terminal-1280x320-light.svg" width="100%">

# Coding Agent: Autonomous GitHub Issue Resolver

An agent that takes a GitHub issue, writes a fix, runs the tests in a sandbox, and iterates until they pass. It is a miniature version of what SWE-bench measures and what tools like Claude Code and SWE-agent do.

> **Input:** a GitHub issue URL
> **Output:** a git diff (patch), a summary of what changed and why, and optionally a pull request

---

## How It Works

The agent explores the repository with tools (search, read, edit, run tests), forms a hypothesis, makes a minimal edit, runs the tests, and uses the failure output as feedback for the next attempt. The loop ends when the fix is verified, the budget runs out, the agent is stuck, or it calls `finish`.

1. **Issue intake**: fetch the issue title, body, and up to 20 comments via the GitHub API, and clone the repo (optionally at a specific commit).
2. **Environment setup**: build a Docker image containing a copy of the repo with its dependencies installed (`pip install -e .`, plus `requirements.txt` if present). Images are cached by repo path, commit, and Dockerfile.
3. **Reproduction**: write a `repro_<name>.py` test that fails because of the bug, *before* touching any code. Only a genuine test failure counts. An import error, syntax error, "file not found" or "no tests collected" does not.
4. **Repo navigation**: ripgrep search, a compact repo map with class/function signatures, symbol lookup, and line-range file viewing, so the whole repo never has to be loaded into context.
5. **Fix generation**: minimal edits through `str_replace`, which must match exactly once. Edits that would introduce a Python syntax error are rejected before they are written.
6. **Test execution**: targeted tests first (fast), then the full suite to check for regressions.
7. **Failure analysis**: pytest output is condensed to failing test ids, `E` lines, and source locations before it goes back to the model.
8. **Iteration**: the agent gets nudges when it repeats the same failure, has not reproduced the bug, or is low on steps. It can call `revert_changes` to start a fresh attempt.
9. **Stopping logic**: stop when the fix is verified, the agent calls `finish`, or on max steps, max cost, timeout, repeated identical failures, or two consecutive turns without tool calls.
10. **Output**: a validated patch, a summary, a full trajectory log, and optionally a PR.

### When is an issue "resolved"?

A run's status is decided by evidence, not by the agent's own claim:

| Status | Meaning |
|--------|---------|
| `resolved` | The patch passed validation **and** the fix is verified: after the last source edit, every test that reproduced the bug passes, and the latest full-suite run shows no failures beyond those already present on the unmodified code. |
| `unverified` | The patch passed validation and the agent called `finish(status="done")`, but the test evidence above is missing. |
| `unresolved` | Anything else: the agent gave up, ran out of budget, got stuck, or the patch was rejected. |

Pre-existing failures are recognised when the agent runs the full suite before its first edit (or after `revert_changes`). Those failing test ids become the baseline. `--open-pr` only opens a PR for `resolved` runs.

---

## Architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture/architecture-dark.svg">
  <img alt="Architecture: setup (issue intake, image build, container start), the agent loop (Claude picks a tool; read/edit tools run on the host repo, search/test/shell tools run in a disposable sandbox that receives host edits before each command; test output is parsed, state updated, nudges added, and stopping criteria decide whether to continue), and output (patch validation, resolved/unverified/unresolved status, optional PR, trajectory log)." src="docs/architecture/architecture-light.svg" width="100%">
</picture>

Colors mark where each part runs: **blue** on the host, **amber** inside the sandbox container, **violet** the LLM, **green** the outputs. The diagram is generated from design tokens (`docs/architecture/tokens.json`, three layers: primitive → semantic → component); to change it, edit the tokens or the layout and run `python docs/architecture/build_diagram.py`.

<details>
<summary>Text version</summary>

```
GitHub issue URL
      ↓
issue_fetcher.py + repo_cloner.py          (host)
      ↓
env_builder.py → image with a copy of the repo + deps installed
      ↓
docker_manager.py → container started, nothing mounted from the host
      ↓
┌──────────────── agent_loop.py (repeats) ─────────────────────┐
│  LLM sees issue + repo_map + tool results + nudges           │
│       ↓                                                      │
│  chooses tool                                                │
│       ├─ view / edit / repo_map → run on the host repo       │
│       └─ search / run_tests / run_shell → run in container   │
│            (host edits are synced into the container first;  │
│             test runs first discard in-container changes)    │
│       ↓                                                      │
│  test_output_parser.py → condensed failure info              │
│       ↓                                                      │
│  state.py updated → strategy_manager.py (nudges)             │
│                   → stopping_criteria.py                     │
│       ↓                                                      │
│  verified? finished? stuck? out of budget? → exit, else loop │
└──────────────────────────────────────────────────────────────┘
      ↓
patch_validator.py → final diff (repro_* files excluded)
      ↓
pr_creator.py (only if resolved) + trajectory_logger.py
```

</details>

The host repo is the single source of truth: the patch is always taken from it. The container works on its own copy, so anything that happens inside it (files written by tests, edits made through `run_shell`) never reaches the patch or the host filesystem.

---

## Project Structure

```
Self-Improving-Coding-Agent/
│
├── agent/
│   ├── main.py                    # CLI entry point (`agent solve <issue-url>`) and run_task()
│   ├── config.py                  # Model, budgets, pricing, sandbox settings, paths
│   │
│   ├── core/
│   │   ├── agent_loop.py          # Main loop: call LLM -> execute tools -> feed results back
│   │   ├── state.py               # Edits, test runs, reproduction, baseline failures, verification
│   │   ├── stopping_criteria.py   # Finished, verified, budgets, stuck detection
│   │   └── strategy_manager.py    # Stuck / no-repro / low-budget nudges
│   │
│   ├── tools/
│   │   ├── registry.py            # Tool schemas exposed to the LLM + dispatch
│   │   ├── file_viewer.py         # Line-range viewer; path safety (no escapes, no .git)
│   │   ├── code_search.py         # ripgrep wrapper
│   │   ├── symbol_search.py       # Regex-based definition/reference finder (ripgrep)
│   │   ├── repo_map.py            # Compact tree + Python signatures
│   │   ├── file_editor.py         # str_replace / create_file / revert_changes with guards
│   │   ├── test_runner.py         # Run pytest in the sandbox, record parsed results
│   │   └── shell_tool.py          # Allow-listed commands in the sandbox
│   │
│   ├── sandbox/
│   │   ├── docker_manager.py      # Container lifecycle + host→container file sync
│   │   ├── env_builder.py         # Detect Python project, render Dockerfile, build/cache image
│   │   └── resource_limits.py     # CPU/memory/pids caps, network mode, dropped capabilities
│   │
│   ├── github/
│   │   ├── issue_fetcher.py       # Pull issue + comments
│   │   ├── repo_cloner.py         # Clone + checkout commit (token stripped from .git/config)
│   │   └── pr_creator.py          # Branch, commit, push, open PR
│   │
│   ├── analysis/
│   │   ├── test_output_parser.py  # Counts, failing node ids, error lines, exit-code semantics
│   │   ├── context_builder.py     # Initial prompt, output truncation, history compaction
│   │   └── patch_validator.py     # Diff checks: tests, pytest config, syntax, size
│   │
│   ├── llm/
│   │   ├── llm_client.py          # Anthropic Messages API with native tool use
│   │   └── prompts.py             # System prompt, workflow instructions, nudges
│   │
│   └── utils/
│       ├── cost_tracker.py        # Token usage (incl. prompt-cache tokens) → USD
│       ├── git.py                 # Hardened host-side git (no hooks, no fsmonitor) + secret redaction
│       └── trajectory_logger.py   # Full record of every thought/action/observation
│
├── evaluation/
│   ├── benchmark_runner.py        # Run the agent over SWE-bench instances, write predictions
│   ├── swebench_adapter.py        # Load SWE-bench Lite/Verified instances
│   ├── metrics.py                 # Self-verified rate, cost, steps, stop reasons, resolve rate
│   └── trajectory_analyzer.py     # Categorize failure modes across runs
│
├── assets/banners/readme/
│   ├── build_banners.py           # README banners (3 styles × light/dark) from the same tokens
│   └── {minimalist,geometric,terminal}-1280x320-{light,dark}.svg
│
├── docs/architecture/
│   ├── tokens.json                # Design tokens: primitive → semantic (light/dark) → component
│   ├── build_diagram.py           # Generates the architecture SVGs from the tokens
│   └── architecture-{light,dark}.svg
│
├── docker/
│   ├── Dockerfile.base            # python:3.11-slim + git, ripgrep, build-essential, pytest
│   └── docker-compose.yml         # Builds the base image as `coding-agent-base`
│
├── tests/                         # 54 unit tests, see "Testing"
├── data/                          # Created at runtime (git-ignored)
│   ├── repos/                     # Cloned repos
│   ├── trajectories/              # Saved agent runs (JSON)
│   ├── patches/                   # Generated diffs
│   └── benchmark_results/
│
├── .env.example
├── .gitignore
├── LICENSE                        # MIT
├── pyproject.toml                 # Package metadata; installs the `agent` command
├── requirements.txt               # Same dependencies, for `pip install -r`
├── README.md
└── run.sh                         # Wrapper: runs agent.main from the project folder
```

---

## Getting Started

### Prerequisites

- Python 3.11+ (the patch validator uses `tomllib`)
- Docker (running locally)
- git on the host
- An Anthropic API key
- A GitHub personal access token (optional for public issues; needed for private repos, higher rate limits, and opening PRs)

### Installation

```bash
git clone https://github.com/masudibnmusa/Self-Improving-Coding-Agent.git
cd Self-Improving-Coding-Agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"          # installs the `agent` command; add ",bench" for SWE-bench runs

cp .env.example .env
# then edit .env and add your keys
```

Use an editable install (`-e`) from the checkout: the agent reads `docker/Dockerfile.base` and writes `data/` relative to the project folder. `pip install -r requirements.txt` still works if you prefer running through `python -m agent.main`.

### Environment variables

```bash
ANTHROPIC_API_KEY=your-key-here
GITHUB_TOKEN=your-token-here
```

> **Important:** these keys live on the host only. They are never passed into the sandbox container, and the token is removed from the cloned repo's `.git/config` and redacted from error messages.

### Base sandbox image

The base image (`coding-agent-base`, from `docker/Dockerfile.base`) is built automatically the first time any run needs it, whether that's `agent solve`, `run.sh`, or the benchmark runner. To build or rebuild it yourself:

```bash
docker build -f docker/Dockerfile.base -t coding-agent-base docker/
# or: docker compose -f docker/docker-compose.yml build
```

---

## Usage

### Solve a single issue

```bash
agent solve https://github.com/<owner>/<repo>/issues/<number>
# equivalent, without installing the package:
python -m agent.main solve https://github.com/<owner>/<repo>/issues/<number>
./run.sh solve https://github.com/<owner>/<repo>/issues/<number>
```

### Options

```bash
agent solve <issue-url> \
  --commit <sha> \
  --max-steps 40 \
  --max-cost 2.00 \
  --timeout 1800 \
  --open-pr
```

| Flag | Default | Description |
|------|---------|-------------|
| `--commit` | default branch HEAD | Check out this commit before solving |
| `--max-steps` | 40 | Maximum number of agent loop iterations |
| `--max-cost` | 2.00 | Dollar cap for the run (checked before each LLM call) |
| `--timeout` | 1800 | Wall-clock limit in seconds (checked between steps) |
| `--open-pr` | off | Open a pull request if the run is `resolved` (needs push access to the repo) |
| `--no-reproduce` | off | Skip the reproduce-first requirement (useful for ablations) |

### Output

Each run produces:

- `data/patches/<run-id>.diff`: the final patch (`repro_*` files excluded)
- `data/trajectories/<run-id>.json`: every thought, action, and observation, plus metadata (status, stop reason, test runs, repro targets, baseline failures, cost breakdown)
- A printed summary: status, stop reason, verified flag, steps, cost, validation problems, patch path, PR URL

The process exits with `0` if the run is `resolved`, `2` if it is not, and `1` if `ANTHROPIC_API_KEY` is missing.

Stop reasons: `verified`, `agent_finished`, `max_steps`, `max_cost`, `timeout`, `stuck`, `no_tool_calls`.

---

## Configuration

Defaults live in the `Config` dataclass in `agent/config.py`. The CLI flags above override the budget fields; everything else is edited in that file.

| Field | Default | Purpose |
|-------|---------|---------|
| `model` | `claude-sonnet-5-5` | Claude model used for the agent |
| `max_output_tokens` | 4096 | Max tokens per model response |
| `max_steps` / `max_cost_usd` / `timeout_seconds` | 40 / 2.00 / 1800 | Budgets per issue |
| `stuck_threshold` | 3 | Nudge after N identical consecutive test failures; stop after 2N |
| `tool_output_limit` | 8000 | Max characters returned from any single tool call |
| `keep_recent_turns` | 6 | Older tool outputs beyond this are compacted to a placeholder |
| `price_input_per_mtok` / `price_output_per_mtok` | 2.00 / 10.00 | USD per million tokens, Anthropic API rates for `claude-sonnet-5-5` |
| `price_cache_write_per_mtok` / `price_cache_read_per_mtok` | 2.50 / 0.10 | Prompt-cache writes (5-minute TTL) and reads for the same model. **Update all four prices if you change `model`**; Bedrock and Vertex AI price differently |
| `base_image` | `coding-agent-base` | Base image for per-repo images |
| `sandbox_cpus` / `sandbox_memory` / `sandbox_pids` | 2.0 / `4g` / 512 | Container resource caps |
| `sandbox_network` | `none` | Docker network mode for the container (network is only available at image build time) |
| `command_timeout` | 300 | Per-command timeout in seconds (full test runs get 3×) |
| `reproduce_first` | `True` | Require a reproduction before a fix can be verified |

---

## Tools Exposed to the Agent

| Tool | Runs on | What it does |
|------|---------|--------------|
| `view_file` | host | Read a file with line numbers (max 250 lines per call) |
| `search_code` | sandbox | ripgrep across the repo, optional path/glob |
| `find_symbol` | sandbox | Locate definitions and references of an identifier |
| `repo_map` | host | Compact tree plus Python signatures, optionally for a subdirectory |
| `str_replace` | host | Replace exactly one occurrence of `old_str`; keeps the file's line endings; rejects syntax errors, test files, and pytest-config changes |
| `create_file` | host | Create a new file (same guards); repro scripts must be named `repro_<name>.py` |
| `run_tests` | sandbox | `scope='targeted'` with paths, or `scope='full'`; returns condensed results |
| `run_shell` | sandbox | Allow-listed commands (`ls`, `cat`, `head`, `tail`, `wc`, `find`, `python`, `pytest`, read-only `git` subcommands) on a disposable copy; changes made here are not part of the patch |
| `revert_changes` | host | Discard all source changes (repro files kept) and start a new attempt |
| `finish` | — | End the run with `done` or `give_up` and a summary |

Paths may be given relative to the repo or as `/workspace/...`. Paths that escape the repo or point into `.git` (including through symlinks) are rejected. All tool output is truncated to `tool_output_limit`.

---

## Safety and Sandboxing

LLM-driven shell access is powerful and risky, and issue text is untrusted input that goes straight into the prompt. The design is defensive by default:

- **Isolated execution**: every task runs in its own Docker container on the container's own copy of the repo. Nothing from the host is mounted. The agent's edits are made on the host by the edit tools and pushed into the container before each command, and each test run first discards anything changed inside the container. Files written by tests never reach the host, and the host's `.git` is unreachable from the sandbox.
- **Hardened host-side git**: every git command run on the host disables hooks and fsmonitor, diffs never run external diff programs, and the edit tools refuse paths inside `.git`. A tampered repo config therefore cannot execute commands on the host.
- **No network at run time**: the container runs with `network_mode=none` by default.
- **No secrets in the sandbox**: API keys and tokens never enter the container.
- **Least privilege**: all Linux capabilities dropped, `no-new-privileges`, CPU/memory/pids caps, per-command timeouts.
- **Restricted shell**: only allow-listed commands, run without a shell (no pipes or redirects). Because `python` is allowed, the container (not the allow-list) is the real security boundary.
- **Anti-cheating checks**: test files (`tests/`, `test_*.py`, `*_test.py`, `conftest.py`) and pytest-only config (`pytest.ini`, `pytest.toml`) cannot be edited. In `setup.cfg`, `pyproject.toml` and `tox.ini`, the pytest section (`[tool:pytest]`, `[tool.pytest.ini_options]`, `[pytest]`) is locked while the rest of the file stays editable. The patch validator re-checks all of this on the final diff, however the change was made.
- **Evidence-based success**: see [When is an issue "resolved"?](#when-is-an-issue-resolved).
- **Patch validation**: the final diff must be non-empty, compile (Python files), and change at most 400 lines.

---

## Evaluation

The `evaluation/` module runs the agent on SWE-bench instances and summarizes the results.

```bash
# Run on a subset of SWE-bench Lite (resumable: finished instances are skipped)
python -m evaluation.benchmark_runner --dataset swebench-lite --limit 25 --run-name my-run

# Specific instances / Verified split / ablation
python -m evaluation.benchmark_runner --dataset swebench-verified --ids django__django-11099 sympy__sympy-20590
python -m evaluation.benchmark_runner --limit 25 --no-reproduce --run-name no-repro

# Score predictions with the official harness (the runner prints this command)
python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path data/benchmark_results/my-run/predictions.jsonl --max_workers 4 --run_id my-run

# Summarize (add --report <harness-report.json> with `resolved_ids` for the official resolve rate)
python -m evaluation.metrics data/benchmark_results/my-run

# Categorize failure modes from trajectories
python -m evaluation.trajectory_analyzer data/trajectories --prefix my-run
```

Each run directory contains `results.jsonl` (status, stop reason, verified, steps, cost, patch size, validation problems per instance) and `predictions.jsonl` (in SWE-bench's prediction format).

### Metrics

- **Resolve rate**: share of instances whose patch passes the official hidden tests (needs `--report`)
- **Self-verified rate**: share of instances the agent verified with its own tests
- **Cost per issue**: average dollars spent
- **Steps per issue**: average number of loop iterations
- **Stop reasons**: counts of `verified`, `agent_finished`, `max_steps`, …
- **Failure modes** (`trajectory_analyzer.py`): `resolved_verified`, `stuck_loop`, `out_of_budget`, `gave_up`, `edit_failures`, `regression`, `never_reproduced`, `other`

### Ablations

Planned comparisons to show which design choices matter:

- Reproduce-first vs. no reproduction step (`--no-reproduce`)
- Different step and cost budgets (`--max-steps`, `--max-cost`)
- With vs. without repo map / symbol search

### Results

No benchmark runs have been recorded yet.

| Configuration | Instances | Resolve rate | Self-verified | Avg. cost | Avg. steps |
|---------------|-----------|--------------|---------------|-----------|------------|
| _to be filled in_ | | | | | |

---

## Testing

```bash
pytest tests/
```

The unit tests need no Docker daemon, network, or API key: the LLM is faked, and sandbox behaviour is tested against a stand-in container that runs the same commands in a local directory.

Current status: **58 passed in ~1.0 s** (Python 3.12, git 2.56, Linux).

| File | Tests | Covers |
|------|------:|--------|
| `test_agent_loop.py` | 3 | Loop runs tools and finishes; stops after turns without tool calls; unknown tools return errors |
| `test_file_editor.py` | 7 | Unique replace, not-found and ambiguous matches, syntax-error rejection, test-file protection, repro files, path escapes |
| `test_stopping_criteria.py` | 7 | Finish, max steps, max cost, stuck detection, verification ordering |
| `test_test_output_parser.py` | 3 | Failure parsing, passing runs, stable failure signatures |
| `test_security.py` | 9 | `.git` edits and symlinks blocked; host git ignores tampered fsmonitor and hooks; nothing mounted into the container; token redaction; cost tracking for all four token kinds with default and custom prices |
| `test_fixes.py` | 29 | Status and PR gating; CRLF preservation; what counts as a reproduction (exit codes 1/2/4/5/124, fixture errors); repro re-check after the last edit; pre-existing failure baseline; failing-id parsing; `/workspace` paths in `repo_map`; host↔sandbox sync (edits, deletions, reverts, discarding in-container changes, keeping build output); pytest-config protection in the edit tools and validator; base image built automatically (also via `build_image`, which the benchmark runner uses); `agent` console script target |

The security and correctness tests were mutation-checked: disabling each fix (e.g. the git hardening, the fresh reset before test runs, CRLF handling, the repro re-check, the PR gate) makes the corresponding test fail.

---

## Known Limitations

- **Python + pytest only.** `env_builder` supports Python projects (`pyproject.toml`, `setup.py`, `setup.cfg`, or `requirements.txt`). Other languages raise an error.
- **Generic environment setup.** The image is built from `python:3.11-slim` with a best-effort `pip install`. Install failures are not fatal, so a broken environment shows up later as test errors. Older SWE-bench repos often need specific Python/dependency versions; for serious benchmark runs, use SWE-bench's prebuilt per-instance images (not yet integrated).
- **Compiled code is not rebuilt.** Extensions built when the image is created are available, but if the agent edits C/Cython sources they are not recompiled.
- **The Docker sandbox sync has only been tested with a stand-in container.** Run a real `solve` once before relying on it.
- **Budgets are checked between steps.** A single long full-suite run (up to 3 × `command_timeout`) or one LLM call can overshoot the timeout or cost cap.
- **No prompt caching yet**, so every step resends the full history at full price.
- **Test ids containing `" - "`** (e.g. some parametrized ids) are matched by a cut-off name, which can make verification fail when it should pass, but never the reverse.
- **PRs** are pushed to a fixed branch name (`agent/fix-issue-<n>`) on the upstream repo, so re-runs conflict and forks are not supported yet.
- Results depend heavily on the chosen model and budgets, and the agent can still fail on issues that need broad refactors or deep domain knowledge.

---

## Acknowledgments

Inspired by [SWE-bench](https://www.swebench.com/), [SWE-agent](https://github.com/SWE-agent/SWE-agent), and Claude Code.

---

## License

Released under the [MIT License](LICENSE).
