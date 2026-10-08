# Coding Agent: Autonomous GitHub Issue Resolver

An agent that takes a GitHub issue, writes a fix, runs the tests in a sandbox, and iterates until they pass. It is a miniature version of what SWE-bench measures and what tools like Claude Code and SWE-agent do.

> **Input:** a GitHub issue URL
> **Output:** a git diff (patch), a summary of what changed and why, and optionally a pull request

---

## How It Works

The agent explores the repository with tools (search, read file, edit, run tests), forms a hypothesis, makes a minimal edit, runs the tests, and uses the failure output as feedback for the next attempt. The loop ends when tests pass, the budget runs out, or the agent is stuck.

1. **Issue intake**: fetch the issue title, body, and comments via the GitHub API, and clone the repo at the right commit.
2. **Environment setup**: build a Docker container with the repo's dependencies installed so tests run reliably.
3. **Reproduction**: write or find a failing test that reproduces the bug *before* touching any code. This gives a clear success signal.
4. **Repo navigation**: use grep, file tree, symbol search, and "read file range" to find relevant code without loading the whole repo into context.
5. **Fix generation**: propose a minimal edit, applied via search/replace or unified diff.
6. **Test execution**: run targeted tests first (fast), then the wider suite to check for regressions.
7. **Failure analysis**: parse test output (stack traces, assertion diffs) and feed the relevant parts back to the agent.
8. **Iteration**: revise the approach, with the option to revert and try a different hypothesis if going in circles.
9. **Stopping logic**: stop on success, max steps/tokens/time, repeated identical failures, or a "give up and explain" decision.
10. **Output**: produce a patch, a summary, and optionally open a PR.

---

## Architecture

```
GitHub issue URL
      ↓
issue_fetcher.py + repo_cloner.py
      ↓
env_builder.py → docker_manager.py (sandbox ready)
      ↓
┌──────────────── agent_loop.py (repeats) ────────────────┐
│  LLM sees issue + repo_map + state                      │
│       ↓                                                 │
│  chooses tool: search / view / edit / run tests         │
│       ↓                                                 │
│  tool executes inside sandbox                           │
│       ↓                                                 │
│  test_output_parser.py → condensed failure info         │
│       ↓                                                 │
│  state.py updated → stopping_criteria.py                │
│       ↓                                                 │
│  tests pass? stuck? out of budget? → exit, else loop    │
└─────────────────────────────────────────────────────────┘
      ↓
patch_validator.py → final diff
      ↓
pr_creator.py (optional) + trajectory_logger.py
```

---

## Project Structure

```
coding-agent/
│
├── agent/
│   ├── main.py                    # CLI entry point: `agent solve <issue-url>`
│   ├── config.py                  # Model, budgets, sandbox settings
│   │
│   ├── core/
│   │   ├── agent_loop.py          # Main loop: observe -> think -> act -> repeat
│   │   ├── state.py               # Tracks edits made, tests run, attempts so far
│   │   ├── stopping_criteria.py   # Success, budget limits, stuck detection
│   │   └── strategy_manager.py    # Reproduce-first, retry, backtrack logic
│   │
│   ├── tools/
│   │   ├── registry.py            # Tool definitions exposed to the LLM
│   │   ├── file_viewer.py         # Read file with line ranges
│   │   ├── code_search.py         # grep / ripgrep wrapper
│   │   ├── symbol_search.py       # Find definitions/references (tree-sitter/ctags)
│   │   ├── repo_map.py            # Compact tree + signatures overview of repo
│   │   ├── file_editor.py         # Apply str_replace / patch edits safely
│   │   ├── test_runner.py         # Run tests in sandbox, return parsed results
│   │   └── shell_tool.py          # Restricted shell commands
│   │
│   ├── sandbox/
│   │   ├── docker_manager.py      # Build/start/stop containers per task
│   │   ├── env_builder.py         # Detect language/deps, build image
│   │   └── resource_limits.py     # CPU/memory/time caps, network restrictions
│   │
│   ├── github/
│   │   ├── issue_fetcher.py       # Pull issue + comments
│   │   ├── repo_cloner.py         # Clone + checkout correct commit
│   │   └── pr_creator.py          # Open PR with patch + explanation
│   │
│   ├── analysis/
│   │   ├── test_output_parser.py  # Extract failures, tracebacks, assertion diffs
│   │   ├── context_builder.py     # Select relevant code/errors to fit context
│   │   └── patch_validator.py     # Check diff is minimal, valid, and doesn't touch tests
│   │
│   ├── llm/
│   │   ├── llm_client.py          # Claude API with native tool use
│   │   └── prompts.py             # System prompt, reproduce/fix/reflect prompts
│   │
│   └── utils/
│       ├── trajectory_logger.py   # Full record of every thought/action/observation
│       └── cost_tracker.py        # Token and dollar usage per run
│
├── evaluation/
│   ├── benchmark_runner.py        # Run agent over a set of issues
│   ├── swebench_adapter.py        # Load SWE-bench Lite/Verified instances
│   ├── metrics.py                 # Resolve rate, cost per issue, steps per issue
│   └── trajectory_analyzer.py     # Categorize failure modes across runs
│
├── data/
│   ├── repos/                     # Cloned repos
│   ├── trajectories/              # Saved agent runs (JSON)
│   ├── patches/                   # Generated diffs
│   └── benchmark_results/
│
├── docker/
│   ├── Dockerfile.base            # Base image with common tooling
│   └── docker-compose.yml
│
├── tests/
│   ├── test_file_editor.py
│   ├── test_test_output_parser.py
│   ├── test_stopping_criteria.py
│   └── test_agent_loop.py
│
├── .env.example
├── requirements.txt
├── README.md
└── run.sh
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker (running locally)
- An Anthropic API key
- A GitHub personal access token (needed for fetching private issues and opening PRs)

### Installation

```bash
git clone https://github.com/masudibnmusa/Self-Improving-Coding-Agent.git
cd coding-agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and add your keys
```

### Environment variables

```bash
ANTHROPIC_API_KEY=your-key-here
GITHUB_TOKEN=your-token-here
```

> **Important:** these keys live on the host only. They are never passed into the sandbox container.

### Build the base sandbox image

```bash
docker build -f docker/Dockerfile.base -t coding-agent-base .
```

---

## Usage

### Solve a single issue

```bash
python -m agent.main solve https://github.com/<owner>/<repo>/issues/<number>
```

### Common options

```bash
python -m agent.main solve <issue-url> \
  --max-steps 40 \
  --max-cost 2.00 \
  --timeout 1800 \
  --open-pr
