"""Build the enhanced Neofetch/btop-style terminal profile card SVGs
(dark_mode.svg / light_mode.svg) with terminal window chrome, production metrics,
flagship oc-rsync telemetry, and expanded GitHub statistics.

Usage:
    python tools/build_card.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASCII_SRC = ROOT / "assets" / "ascii-art.txt"
ASCII_SRC_LIGHT = ROOT / "assets" / "ascii-art-light.txt"
STATS_SRC = ROOT / "cache" / "stats.json"

CAREER_START = dt.date(2010, 1, 1)

ADVANCE = 0.5995
ART_COL_WIDTH = 414.0
ART_CELL_ASPECT = 0.54


def art_metrics(cols: int) -> tuple[float, float]:
    font = ART_COL_WIDTH / (cols * ADVANCE)
    return font, font * ADVANCE / ART_CELL_ASPECT

PANEL_FONT = 15.0
PANEL_LINE = 19.0
PANEL_COLS = 61

MARGIN = 16
GUTTER = 20
CHROME_H = 34  # Terminal titlebar height

THEMES = {
    "dark": {
        "art_src": ASCII_SRC,
        "bg": "#0d1117",
        "chrome_bg": "#161b22",
        "border": "#30363d",
        "fg": "#e6edf3",
        "art": "#00d2d3",          # Arcade Inky Cyan for ASCII portrait
        "key": "#00d2d3",          # Inky Cyan keys (high-tech terminal feel)
        "section": "#ff9f43",      # Clyde Orange section titles
        "value": "#e6edf3",        # Pure crisp terminal white for values
        "highlight": "#3fb950",    # Pellet Emerald Green
        "star": "#facc15",         # Arcade Pac-Man Yellow for stars
        "add": "#3fb950",          # Bright Pellet Emerald Green
        "del": "#ff4757",          # Blinky Red for deletions
        "pinky": "#ff70a6",        # Pinky Pink for highlights & contributions
        "clyde": "#ff9f43",        # Clyde Orange
        "dots": "#2d333b",         # Sleek subtle terminal dots
        "badge_bg": "#1f2937",
        "label": "#8b949e",
        "prompt_user": "#3fb950",  # Green
        "prompt_dir": "#00d2d3",   # Cyan
        "prompt_cmd": "#facc15",   # Pac-Man Yellow
        "pacman": "#facc15",       # Arcade gold Pac-Man
    },
    "light": {
        "art_src": ASCII_SRC_LIGHT,
        "bg": "#ffffff",
        "chrome_bg": "#f6f8fa",
        "border": "#d0d7de",
        "fg": "#1f2328",
        "art": "#0284c7",          # Inky Cyan (high-contrast deep cyan)
        "key": "#0284c7",          # Inky Cyan keys
        "section": "#d35400",      # Clyde Orange section titles
        "value": "#1f2328",        # Deep charcoal values (maximum readability)
        "highlight": "#1a7f37",    # Pellet Deep Emerald Green
        "star": "#ca8a04",         # Arcade Pac-Man Gold
        "add": "#1a7f37",          # Pellet Deep Emerald Green
        "del": "#d63031",          # Blinky Red
        "pinky": "#d81b60",        # Pinky Pink
        "clyde": "#d35400",        # Clyde Orange
        "dots": "#d8dee4",         # Clean soft gray dots
        "badge_bg": "#eaeef2",
        "label": "#57606a",
        "prompt_user": "#1a7f37",  # Green
        "prompt_dir": "#0284c7",   # Cyan
        "prompt_cmd": "#ca8a04",   # Pac-Man Gold
        "pacman": "#ca8a04",       # Arcade gold Pac-Man
    },
}

TITLE = "ofer@chen"

INFO = [
    ("OS", "RHEL, Rocky, Debian, Talos, Yocto"),
    ("Uptime", None),
    ("Host", "Central District, IL"),
    ("Kernel", "Sr. DevOps, Platform & AI Infra"),
    ("Virt.GPU", "KVM/QEMU, NVIDIA MIG/vGPU, PCIe"),
    ("Languages.Code", "Rust, Go, Python, Bash, C/C++"),
    ("Languages.IaC", "Terraform, OpenTofu, Crossplane"),
    ("Focus.Cloud", "K8s (CKA/CKAD), Cilium, Vault"),
    ("Focus.Net", "EVPN-VXLAN, GoBGP/RTBH, Juniper"),
    ("Certs.Verified", "CKA, CKAD, Vault, Terraform, AWS-SAA"),
]

PROD_METRICS = [
    ("Impact.BUM_Filter", "-90% Traffic (GoBGP/RTBH IPv4/v6)"),
    ("Impact.AI_Inference", "Multi-GPU LLM & Diffusion WebUI"),
    ("Impact.IaC_Fleet", "Zero Drift (100s HVs / 1000s VMs)"),
]

CONTACT = [
    ("Email", "oferchen@gmail.com"),
    ("LinkedIn", "linkedin.com/in/0ferchen"),
    ("Flagship", "github.com/oferchen/rsync (Rust)"),
]


def esc(text: str) -> str:
    return html.escape(text, quote=False)


class Row:
    """A panel row assembled from fixed segments and elastic fills."""

    def __init__(self) -> None:
        self._segs: list[dict] = []

    def text(self, value: str, cls: str | None = None, eid: str | None = None) -> "Row":
        self._segs.append({"kind": "text", "v": str(value), "cls": cls, "id": eid})
        return self

    def key(self, value: str) -> "Row":
        parts = str(value).split(".")
        for i, part in enumerate(parts):
            if i:
                self.text(".")
            self.text(part, cls="key")
        return self

    def value(self, v: str, eid: str | None = None) -> "Row":
        return self.text(v, cls="value", eid=eid)

    def fill(self, char: str = ".", cls: str = "cc", eid: str | None = None) -> "Row":
        self._segs.append({"kind": "fill", "char": char, "cls": cls, "id": eid})
        return self

    def _fixed_len(self) -> int:
        return sum(len(s["v"]) for s in self._segs if s["kind"] == "text")

    def _fill_widths(self, width: int) -> dict[int, int]:
        fills = [i for i, s in enumerate(self._segs) if s["kind"] == "fill"]
        if not fills:
            return {}
        slack = width - self._fixed_len()
        if slack < len(fills):
            raise SystemExit(
                f"row does not fit in {width} cols (needs {self._fixed_len() + len(fills)}): "
                f"{''.join(s.get('v', '~') for s in self._segs)!r}"
            )
        base, extra = divmod(slack, len(fills))
        return {idx: base + (1 if n < extra else 0) for n, idx in enumerate(fills)}

    def render(self, x: int, y: float, width: int) -> str:
        widths = self._fill_widths(width)
        out, total = [], 0
        for i, s in enumerate(self._segs):
            body = s["v"] if s["kind"] == "text" else s["char"] * widths[i]
            total += len(body)
            attrs = ""
            if s["cls"]:
                attrs += f' class="{s["cls"]}"'
            if s["id"]:
                attrs += f' id="{s["id"]}"'
            out.append(f"<tspan{attrs}>{esc(body)}</tspan>" if attrs else esc(body))
        assert total == width, f"row rendered {total} cols, expected {width}"
        return f'<tspan x="{x}" y="{y:g}">{"".join(out)}</tspan>'


def info_row(key: str, value: str, eid: str | None = None) -> Row:
    return (
        Row().text(". ", cls="cc").key(key).text(":")
        .text(" ", cls="cc").fill().text(" ", cls="cc")
        .value(value, eid)
    )


def rule_row(label: str, bold: bool = False) -> Row:
    r = Row()
    r.text(label, cls="title" if bold else "section")
    r.text(" -").fill("—", cls="cc").text("-")
    return r


def uptime(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    years = today.year - CAREER_START.year
    months = today.month - CAREER_START.month
    days = today.day - CAREER_START.day
    if days < 0:
        months -= 1
        prev = today.replace(day=1) - dt.timedelta(days=1)
        days += prev.day
    if months < 0:
        years -= 1
        months += 12

    def plural(n: int, word: str) -> str:
        return f"{n} {word}" + ("" if n == 1 else "s")

    return f"{plural(years,'year')}, {plural(months,'month')}, {plural(days,'day')}"


def load_stats() -> dict:
    defaults = {
        "repos": "119", "contrib": "142", "stars": "1,200", "forks": "84",
        "commits": "4,850", "prs": "318", "issues": "145", "followers": "56",
        "loc": "342,800", "added": "489,200", "deleted": "146,400",
        "rsync_stars": "113", "rsync_forks": "5", "rsync_ver": "v0.4.2",
        "streak_current": "19", "streak_longest": "64",
        "linkedin_followers": "3,232", "linkedin_connections": "500+",
        "linkedin_certs": "CKA, CKAD, Vault, Terraform, AWS-SAA",
    }
    if not STATS_SRC.exists():
        return defaults
    raw = json.loads(STATS_SRC.read_text(encoding="utf-8"))
    out = {}
    for k, dv in defaults.items():
        val = raw.get(k)
        if isinstance(val, int):
            out[k] = f"{val:,}"
        elif isinstance(val, str) and val:
            out[k] = val
        else:
            out[k] = dv
    return out


def load_art(src: Path) -> list[str]:
    lines = src.read_text(encoding="utf-8").split("\n")
    filled = [i for i, line in enumerate(lines) if line.strip()]
    if not filled:
        raise SystemExit(f"{src} has no content")
    body = [line.rstrip() for line in lines[filled[0]: filled[-1] + 1]]
    indent = min(len(l) - len(l.lstrip()) for l in body if l.strip())
    return [l[indent:] for l in body]


LINE_MID = 0.35
LINE_PAD = 0.65


def build_panel(x: int, y0: float) -> tuple[list[str], int]:
    st = load_stats()
    rows: list[Row | None] = [rule_row(TITLE, bold=True)]

    for item in INFO:
        if item is None:
            rows.append(None)
            continue
        key, val = item
        if key == "Uptime":
            rows.append(
                Row().text(". ", cls="cc").key(key).text(":")
                .text(" ", cls="cc").fill().text(" ", cls="cc")
                .text(uptime(), cls="starColor", eid="age_data")
            )
        elif key == "Certs.Verified":
            rows.append(
                Row().text(". ", cls="cc").key(key).text(":")
                .text(" ", cls="cc").fill().text(" ", cls="cc")
                .text(val, cls="addColor")
            )
        else:
            rows.append(info_row(key, val))

    rows.append(None)
    rows.append(rule_row("- Production Impact & Scale"))
    rows += [info_row(k, v) for k, v in PROD_METRICS]

    rows.append(None)
    rows.append(rule_row("- Contact & Flagship Engine"))
    rows.append(info_row("Email", "oferchen@gmail.com"))
    rows.append(
        Row().text(". ", cls="cc").key("LinkedIn").text(":")
        .text(" ", cls="cc").fill().text(" ", cls="cc")
        .value("in/0ferchen")
        .text(f" ({st['linkedin_followers']} followers", cls="addColor")
        .text(" | ").text(f"{st['linkedin_connections']} conn", cls="pinkyColor").text(")")
    )
    rows.append(info_row("Flagship", "github.com/oferchen/rsync (Rust)"))
    rows.append(
        Row().text(". ", cls="cc").key("oc-rsync.Spec").text(":")
        .text(" ", cls="cc").fill().text(" ", cls="cc")
        .text(f"{st['rsync_stars']}★", cls="starColor")
        .text(f" {st['rsync_forks']}⑂", cls="clydeColor")
        .text(" | SIMD • io_uring • QUIC", cls="value")
    )

    rows.append(None)
    rows.append(rule_row("- Live GitHub Telemetry"))
    rows.append(
        Row().text(". ", cls="cc").key("Repos").text(":")
        .text(" ", cls="cc").fill(eid="repo_data_dots").text(" ", cls="cc")
        .value(st["repos"], "repo_data")
        .text(" {").text("Contributed", cls="pinkyColor").text(": ")
        .value(st["contrib"], "contrib_data").text("}")
        .text(" | ").key("Stars").text(":")
        .text(" ", cls="cc").fill(eid="star_data_dots").text(" ", cls="cc")
        .text(st["stars"], cls="starColor", eid="star_data")
    )
    rows.append(
        Row().text(". ", cls="cc").key("Commits").text(":")
        .text(" ", cls="cc").fill(eid="commit_data_dots").text(" ", cls="cc")
        .value(st["commits"], "commit_data")
        .text(" | ").key("PRs").text(": ")
        .value(st["prs"], "pr_data")
        .text(" | ").key("Followers").text(":")
        .text(" ", cls="cc").fill(eid="follower_data_dots").text(" ", cls="cc")
        .value(st["followers"], "follower_data")
    )
    rows.append(
        Row().text(". ", cls="cc").key("Streak.Active").text(":")
        .text(" ", cls="cc").fill().text(" ", cls="cc")
        .text(f"{st['streak_current']}d", cls="addColor")
        .text(" (").text("Max", cls="pinkyColor").text(": ")
        .value(f"{st['streak_longest']}d").text(")")
        .text(" | ").key("Issues").text(":")
        .text(" ", cls="cc").fill().text(" ", cls="cc")
        .text(st["issues"], cls="clydeColor")
    )
    rows.append(
        Row().text(". ", cls="cc").key("Lines of Code").text(":")
        .text(" ", cls="cc").fill(eid="loc_data_dots").text(" ", cls="cc")
        .value(st["loc"], "loc_data")
        .text(" ( ").text(st["added"], cls="addColor", eid="loc_add")
        .text("++", cls="addColor").text(", ")
        .text(st["deleted"], cls="delColor", eid="loc_del")
        .text("--", cls="delColor").text(" )")
    )

    out = []
    for i, row in enumerate(rows):
        y = y0 + i * PANEL_LINE
        if row is None:
            out.append(f'<tspan x="{x}" y="{y:g}" class="cc">.</tspan>')
        else:
            out.append(row.render(x, y, PANEL_COLS))

    y = y0 + (len(rows) + 0.85) * PANEL_LINE
    out.append(
        f'<tspan x="{x}" y="{y:g}">'
        f'<tspan class="promptUser">ofer@chen</tspan><tspan class="cc">:</tspan>'
        f'<tspan class="promptDir">~/infra</tspan><tspan class="cc">$ </tspan>'
        f'<tspan class="promptCmd">cargo test --release &amp;&amp; kubectl get nodes </tspan>'
        f'<tspan class="key">█'
        f'<animate attributeName="opacity" values="1;0" dur="1.06s"'
        f' calcMode="discrete" repeatCount="indefinite"/>'
        f'</tspan></tspan>'
    )
    return out, len(rows) + 1.85


def build(theme: str) -> str:
    c = THEMES[theme]
    art = load_art(c["art_src"])
    art_cols = max(len(l) for l in art)
    art_font, art_line = art_metrics(art_cols)

    panel_x = int(MARGIN + ART_COL_WIDTH + GUTTER)
    _, panel_rows = build_panel(panel_x, 0.0)

    panel_span = (panel_rows - 1) * PANEL_LINE
    art_span = (len(art) - 1) * art_line
    half = max(panel_span / 2 + LINE_PAD * PANEL_FONT, art_span / 2 + LINE_PAD * art_font)
    body_axis = CHROME_H + MARGIN + half

    panel_lines, _ = build_panel(panel_x, body_axis - panel_span / 2 + LINE_MID * PANEL_FONT)
    art_y0 = body_axis - art_span / 2 + LINE_MID * art_font

    width = 1018
    height = round(CHROME_H + 2 * (MARGIN + half))

    art_tspans = "\n".join(
        f'<tspan x="{MARGIN}" y="{art_y0 + i * art_line:.2f}">{esc(line)}</tspan>'
        for i, line in enumerate(art)
    )

    divider_x = MARGIN + ART_COL_WIDTH + GUTTER / 2

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="{height}px"
     viewBox="0 0 {width} {height}" font-family="ConsolasFallback,Consolas,Menlo,monospace">
<style>
@font-face {{
  src: local('Consolas'), local('Consolas Bold');
  font-family: 'ConsolasFallback';
  font-display: swap;
  size-adjust: 109%;
}}
.key {{fill: {c['key']};}}
.section {{fill: {c['section']}; font-weight: bold;}}
.value {{fill: {c['value']};}}
.title {{fill: {c['star']}; font-weight: bold;}}
.addColor {{fill: {c['add']}; font-weight: bold;}}
.delColor {{fill: {c['del']}; font-weight: bold;}}
.starColor {{fill: {c['star']}; font-weight: bold;}}
.hlColor {{fill: {c['highlight']}; font-weight: bold;}}
.pinkyColor {{fill: {c['pinky']}; font-weight: bold;}}
.clydeColor {{fill: {c['clyde']}; font-weight: bold;}}
.cc {{fill: {c['dots']};}}
.promptUser {{fill: {c['prompt_user']}; font-weight: bold;}}
.promptDir {{fill: {c['prompt_dir']}; font-weight: bold;}}
.promptCmd {{fill: {c['prompt_cmd']};}}
text, tspan {{white-space: pre;}}
</style>
<!-- Outer Card Background & Border -->
<rect x="0.5" y="0.5" width="{width - 1}px" height="{height - 1}px" fill="{c['bg']}" stroke="{c['border']}" stroke-width="1" rx="14"/>
<!-- Terminal Chrome Header Bar -->
<path d="M14 1h{width - 28}a13 13 0 0 1 13 13v{CHROME_H - 14}H1V14A13 13 0 0 1 14 1z" fill="{c['chrome_bg']}"/>
<line x1="1" y1="{CHROME_H}" x2="{width - 1}" y2="{CHROME_H}" stroke="{c['border']}" stroke-width="1"/>
<!-- Traffic Light Window Controls -->
<circle cx="22" cy="{CHROME_H / 2:g}" r="6" fill="#ff5f56"/>
<circle cx="42" cy="{CHROME_H / 2:g}" r="6" fill="#ffbd2e"/>
<circle cx="62" cy="{CHROME_H / 2:g}" r="6" fill="#27c93f"/>
<text x="{width / 2:g}" y="{CHROME_H / 2 + 4.5:g}" font-size="13px" fill="{c['dots']}" text-anchor="middle">ofer@chen: ~/infrastructure — neofetch --live-telemetry (zsh)</text>
<!-- Subtle Vertical Column Divider -->
<line x1="{divider_x:g}" y1="{CHROME_H + 12}" x2="{divider_x:g}" y2="{height - 12}" stroke="{c['border']}" stroke-width="1" stroke-dasharray="3,4"/>
<!-- Left Column: 87x47 ASCII Artwork / Portrait -->
<text fill="{c['art']}" font-size="{art_font:.2f}px" class="ascii">
{art_tspans}
</text>
<!-- Right Column: Neofetch Telemetry Panel -->
<text fill="{c['fg']}" font-size="{PANEL_FONT:g}px">
{chr(10).join(panel_lines)}
</text>
</svg>
"""


def main() -> None:
    for name, c in THEMES.items():
        a = load_art(c["art_src"])
        cols = max(len(l) for l in a)
        f, ln = art_metrics(cols)
        print(f"{name:>5} art: {cols} cols x {len(a)} lines -> {f:.2f}px / {ln:.2f}px line")
    print(f"uptime   : {uptime()}")
    for name in THEMES:
        out = ROOT / f"{name}_mode.svg"
        out.write_text(build(name), encoding="utf-8")
        print(f"wrote {out.name} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
