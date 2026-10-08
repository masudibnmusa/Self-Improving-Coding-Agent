from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.tools.code_search import search_code
from agent.tools.file_editor import create_file, revert_changes, str_replace_edit
from agent.tools.file_viewer import view_file
from agent.tools.repo_map import repo_map
from agent.tools.shell_tool import run_shell
from agent.tools.symbol_search import find_symbol
from agent.tools.test_runner import run_tests


@dataclass
class ToolContext:
    repo_path: Path
    sandbox: Any
    state: Any
    config: Any


def _tool(name, description, properties=None, required=None):
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


TOOL_SCHEMAS = [
    _tool("view_file",
          "Read a file with line numbers. Use start_line/end_line to read a range (max 250 lines per call).",
          {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}},
          ["path"]),
    _tool("search_code",
          "Regex search across the repo (ripgrep). Returns file:line:match.",
          {"pattern": {"type": "string"},
           "path": {"type": "string", "description": "Subdirectory or file, default '.'"},
           "glob": {"type": "string", "description": "e.g. '*.py'"}},
          ["pattern"]),
    _tool("find_symbol",
          "Find where a function/class is defined and where it is referenced.",
          {"name": {"type": "string"}}, ["name"]),
    _tool("repo_map",
          "Compact tree with class/function signatures. Optionally scope to a subdirectory.",
          {"path": {"type": "string"}}),
    _tool("str_replace",
          "Replace exactly one occurrence of old_str with new_str in a file. old_str must match exactly "
          "(including whitespace) and be unique. Existing test files cannot be edited.",
          {"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}},
          ["path", "old_str", "new_str"]),
    _tool("create_file",
          "Create a new file. Reproduction scripts must be named repro_<name>.py (excluded from the final patch).",
          {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _tool("run_tests",
          "Run pytest in the sandbox. scope='targeted' needs paths (e.g. 'repro_bug.py' or "
          "'tests/test_x.py::test_y'). scope='full' runs the whole suite.",
          {"scope": {"type": "string", "enum": ["targeted", "full"]},
           "paths": {"type": "array", "items": {"type": "string"}}},
          ["scope"]),
    _tool("run_shell",
          "Run a restricted read-only-ish command (ls, cat, head, tail, wc, find, python, pytest, git status/diff/log/show).",
          {"command": {"type": "string"}}, ["command"]),
    _tool("revert_changes",
          "Discard ALL source changes (reproduction files are kept) to try a different approach."),
    _tool("finish",
          "End the run. status='done' if you fixed the issue, 'give_up' if you could not. "
          "summary: what changed, why, and what evidence you have.",
          {"status": {"type": "string", "enum": ["done", "give_up"]}, "summary": {"type": "string"}},
          ["status", "summary"]),
]


def _finish(ctx, status, summary):
    ctx.state.finished = True
    ctx.state.finish_status = status
    ctx.state.finish_summary = summary
    return "Recorded. Ending the run."


HANDLERS = {
    "view_file": view_file,
    "search_code": search_code,
    "find_symbol": find_symbol,
    "repo_map": repo_map,
    "str_replace": str_replace_edit,
    "create_file": create_file,
    "run_tests": run_tests,
    "run_shell": run_shell,
    "revert_changes": revert_changes,
    "finish": _finish,
}


def execute_tool(name: str, args: dict, ctx: ToolContext) -> str:
    handler = HANDLERS.get(name)
    if handler is None:
        return f"ERROR: unknown tool '{name}'"
    try:
        return str(handler(ctx, **(args or {})))
    except TypeError as e:
        return f"ERROR: bad arguments for {name}: {e}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"