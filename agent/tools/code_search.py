from agent.tools.file_viewer import rel_path


def search_code(ctx, pattern, path=".", glob=None, max_lines=60):
    try:
        target = rel_path(ctx.repo_path, path)
    except ValueError as e:
        return f"ERROR: {e}"

    cmd = ["rg", "-n", "--no-heading", "-S", "--max-columns", "200",
           "--max-count", "10", "--glob", "!.git"]
    if glob:
        cmd += ["--glob", glob]
    cmd += ["-e", pattern, "--", target]

    code, out = ctx.sandbox.exec(cmd, timeout=60)
    if code == 1:
        return "No matches."
    if code > 1:
        return f"ERROR: {out[:500]}"

    lines = out.splitlines()
    shown = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        shown += f"\n... {len(lines) - max_lines} more matches (narrow with path/glob)"
    return shown