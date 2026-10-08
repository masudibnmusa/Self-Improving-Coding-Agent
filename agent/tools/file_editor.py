import difflib
import re
import subprocess

from agent.analysis.patch_validator import EXCLUDE_REPRO, is_repro_path, is_test_path
from agent.tools.file_viewer import safe_path


def _guard(path: str):
    rel = str(path).replace("\\", "/")
    if is_test_path(rel) and not is_repro_path(rel):
        return ("ERROR: editing or creating test files is not allowed. To reproduce a bug, create a "
                "file named repro_<name>.py (it can contain pytest-style test functions).")
    return None


def _syntax_error(path: str, text: str):
    if not str(path).endswith(".py"):
        return None
    try:
        compile(text, str(path), "exec")
    except SyntaxError as e:
        return f"{e.msg} (line {e.lineno})"
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _not_found_hint(text: str, old: str) -> str:
    if _norm(old) in _norm(text):
        return "The text exists but differs in whitespace/indentation. View the file and copy it exactly."
    first = next((l.strip() for l in old.splitlines() if l.strip()), "")
    lines = text.splitlines()
    match = difflib.get_close_matches(first, [l.strip() for l in lines], n=1, cutoff=0.6)
    if match:
        idx = [l.strip() for l in lines].index(match[0])
        return f"Closest line is {idx + 1}: `{lines[idx].strip()}`. View that region and retry."
    return "No similar line found. Use search_code/view_file to locate the right code."


def _snippet(text: str, start_line: int, n_lines: int, context: int = 3) -> str:
    lines = text.splitlines()
    lo, hi = max(1, start_line - context), min(len(lines), start_line + n_lines + context)
    return "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(lo, hi + 1))


def str_replace_edit(ctx, path, old_str, new_str):
    if (msg := _guard(path)):
        return msg
    try:
        p = safe_path(ctx.repo_path, path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.is_file():
        return f"ERROR: {path} does not exist"
    if not old_str:
        return "ERROR: old_str must not be empty"

    text = p.read_text(encoding="utf-8")
    count = text.count(old_str)
    if count == 0:
        return "ERROR: old_str not found in file. " + _not_found_hint(text, old_str)
    if count > 1:
        lines = [text.count("\n", 0, m.start()) + 1 for m in re.finditer(re.escape(old_str), text)]
        return (f"ERROR: old_str appears {count} times (lines {lines}). "
                "Include more surrounding lines so it is unique.")

    idx = text.find(old_str)
    new_text = text[:idx] + new_str + text[idx + len(old_str):]
    if (err := _syntax_error(path, new_text)):
        return f"ERROR: edit rejected, it would cause a syntax error: {err}. File unchanged."

    p.write_text(new_text, encoding="utf-8")
    ctx.state.record_edit(str(path), "str_replace", is_source=not is_repro_path(str(path)))
    start_line = text.count("\n", 0, idx) + 1
    return "OK. Edited region:\n" + _snippet(new_text, start_line, new_str.count("\n") + 1)


def create_file(ctx, path, content):
    if (msg := _guard(path)):
        return msg
    try:
        p = safe_path(ctx.repo_path, path)
    except ValueError as e:
        return f"ERROR: {e}"
    if p.exists():
        return f"ERROR: {path} already exists. Use str_replace to modify it."
    if (err := _syntax_error(path, content)):
        return f"ERROR: file rejected, syntax error: {err}"

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    ctx.state.record_edit(str(path), "create", is_source=not is_repro_path(str(path)))
    return f"OK. Created {path} ({content.count(chr(10)) + 1} lines)."


def revert_changes(ctx):
    def git(*args):
        return subprocess.run(["git", "-C", str(ctx.repo_path), *args], capture_output=True, text=True)

    git("checkout", "--", ".")
    git("clean", "-fd", "--", ".", EXCLUDE_REPRO)
    ctx.state.reset_for_new_attempt()
    return (f"Reverted all source changes (repro_* files kept). "
            f"Starting attempt #{ctx.state.attempts}. Form a different hypothesis.")