"""README hero banners (1280x320, light + dark) built from docs/architecture/tokens.json.

    python assets/banners/readme/build_banners.py

Three art directions share one left-hand text block; the right-hand visual differs:
  minimalist  four-step flow, one row per role color (LLM, host, sandbox, output)
  geometric   dot grid + a four-color loop that exits into a verified patch
  terminal    an illustrative `agent solve` run in a terminal window
Colors and type come only from tokens (via the diagram's css_tokens), so the banners match the
architecture diagram and switch cleanly between GitHub's light and dark themes.
"""
import importlib.util
import math
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
_spec = importlib.util.spec_from_file_location("build_diagram", ROOT / "docs/architecture/build_diagram.py")
_diagram = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_diagram)
css_tokens = _diagram.css_tokens

W, H = 1280, 320
ROLES = ("llm", "host", "sandbox", "output")

STYLES = """
.bg { fill: var(--banner-bg); }
.kicker { font: var(--weight-kicker) var(--size-banner-kicker) var(--font-ui); letter-spacing: .14em; fill: var(--llm-accent); }
.headline { font: var(--weight-banner-headline) var(--size-banner-headline) var(--font-ui);
            fill: var(--banner-headline); letter-spacing: -.01em; }
.body { font: var(--size-banner-body) var(--font-ui); fill: var(--banner-body); }
.cta-box { fill: var(--banner-cta-bg); stroke: var(--banner-cta-stroke); stroke-width: var(--stroke-frame); }
.cta { font: var(--size-banner-cta) var(--font-code); fill: var(--banner-cta-text); }
.cta-prompt { font: var(--size-banner-cta) var(--font-code); fill: var(--output-accent); }
.rule { stroke: var(--banner-rule); stroke-width: var(--stroke-frame); }
.decor { fill: var(--banner-decor); }
.step-title { font: var(--weight-strong) var(--size-banner-step) var(--font-ui); fill: var(--banner-headline); }
.step-sub { font: var(--size-banner-step-sub) var(--font-code); fill: var(--banner-body); }
.loop-label { font: var(--weight-strong) var(--size-banner-step-sub) var(--font-code); }
.loop-center { font: var(--weight-strong) var(--size-banner-step) var(--font-ui); fill: var(--banner-headline); }
.loop-center-sub { font: var(--size-banner-step-sub) var(--font-ui); fill: var(--banner-body); }
.term { fill: var(--surface); stroke: var(--border); stroke-width: var(--stroke-frame); }
.term-bar { fill: var(--banner-bg); }
.term-text { font: var(--size-banner-term) var(--font-code); fill: var(--banner-headline); }
.term-dim { font: var(--size-banner-term) var(--font-code); fill: var(--banner-body); }
""" + "\n".join(
    f".{r}-fill {{ fill: var(--{r}-bg); stroke: var(--{r}-border); stroke-width: var(--stroke-node); }}\n"
    f".{r}-solid {{ fill: var(--{r}-border); }}\n"
    f".{r}-stroke {{ fill: none; stroke: var(--{r}-border); stroke-width: 6; stroke-linecap: round; }}\n"
    f".{r}-text {{ fill: var(--{r}-accent); }}" for r in ROLES
)


class Canvas:
    def __init__(self):
        self.out = [f'<rect width="{W}" height="{H}" class="bg"/>']

    def add(self, s):
        self.out.append(s)

    def text(self, x, y, s, cls, anchor="start"):
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{escape(s)}</text>')


def text_block(c: Canvas, cta="agent solve <issue-url>"):
    """Shared left side: kicker, headline, tagline, one CTA (inside the 80% safe zone)."""
    x = 72
    c.text(x, 78, "AUTONOMOUS GITHUB ISSUE RESOLVER", "kicker")
    c.text(x, 134, "Self-Improving Coding Agent", "headline")
    c.text(x, 174, "Reproduce the bug, fix it in a Docker sandbox,", "body")
    c.text(x, 202, "and prove it with tests before opening a PR.", "body")
    if cta:
        label = cta
        w = 52 + len(label) * 9.6
        c.add(f'<rect x="{x}" y="226" width="{w:.0f}" height="46" rx="10" class="cta-box"/>')
        c.text(x + 18, 255, "$", "cta-prompt")
        c.text(x + 38, 255, label, "cta")


def minimalist(c: Canvas):
    text_block(c)
    steps = [("llm", "Claude reads the issue", "plans with repo map + tools"),
             ("host", "Edits the host repo", "str_replace · guarded"),
             ("sandbox", "Tests in a sandbox", "repro first, then full suite"),
             ("output", "Ships a verified patch", "resolved → PR")]
    x, y0, w, h, gap = 828, 36, 380, 56, 10
    c.add(f'<line x1="{x + 25}" y1="{y0 + h / 2}" x2="{x + 25}" y2="{y0 + 3 * (h + gap) + h / 2}" class="rule"/>')
    for i, (role, title, sub) in enumerate(steps):
        y = y0 + i * (h + gap)
        c.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" class="{role}-fill"/>')
        c.add(f'<circle cx="{x + 25}" cy="{y + h / 2}" r="9" class="{role}-solid"/>')
        c.text(x + 48, y + 25, title, "step-title")
        c.text(x + 48, y + 45, sub, "step-sub")


