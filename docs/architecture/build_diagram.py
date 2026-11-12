"""Build the README architecture diagram (light + dark SVG) from tokens.json.

    python docs/architecture/build_diagram.py

Token layers (see tokens.json):
  primitive  raw values               --color-blue-500, --font-mono, --fontSize-md
  semantic   meaning, per theme       --host-border: var(--color-blue-500)
  component  diagram parts            --node-host-stroke: var(--host-border)
Shapes and text reference component tokens only, so a theme is just a different semantic layer.
"""
import json
import re
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = json.loads((HERE / "tokens.json").read_text())
CATEGORIES = ("neutral", "host", "sandbox", "llm", "output")
W, H = 1040, 830


# --- tokens -> CSS ---------------------------------------------------------------------------

def _flatten(tree, prefix=""):
    for key, val in tree.items():
        if key.startswith("$"):
            continue
        name = f"{prefix}-{key}" if prefix else key
        if isinstance(val, dict) and "$value" not in val:
            yield from _flatten(val, name)
        else:
            yield name, val["$value"] if isinstance(val, dict) else val


def _ref(value: str) -> str:
    """'{color.blue.500}' -> 'var(--color-blue-500)'; '{semantic.fg}' -> 'var(--fg)'."""
    def sub(m):
        path = m.group(1).split(".")
        if path[0] == "semantic":
            path = path[1:]
        return f"var(--{'-'.join(path)})"
    return re.sub(r"\{([^}]+)\}", sub, value)


def css_tokens(theme: str) -> str:
    primitive = "\n".join(f"  --{n}: {v};" for n, v in _flatten(TOKENS["primitive"]))
    semantic = "\n".join(f"  --{n}: {_ref(v)};" for n, v in TOKENS["semantic"][theme].items())
    component = [f"  --{n}: {_ref(v)};" for n, v in TOKENS["component"].items()]
    for cat in CATEGORIES:   # per-category node tokens
        component += [f"  --node-{cat}-fill: var(--{cat}-bg);",
                      f"  --node-{cat}-stroke: var(--{cat}-border);",
                      f"  --node-{cat}-kicker: var(--{cat}-accent);"]
    for status in ("success", "warning", "danger"):
        component += [f"  --status-{status}-fill: var(--{status}-bg);",
                      f"  --status-{status}-text: var(--{status});"]
    return (f"/* primitive */\nsvg {{\n{primitive}\n}}\n"
            f"/* semantic ({theme}) */\nsvg {{\n{semantic}\n}}\n"
            f"/* component */\nsvg {{\n" + "\n".join(component) + "\n}")


STYLES = """
.bg { fill: var(--diagram-bg); }
.title { font: var(--weight-strong) var(--size-title) var(--font-ui); fill: var(--title-color); }
.section { font: var(--weight-kicker) var(--size-label) var(--font-ui); fill: var(--section-color);
           letter-spacing: .08em; text-transform: uppercase; }
.section-code { font: var(--size-label) var(--font-code); fill: var(--section-color); }
.frame { fill: var(--frame-bg); stroke: var(--frame-stroke); stroke-width: var(--stroke-frame);
         stroke-dasharray: 6 5; }
.zone { stroke-width: var(--stroke-node); }
.node-title { font: var(--weight-strong) var(--size-node-title) var(--font-code); fill: var(--node-title-color); }
.node-title-ui { font: var(--weight-strong) var(--size-node-title) var(--font-ui); fill: var(--node-title-color); }
.node-sub { font: var(--size-node-sub) var(--font-ui); fill: var(--node-sub-color); }
.kicker { font: var(--weight-kicker) var(--size-kicker) var(--font-ui); letter-spacing: .1em; }
.chip { fill: var(--chip-bg); stroke-width: var(--stroke-frame); }
.chip-text { font: var(--size-chip) var(--font-code); fill: var(--node-title-color); }
.status-text { font: var(--weight-strong) var(--size-chip) var(--font-code); }
.edge { fill: none; stroke: var(--connector-stroke); stroke-width: var(--stroke-connector); }
.edge-dashed { stroke-dasharray: 5 4; }
.arrowhead { fill: var(--connector-stroke); }
.edge-label { font: var(--size-label) var(--font-ui); fill: var(--connector-label); }
.legend-text { font: var(--size-label) var(--font-ui); fill: var(--node-sub-color); }
""" + "\n".join(
    f".{c} {{ fill: var(--node-{c}-fill); stroke: var(--node-{c}-stroke); }}\n"
    f".{c}-kicker {{ fill: var(--node-{c}-kicker); }}\n"
    f".{c}-chip {{ stroke: var(--node-{c}-stroke); }}" for c in CATEGORIES
) + "\n" + "\n".join(
    f".status-{s} {{ fill: var(--status-{s}-fill); stroke: var(--status-{s}-text); }}\n"
    f".status-{s}-text {{ fill: var(--status-{s}-text); }}" for s in ("success", "warning", "danger")
)


