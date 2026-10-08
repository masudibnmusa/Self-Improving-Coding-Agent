import ast
import os
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist",
             ".tox", ".mypy_cache", ".pytest_cache"}
OTHER_EXT = {".md", ".rst", ".toml", ".cfg", ".ini", ".js", ".ts", ".c", ".h", ".go", ".rs", ".java"}


def _py_outline(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError):
        return []
    out = []
    funcs = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in tree.body:
        if isinstance(node, funcs):
            out.append(f"  def {node.name}({ast.unparse(node.args)})"[:120])
        elif isinstance(node, ast.ClassDef):
            out.append(f"  class {node.name}")
            for sub in node.body:
                if isinstance(sub, funcs):
                    out.append(f"    def {sub.name}({ast.unparse(sub.args)})"[:120])
    return out


def build_repo_map(repo_path, max_chars: int = 12000, subdir: str = "") -> str:
    root = Path(repo_path).resolve()
    start = (root / subdir).resolve() if subdir else root
    if root != start and root not in start.parents:
        return "ERROR: path escapes the repository"

    blocks, total, skipped = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(start):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = p.relative_to(root)
            if p.suffix == ".py":
                block = "\n".join([str(rel)] + _py_outline(p))
            elif p.suffix in OTHER_EXT:
                block = str(rel)
            else:
                continue
            if total + len(block) > max_chars:
                skipped += 1
                continue
            blocks.append(block)
            total += len(block) + 1

    text = "\n".join(blocks)
    if skipped:
        text += f"\n... {skipped} more files omitted (call repo_map with a subdirectory path)"
    return text or "(empty)"


def repo_map(ctx, path=""):
    return build_repo_map(ctx.repo_path, ctx.config.tool_output_limit, path)