def geometric(c: Canvas):
    # dot grid on the right half, fading out toward the text
    for gx in range(772, W - 20, 24):
        for gy in range(20, H - 10, 24):
            r = 1.6 if gx > 860 else 1.1
            c.add(f'<circle cx="{gx}" cy="{gy}" r="{r}" class="decor"/>')
    text_block(c)
    cx, cy, R = 1000, 160, 96
    labels = {"llm": ("plan", 0, -1), "host": ("edit", 1, 0), "sandbox": ("test", 0, 1), "output": ("verify", -1, 0)}
    for i, role in enumerate(ROLES):          # four arcs, clockwise from the top, small gaps
        a0, a1 = math.radians(-90 + i * 90 + 8), math.radians(-90 + (i + 1) * 90 - 8)
        x0, y0 = cx + R * math.cos(a0), cy + R * math.sin(a0)
        x1, y1 = cx + R * math.cos(a1), cy + R * math.sin(a1)
        c.add(f'<path d="M{x0:.1f},{y0:.1f} A{R},{R} 0 0 1 {x1:.1f},{y1:.1f}" class="{role}-stroke"/>')
        word, dx, dy = labels[role]
        mid = math.radians(-90 + i * 90 + 45)
        lx, ly = cx + (R + 30) * math.cos(mid), cy + (R + 30) * math.sin(mid) + 5
        c.text(lx, ly, word, f"loop-label {role}-text", "start" if math.cos(mid) > 0.1 else
               "end" if math.cos(mid) < -0.1 else "middle")
    c.text(cx, cy - 2, "until verified", "loop-center", "middle")
    c.text(cx, cy + 20, "reproduce → fix → test", "loop-center-sub", "middle")
    # exit: verified patch
    # exit on the loop's free right side, between the "plan" and "edit" labels
    c.add(f'<line x1="{cx + R + 8}" y1="{cy}" x2="1112" y2="{cy}" class="rule"/>')
    c.add(f'<rect x="1112" y="{cy - 19}" width="104" height="38" rx="19" class="output-fill"/>')
    c.text(1164, cy + 6, "patch ✓", "loop-label output-text", "middle")


def terminal(c: Canvas):
    text_block(c, cta="pip install -e .")
    x, y, w, h = 772, 40, 436, 240
    c.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" class="term"/>')
    c.add(f'<path d="M{x + 1},{y + 36} V{y + 14} a13,13 0 0 1 13,-13 H{x + w - 14} a13,13 0 0 1 13,13 V{y + 36} Z" class="term-bar"/>')
    c.add(f'<line x1="{x}" y1="{y + 36}" x2="{x + w}" y2="{y + 36}" class="rule"/>')
    for i, role in enumerate(("llm", "sandbox", "output")):
        c.add(f'<circle cx="{x + 22 + i * 18}" cy="{y + 18}" r="5.5" class="{role}-solid"/>')
    c.text(x + w / 2, y + 23, "agent solve · example run", "term-dim", "middle")
    lines = [
        (None, "$ agent solve …/acme/app/issues/42"),
        ("llm", "plan      locate parse_date()"),
        ("sandbox", "repro     1 failed"),
        ("host", "edit      app/dates.py (+3 −1)"),
        ("sandbox", "test      no new failures"),
        ("output", "status    resolved · PR opened"),
    ]
    for i, (role, s) in enumerate(lines):
        ty = y + 70 + i * 28
        if role is None:
            c.text(x + 22, ty, s, "term-text")
            continue
        c.add(f'<circle cx="{x + 28}" cy="{ty - 5}" r="4.5" class="{role}-solid"/>')
        word, rest = s.split(" ", 1)
        c.text(x + 44, ty, word, f"term-text {role}-text")
        c.text(x + 44 + 8 * 9.2, ty, rest.strip(), "term-dim")


DIRECTIONS = {"minimalist": minimalist, "geometric": geometric, "terminal": terminal}


def build(style: str, theme: str) -> str:
    c = Canvas()
    DIRECTIONS[style](c)
    body = "\n".join(c.out)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">Self-Improving Coding Agent</title>
<desc id="d">Autonomous GitHub issue resolver: reproduces the bug, fixes it in a Docker sandbox, and proves the fix with tests before opening a PR. Run it with: agent solve followed by an issue URL.</desc>
<defs><style>
{css_tokens(theme)}
{STYLES}
</style></defs>
{body}
</svg>
"""


if __name__ == "__main__":
    for style in DIRECTIONS:
        for theme in ("light", "dark"):
            path = HERE / f"{style}-{W}x{H}-{theme}.svg"
            path.write_text(build(style, theme))
            print(f"wrote {path.relative_to(ROOT)}")