# --- drawing primitives ----------------------------------------------------------------------

out: list[str] = []


def text(x, y, s, cls, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>')


def node(x, y, w, h, cat, kicker, title, subs=(), title_cls="node-title"):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" class="{cat} zone"/>')
    text(x + 14, y + 19, kicker, f"kicker {cat}-kicker")
    text(x + 14, y + 38, title, title_cls)
    for i, s in enumerate(subs):
        text(x + 14, y + 56 + i * 15, s, "node-sub")


def chip(x, y, label, cat):
    w = 16 + len(label) * 7.3
    out.append(f'<rect x="{x}" y="{y}" width="{w:.0f}" height="24" rx="12" class="chip {cat}-chip"/>')
    text(x + w / 2, y + 16, label, "chip-text", "middle")
    return x + w + 8


def status_chip(x, y, label, kind):
    w = 14 + len(label) * 7.8   # bold mono is wider than the regular chips
    out.append(f'<rect x="{x}" y="{y}" width="{w:.0f}" height="24" rx="12" class="chip status-{kind}"/>')
    text(x + w / 2, y + 16, label, f"status-text status-{kind}-text", "middle")
    return x + w + 6


def edge(points, label=None, label_at=None, dashed=False, anchor="middle"):
    d = "M" + " L".join(f"{x},{y}" for x, y in points)
    cls = "edge edge-dashed" if dashed else "edge"
    out.append(f'<path d="{d}" class="{cls}" marker-end="url(#arrow)"/>')
    if label:
        lx, ly = label_at
        text(lx, ly, label, "edge-label", anchor)


# --- layout ----------------------------------------------------------------------------------

def draw():
    out.clear()
    out.append(f'<rect width="{W}" height="{H}" class="bg"/>')

    # header + legend
    text(32, 38, "Run lifecycle", "title")
    lx = 520
    for cat, label in (("host", "Host"), ("sandbox", "Sandbox container"),
                       ("llm", "LLM"), ("output", "Output")):
        out.append(f'<rect x="{lx}" y="27" width="14" height="14" rx="4" class="{cat} zone"/>')
        text(lx + 20, 38, label, "legend-text")
        lx += 34 + len(label) * 6.6

    # 1 · setup
    text(32, 76, "1 · Setup", "section")
    y, h, w, gap = 88, 80, 223, 28
    xs = [32 + i * (w + gap) for i in range(4)]
    node(xs[0], y, w, h, "neutral", "INPUT", "GitHub issue URL", ["github.com/owner/repo/issues/N"],
         title_cls="node-title-ui")
    node(xs[1], y, w, h, "host", "HOST", "issue_fetcher.py", ["+ repo_cloner.py: issue, comments,", "clone at commit"])
    node(xs[2], y, w, h, "host", "HOST → IMAGE", "env_builder.py", ["image: repo copy + deps installed"])
    node(xs[3], y, w, h, "sandbox", "SANDBOX", "docker_manager.py", ["container up, nothing mounted"])
    for i in range(3):
        edge([(xs[i] + w, y + h / 2), (xs[i + 1] - 4, y + h / 2)])

    # 2 · agent loop
    fy, fh = 226, 446
    text(32, 210, "2 · Agent loop", "section")
    text(150, 210, "agent_loop.py — repeats every step", "section-code")
    out.append(f'<rect x="32" y="{fy}" width="976" height="{fh}" rx="16" class="frame"/>')
    edge([(xs[3] + w / 2, y + h), (xs[3] + w / 2, 192), (520, 192), (520, 246)],
         "start", (xs[3] + w / 2 - 8, 186), anchor="end")

    # LLM + dispatcher
    node(360, 250, 320, 66, "llm", "LLM", "Claude · llm_client.py",
         ["sees issue, repo map, tool results, nudges"])
    out.append('<rect x="410" y="340" width="220" height="34" rx="17" class="neutral zone"/>')
    text(520, 362, "registry.py · picks a tool", "chip-text", "middle")
    edge([(520, 316), (520, 336)])

    # host zone
    hx, hy, hw, hh = 96, 404, 380, 150
    out.append(f'<rect x="{hx}" y="{hy}" width="{hw}" height="{hh}" rx="12" class="host zone"/>')
    text(hx + 14, hy + 20, "HOST REPO · SOURCE OF TRUTH", "kicker host-kicker")
    cx = hx + 14
    for label in ("view_file", "repo_map", "str_replace"):
        cx = chip(cx, hy + 32, label, "host")
    cx = hx + 14
    for label in ("create_file", "revert_changes"):
        cx = chip(cx, hy + 64, label, "host")
    text(hx + 14, hy + 112, "Guards: no .git, no test files, no pytest", "node-sub")
    text(hx + 14, hy + 127, "config changes, syntax-checked, line endings kept", "node-sub")
    edge([(410, 357), (hx + hw / 2, 357), (hx + hw / 2, hy - 4)],
         "read · edit", (hx + hw / 2 + 8, 390), anchor="start")

    # sandbox zone
    sx, sy, sw, sh = 564, 404, 420, 150
    out.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="12" class="sandbox zone"/>')
    text(sx + 14, sy + 20, "SANDBOX CONTAINER · DISPOSABLE COPY", "kicker sandbox-kicker")
    cx = sx + 14
    for label in ("search_code", "find_symbol"):
        cx = chip(cx, sy + 32, label, "sandbox")
    cx = sx + 14
    for label in ("run_tests", "run_shell"):
        cx = chip(cx, sy + 64, label, "sandbox")
    text(sx + 14, sy + 112, "No network, all capabilities dropped. Test runs", "node-sub")
    text(sx + 14, sy + 127, "first discard in-container changes.", "node-sub")
    edge([(630, 357), (sx + sw / 2, 357), (sx + sw / 2, sy - 4)],
         "search · test · shell", (sx + sw / 2 + 8, 390), anchor="start")

    # host -> sandbox sync
    edge([(hx + hw, sy + 62), (sx - 4, sy + 62)], dashed=True)
    text((hx + hw + sx) / 2, sy + 52, "sync edits", "edge-label", "middle")
    text((hx + hw + sx) / 2, sy + 82, "before each", "edge-label", "middle")
    text((hx + hw + sx) / 2, sy + 96, "command", "edge-label", "middle")

    # feedback row (right to left)
    ry, rh, rw = 584, 64, 204
    rx = {name: 96 + i * (rw + 24) for i, name in
          enumerate(("stop", "strategy", "state", "parser"))}
    node(rx["parser"], ry, rw, rh, "neutral", "FEEDBACK", "test_output_parser", ["failing ids, E lines, locations"])
    node(rx["state"], ry, rw, rh, "neutral", "STATE", "state.py", ["edits, tests, repro, baseline"])
    node(rx["strategy"], ry, rw, rh, "neutral", "NUDGES", "strategy_manager", ["stuck, no repro, low budget"])
    node(rx["stop"], ry, rw, rh, "neutral", "STOP?", "stopping_criteria", ["verified, finished, stuck, budget"])
    edge([(sx + sw / 2 + 108, sy + sh), (sx + sw / 2 + 108, ry - 4)])
    for a, b in (("parser", "state"), ("state", "strategy"), ("strategy", "stop")):
        edge([(rx[a], ry + rh / 2), (rx[b] + rw + 4, ry + rh / 2)])

    # loop back to the LLM
    edge([(rx["stop"], ry + rh / 2), (64, ry + rh / 2), (64, 283), (356, 283)],
         "continue → next step", (74, 277), anchor="start")

    # 3 · output
    oy, oh = 724, 76
    text(32, 708, "3 · Output", "section")
    ox = {"validator": (96, 204), "status": (324, 292), "pr": (640, 148), "log": (800, 184)}
    vx, vw = ox["validator"]
    node(vx, oy, vw, oh, "output", "OUTPUT", "patch_validator.py",
         ["final diff, repro_* excluded", "tests/pytest config checked"])
    sxo, sw_o = ox["status"]
    out.append(f'<rect x="{sxo}" y="{oy}" width="{sw_o}" height="{oh}" rx="10" class="output zone"/>')
    text(sxo + 14, oy + 19, "STATUS", "kicker output-kicker")
    cx = sxo + 14
    for label, kind in (("resolved", "success"), ("unverified", "warning"), ("unresolved", "danger")):
        cx = status_chip(cx, oy + 30, label, kind)
    text(sxo + 14, oy + 68, "resolved = repro + full suite verified", "node-sub")
    node(ox["pr"][0], oy, ox["pr"][1], oh, "output", "OPTIONAL", "pr_creator.py",
         ["opens a PR only if", "status is resolved"])
    node(ox["log"][0], oy, ox["log"][1], oh, "output", "ALWAYS", "trajectory_logger",
         ["every step, test run and", "cost, saved as JSON"])

    stop_cx = rx["stop"] + rw / 2
    edge([(stop_cx, ry + rh), (stop_cx, oy - 4)], "stop → exit", (stop_cx + 8, 698), anchor="start")
    edge([(vx + vw, oy + oh / 2), (sxo - 4, oy + oh / 2)])
    edge([(sxo + sw_o, oy + oh / 2), (ox["pr"][0] - 4, oy + oh / 2)])
    log_cx = ox["log"][0] + ox["log"][1] / 2
    edge([(log_cx, fy + fh), (log_cx, oy - 4)], dashed=True)
    text(log_cx - 8, 698, "logs every event", "edge-label", "end")

    return "\n".join(out)


def build(theme: str) -> str:
    body = draw()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">Coding agent architecture ({theme})</title>
<desc id="d">Setup: GitHub issue URL, issue_fetcher and repo_cloner, env_builder builds an image with a copy of the repo, docker_manager starts a container with nothing mounted. Agent loop: Claude picks a tool through registry.py; view, edit and repo_map tools run on the host repo, which is the source of truth; search, test and shell tools run in a disposable sandbox container that receives host edits before each command. Test output is parsed, state is updated, strategy_manager adds nudges and stopping_criteria decides whether to continue or exit. Output: patch_validator produces the final diff, the run is resolved, unverified or unresolved, pr_creator opens a PR only when resolved, and trajectory_logger records every event.</desc>
<defs>
<style>
{css_tokens(theme)}
{STYLES}
</style>
<marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
<path d="M0,0 L10,5 L0,10 z" class="arrowhead"/>
</marker>
</defs>
{body}
</svg>
"""


if __name__ == "__main__":
    for theme in ("light", "dark"):
        path = HERE / f"architecture-{theme}.svg"
        path.write_text(build(theme))
        print(f"wrote {path.relative_to(HERE.parent.parent)}")
