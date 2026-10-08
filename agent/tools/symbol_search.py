import re


def find_symbol(ctx, name):
    """Regex-based definition/reference finder. Swap in tree-sitter or ctags later for precision."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        return "ERROR: name must be a plain identifier"

    defs_pattern = rf"^\s*(async\s+def|def|class|function|func|fn|struct|interface|enum|type)\s+{name}\b"
    base = ["rg", "-n", "--no-heading", "--case-sensitive", "--max-columns", "200", "--glob", "!.git"]

    _, defs = ctx.sandbox.exec(base + ["-e", defs_pattern, "--", "."], timeout=60)
    _, refs = ctx.sandbox.exec(base + ["-w", "-e", name, "--", "."], timeout=60)

    def_lines = defs.splitlines()[:20]
    ref_lines = [l for l in refs.splitlines() if l not in def_lines][:40]

    out = ["Definitions:"] + (def_lines or ["  (none found)"])
    out += ["", "References:"] + (ref_lines or ["  (none found)"])
    return "\n".join(out)