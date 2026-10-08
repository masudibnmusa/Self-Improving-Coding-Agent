from pathlib import Path


def normalize(path: str) -> str:
    path = str(path).strip()
    if path.startswith("/workspace/"):
        path = path[len("/workspace/"):]
    return path or "."


def safe_path(repo_path, rel: str) -> Path:
    root = Path(repo_path).resolve()
    p = (root / normalize(rel)).resolve()
    if p != root and root not in p.parents:
        raise ValueError(f"path escapes the repository: {rel}")
    return p


def rel_path(repo_path, rel: str) -> str:
    p = safe_path(repo_path, rel)
    r = p.relative_to(Path(repo_path).resolve())
    return str(r) if str(r) != "." else "."


def view_file(ctx, path, start_line=1, end_line=None, max_lines=250):
    try:
        p = safe_path(ctx.repo_path, path)
    except ValueError as e:
        return f"ERROR: {e}"
    if not p.is_file():
        return f"ERROR: {path} is not a file (use repo_map or run_shell 'ls' to explore)"

    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    total = len(lines)
    start = max(1, int(start_line or 1))
    if start > total:
        return f"ERROR: start_line {start} is beyond end of file ({total} lines)"
    end = int(end_line) if end_line else start + max_lines - 1
    end = min(end, total, start + max_lines - 1)

    body = "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(start, end + 1))
    header = f"{path} (lines {start}-{end} of {total})"
    footer = f"\n[more lines below: call again with start_line={end + 1}]" if end < total else ""
    return f"{header}\n{body}{footer}"