```

| Flag | Description |
|------|-------------|
| `--max-steps` | Maximum number of agent loop iterations |
| `--max-cost` | Hard dollar cap for the run |
| `--timeout` | Wall-clock limit in seconds |
| `--open-pr` | Open a pull request with the final patch |
| `--no-reproduce` | Skip the reproduce-first step (useful for ablations) |

### Output

Each run produces:

- `data/patches/<run-id>.diff`: the final patch
- `data/trajectories/<run-id>.json`: every thought, action, and observation
- A printed summary: what changed, why, test results, and cost

---

## Configuration

Settings live in `agent/config.py`.

| Setting | Purpose |
|---------|---------|
| `MODEL` | Claude model used for the agent |
| `MAX_STEPS` | Step budget per issue |
| `MAX_TOKENS` / `MAX_COST_USD` | Token and dollar budgets |
| `STUCK_THRESHOLD` | Number of repeated identical failures before the agent is considered stuck |
| `TOOL_OUTPUT_LIMIT` | Max characters returned from any single tool call |
| `SANDBOX_CPU` / `SANDBOX_MEMORY` / `SANDBOX_TIMEOUT` | Container resource caps |
| `SANDBOX_NETWORK` | `none` (default) or an allowlist |

---

## Tools Exposed to the Agent

| Tool | What it does |
|------|--------------|
| `view_file` | Read a file, optionally by line range |
| `search_code` | grep/ripgrep across the repo |
| `find_symbol` | Locate definitions and references |
| `repo_map` | Compact tree plus signatures overview |
| `edit_file` | Apply `str_replace` or patch edits, with clear error messages on mismatch |
| `run_tests` | Run targeted or full tests in the sandbox and return parsed results |
| `run_shell` | Restricted shell commands inside the sandbox |

All tool output is truncated to a configurable limit to protect the context window.

---

## Safety and Sandboxing

LLM-driven shell access is powerful and risky, so the design is defensive by default:

- **Containerized execution**: every task runs in its own Docker container.
- **No network by default**: the sandbox has no outbound access unless explicitly allowlisted.
- **No secrets in the sandbox**: API keys and tokens never enter the container.
- **Resource limits**: CPU, memory, and wall-clock caps per container.
- **Restricted shell**: only an approved set of commands is available.
- **Anti-cheating checks**: `patch_validator.py` rejects patches that modify test files, so the agent can't "pass" by editing the tests. Held-out tests are never visible to the agent.
- **Patch validation**: diffs must be syntactically valid and minimal.

---

## Evaluation

The `evaluation/` module measures how well the agent performs on real issues.

```bash
# Run on a subset of SWE-bench Lite
python -m evaluation.benchmark_runner --dataset swebench-lite --limit 25

# Summarize results
python -m evaluation.metrics data/benchmark_results/<run-id>
```

### Metrics

- **Resolve rate**: percentage of issues where the patch passes the official tests
- **Cost per issue**: average dollars spent
- **Steps per issue**: average number of loop iterations
- **Failure modes**: categorized by `trajectory_analyzer.py` (bad localization, bad edit, regression, stuck loop, out of budget)

### Ablations

Planned comparisons to show which design choices matter:

- Reproduce-first vs. no reproduction step
- Different step and cost budgets
- With vs. without repo map / symbol search

### Results

| Configuration | Instances | Resolve rate | Avg. cost | Avg. steps |
|---------------|-----------|--------------|-----------|------------|
| _to be filled in_ | | | | |

---

## Testing

```bash
pytest tests/
```

Unit tests cover the file editor, test output parser, stopping criteria, and the agent loop (with a mocked LLM client).

---

## Known Limitations

- Automatic environment setup is hard to generalize. Custom issues currently target a narrow set of repos (e.g., Python projects using pytest); benchmark runs use SWE-bench's prebuilt images.
- Long test outputs and large files can strain the context window despite truncation.
- The agent can still fail on issues that need broad refactors or deep domain knowledge.
- Results depend heavily on the chosen model and budgets.

---

## Acknowledgments

Inspired by [SWE-bench](https://www.swebench.com/), [SWE-agent](https://github.com/SWE-agent/SWE-agent), and Claude Code.

---

## License

MIT 