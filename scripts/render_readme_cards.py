"""Render the profile README as a stack of animated SVG cards into cards/.

    python scripts/render_readme_cards.py           # animated cards
    STATIC=1 python scripts/render_readme_cards.py  # every card at its final frame, for screenshots

The cards are shown through <img>, so each SVG carries everything inline: one <style> block with
CSS keyframes, fonts subset with pyftsubset to exactly the characters the card uses and embedded as
base64 WOFF, and the portrait drawn as text. Every animation is CSS (no SMIL), so a single
prefers-reduced-motion rule switches all of it off and leaves the final frame. Delays are
staggered so the README plays top to bottom.

Layout: every card is drawn at GitHub's 880px README column and shown at width="100%"; cards in a
row of three are exactly a third each (33.333%). The 12px gaps are baked into the SVGs, because
GitHub's own spacing between images is uneven, so the README itself has no blank lines or spaces
between images.

Colours and type follow yrmn.me (dark theme): Inter, Geist Mono for small labels and the ASCII
portrait, dark surfaces and the brand blue #3392ff.
Data: data/contributions.json and data/repos.json, written by scripts/fetch_github_data.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image, ImageEnhance, ImageOps

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
FONTS = ROOT / "fonts"
DATA = ROOT / "data"
PHOTO = ROOT / "assets" / "portrait-source.jpg"
STATIC = os.environ.get("STATIC") == "1"

# --- brand: yrmn.me, dark theme -------------------------------------------------------------------
CARD = "#171717"
LINE = "#262626"
TEXT = "#fafafa"
MUTED = "#a1a1a1"
FAINT = "#737373"
BLUE = "#3392ff"
PAPER = "#f4f4f2"
INK = "#121212"
GREEN = "#22c55e"
# Contribution levels, from an empty day to the busiest, in the brand blue.
LEVELS = ["#222222", "#123563", "#1b4f94", "#2470cf", BLUE]
EASE = "cubic-bezier(.2,.8,.2,1)"
EASE_BACK = "cubic-bezier(.34,1.45,.64,1)"

LOGIN = "oleksand4rux-del"
SITE = "https://yrmn.me"

W = 880  # GitHub's README column
GAP = 12  # gap between cards, baked into each SVG
COL = W / 3  # a card in a row of three, gap included

# When each card starts, so the page reads top to bottom.
DELAY = {"hero": 0.0, "graph": 0.5, "activity": 0.9, "tile": 1.4, "title": 1.9, "project": 2.1}


# --- fonts ------------------------------------------------------------------------------------------
@dataclass
class Font:
    family: str
    file: str
    features: str = "kern,liga,calt,tnum"
    units: int = 0
    widths: dict | None = None

    @property
    def src(self) -> Path:
        return FONTS / "src" / f"{self.file}.ttf"

    def face(self, chars: set[str]) -> str:
        """Subset to exactly the characters this card uses (pyftsubset, cached by content in
        fonts/build) and return the @font-face rule with the WOFF as a base64 data URI."""
        keep = "".join(sorted(chars | {" "}))
        key = hashlib.sha1(keep.encode()).hexdigest()[:10]
        woff = FONTS / "build" / f"{self.file}-{key}.woff"
        woff.parent.mkdir(exist_ok=True)
        if not woff.exists():
            subprocess.run(
                [
                    sys.executable, "-m", "fontTools.subset", str(self.src),
                    f"--text={keep}", "--flavor=woff", f"--layout-features={self.features}",
                    "--no-hinting", "--desubroutinize", "--name-IDs=1,2", f"--output-file={woff}",
                ],
                check=True,
            )
        b64 = base64.b64encode(woff.read_bytes()).decode()
        return f"@font-face{{font-family:'{self.family}';src:url(data:font/woff;base64,{b64}) format('woff')}}"

    def measure(self, s: str, size: float) -> float:
        if self.widths is None:
            tt = TTFont(self.src)
            self.units = tt["head"].unitsPerEm
            cmap, hmtx = tt.getBestCmap(), tt["hmtx"]
            self.widths = {chr(c): hmtx[g][0] for c, g in cmap.items()}
        return sum(self.widths.get(ch, self.units * 0.55) for ch in s) * size / self.units


REG = Font("Inter", "Inter-Regular")
MED = Font("Inter Medium", "Inter-Medium")
SEMI = Font("Inter SemiBold", "Inter-SemiBold")
DISPLAY = Font("Inter Display", "Inter-Display-SemiBold")
# No ligatures in the mono face: "###" or "==" would merge and push the portrait's columns apart.
MONO = Font("Geist Mono", "GeistMono-Regular", features="")
ALL = [REG, MED, SEMI, DISPLAY, MONO]

# Characters each font draws on the card being rendered; svg() subsets to exactly these.
USED: dict[str, set[str]] = {}


def wrap(s: str, f: Font, size: float, width: float) -> list[str]:
    lines, line = [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if f.measure(trial, size) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


# --- svg helpers ------------------------------------------------------------------------------------
BASE_CSS = (
    f"@keyframes rise{{from{{opacity:0;transform:translateY(14px)}}to{{opacity:1;transform:none}}}}"
    f"@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}"
    f"@keyframes grow{{from{{transform:scaleY(0)}}to{{transform:none}}}}"
    f"@keyframes pop{{0%{{opacity:0;transform:translateY(6px) scale(.8)}}100%{{opacity:1;transform:none}}}}"
    f"@keyframes cell{{from{{opacity:0;transform:scale(.3)}}to{{opacity:1;transform:none}}}}"
    f"@keyframes swing{{0%{{opacity:0;transform:translateY(46px) rotate(5deg)}}70%{{opacity:1;transform:translateY(-4px) rotate(-.6deg)}}100%{{opacity:1;transform:none}}}}"
    f"@keyframes nudge{{0%,70%,100%{{transform:none}}82%{{transform:translate(3px,-3px)}}}}"
    f"@keyframes ring{{0%{{opacity:.7;transform:scale(.2)}}100%{{opacity:0;transform:scale(1.6)}}}}"
    f"@keyframes sweep{{0%{{transform:translateX(0)}}40%,100%{{transform:translateX(640px)}}}}"
    f"@keyframes show{{from,to{{opacity:1}}}}@keyframes hold{{from,to{{opacity:0}}}}"
    f"@keyframes print{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}"
    f".rise{{animation:rise .8s {EASE} both}}.fade{{animation:fade .8s ease-out both}}"
    f".grow{{transform-box:fill-box;transform-origin:50% 100%;animation:grow .8s {EASE} both}}"
    f".pop{{transform-box:fill-box;transform-origin:50% 100%;animation:pop .5s {EASE_BACK} both}}"
    f".cell{{transform-box:fill-box;transform-origin:center;animation:cell .45s {EASE_BACK} both}}"
    f".swing{{transform-box:fill-box;transform-origin:50% 100%;animation:swing .9s {EASE_BACK} both}}"
    f".nudge{{animation:nudge 2.8s {EASE} infinite}}"
    f".ring{{transform-box:fill-box;transform-origin:100% 0;opacity:0;animation:ring 2.4s ease-out 3}}"
    f".sweep{{animation:sweep 7s {EASE} infinite}}"
    f".print{{animation:print .4s ease-out both}}"
    # Count-up frames show only for their slot; the final figure is hidden until its slot comes.
    f".tick{{opacity:0;animation:show .06s linear}}.last{{animation:hold 0s linear backwards}}"
)


def svg(w: float, h: float, body: str, label: str, left: float = 0, right: float = 0, bottom: float = GAP) -> str:
    """A card of w x h drawn at x=left on a transparent canvas, padded so rows tile exactly."""
    if left:
        body = f'<g transform="translate({left:.3f} 0)">{body}</g>'
    cw, ch = w + left + right, h + bottom
    faces = "".join(f.face(USED[f.family]) for f in ALL if USED.get(f.family))
    css = "" if STATIC else BASE_CSS
    # One rule turns every animation off for people who ask for less motion.
    reduce = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw:.3f}" height="{ch:.0f}" viewBox="0 0 {cw:.3f} {ch:.0f}" '
        f'role="img" aria-label="{escape(label)}"><title>{escape(label)}</title>'
        f"<style>{faces}{css}{reduce}</style>{body}</svg>"
    )


def text(x: float, y: float, s: str, f: Font, size: float, fill: str, extra: str = "", anchor: str = "start") -> str:
    USED.setdefault(f.family, set()).update(s)
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{f.family}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" {extra}>{escape(s)}</text>'
    )


def label(x: float, y: float, s: str, fill: str = FAINT, anchor: str = "start") -> str:
    """Small mono caption over a group, like the site's group labels."""
    return text(x, y, s.upper(), MONO, 11, fill, 'letter-spacing="1.1"', anchor)


def a(cls: str, delay: float) -> str:
    return f'class="{cls}" style="animation-delay:{delay:.2f}s"'


def surface(w: float, h: float, fill: str = CARD, stroke: str | None = LINE, r: int = 20) -> str:
    edge = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x=".5" y=".5" width="{w - 1:.3f}" height="{h - 1:.3f}" rx="{r}" fill="{fill}"{edge}/>'


def arrow(x: float, y: float, color: str, delay: float, size: float = 1.0) -> str:
    """↗ drawn as a path on a 24px grid, nudging now and then."""
    return (
        f'<g transform="translate({x:.1f} {y:.1f}) scale({size})"><g {a("nudge", delay)}>'
        f'<path d="M7 17 17 7M9 7h8v8" fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        f"</g></g>"
    )


def count_up(x: float, y: float, value: str, f: Font, size: float, fill: str, start: float, extra: str = "") -> str:
    """The figure counts up from zero, one text per step; plain CSS, so STATIC and reduced motion
    show the final figure only."""
    digits = "".join(ch for ch in value if ch.isdigit())
    if STATIC or not digits:
        return text(x, y, value, f, size, fill, extra)
    final, steps = int(digits), 14
    frames = sorted({round(final * (k / steps) ** 0.55) for k in range(steps)})
    out = [
        f'<g class="tick" style="animation-delay:{start + k * 0.055:.2f}s">{text(x, y, value.replace(digits, str(v), 1), f, size, fill, extra)}</g>'
        for k, v in enumerate(frames)
    ]
    out.append(f'<g class="last" style="animation-delay:{start + len(frames) * 0.055:.2f}s">{text(x, y, value, f, size, fill, extra)}</g>')
    return "".join(out)


# --- data -------------------------------------------------------------------------------------------
def load() -> tuple[list[tuple[date, int]], list[dict]]:
    c = json.loads((DATA / "contributions.json").read_text(encoding="utf-8"))
    days = [(date.fromisoformat(d["date"]), d["count"]) for d in c["days"]]
    path = DATA / "repos.json"
    repos = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return days, repos


def stats(days: list[tuple[date, int]]) -> dict:
    longest = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current = 0
    tail = days[:-1] if days and days[-1][1] == 0 else days  # today may still be empty
    for _, n in reversed(tail):
        if not n:
            break
        current += 1
    months: dict[tuple[int, int], int] = {}
    for d, n in days:
        months[(d.year, d.month)] = months.get((d.year, d.month), 0) + n
    return {
        "total": sum(n for _, n in days),
        "active": sum(1 for _, n in days if n),
        "days": len(days),
        "busiest": max(days, key=lambda d: d[1]),
        "longest": longest,
        "current": current,
        "months": months,
    }


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# --- ascii portrait ---------------------------------------------------------------------------------
RAMP = " .:-=+*#%@"  # dark -> bright: on a dark card the lit face takes the dense characters


def ascii_rows(cols: int) -> list[str]:
    """The photo as rows of characters: cropped to the head, local contrast lifted so the shadow
    side keeps its features, and near-black (the background, the dark shirt) left blank."""
    img = Image.open(PHOTO).convert("L")
    w, h = img.size
    face = img.crop((int(w * 0.24), int(h * 0.215), int(w * 0.80), int(h * 0.66)))
    rows = round(cols * face.height / face.width * 0.6)  # mono cells are 0.6 as wide as tall
    lifted = Image.blend(face, ImageOps.equalize(face), 0.55)
    lifted = ImageEnhance.Contrast(lifted).enhance(1.25).resize((cols, rows), Image.LANCZOS)
    dark = face.resize((cols, rows), Image.LANCZOS)
    px, raw = lifted.load(), dark.load()
    out = []
    for y in range(rows):
        line = "".join(
            " " if raw[x, y] < 7 else RAMP[min(len(RAMP) - 1, int((px[x, y] / 255) ** 0.9 * len(RAMP)))]
            for x in range(cols)
        )
        out.append(line.rstrip())
    return out


# --- cards ------------------------------------------------------------------------------------------
ABOUT = "I design and build digital products end to end, from discovery to production code. 9 years across fintech, Web3, SaaS and EdTech."


def hero() -> str:
    h = 420
    d0 = DELAY["hero"]
    body = [surface(W, h)]
    x = 44
    body.append(f'<g {a("fade", d0)}><rect x="{x}" y="50" width="8" height="8" rx="2" fill="{BLUE}"/>{label(x + 18, 58, "Product designer · Design engineer")}</g>')
    body.append(f'<g {a("rise", d0 + 0.12)}>{text(x - 3, 158, "Oleksandr", DISPLAY, 88, TEXT, "letter-spacing=\"-3.4\"")}</g>')
    body.append(f'<g {a("rise", d0 + 0.24)}>{text(x - 3, 246, "Yeromin", DISPLAY, 88, BLUE, "letter-spacing=\"-3.4\"")}</g>')
    for i, line in enumerate(wrap(ABOUT, REG, 18, 440)):
        body.append(f'<g {a("rise", d0 + 0.38 + i * 0.07)}>{text(x, 292 + i * 26, line, REG, 18, MUTED)}</g>')
    site_w = MED.measure("yrmn.me", 15)
    body.append(
        f'<g {a("fade", d0 + 0.7)}><circle cx="{x + 4}" cy="383" r="4" fill="{GREEN}"/>'
        f'{text(x + 16, 388, "yrmn.me", MED, 15, TEXT)}{arrow(x + 16 + site_w + 1, 372, BLUE, d0 + 1.4, 0.7)}'
        f'{text(x + 16 + site_w + 24, 388, "·  Open to remote roles", REG, 15, FAINT)}</g>'
    )
    # ASCII portrait, printed row by row like a terminal, top to bottom.
    if PHOTO.exists():
        cols, size = 78, 6.1
        cw, lh = size * 0.6, size * 1.0
        ax, ay = W - 44 - cols * cw, 38
        body.append(f'<g font-family="Geist Mono" font-size="{size}" fill="#d4d4d4">')
        for i, line in enumerate(ascii_rows(cols)):
            if not line.strip():
                continue
            # Browsers collapse spaces in SVG text inside <img>, so each row starts at its first
            # character's column and the spaces inside it are no-break spaces.
            indent = len(line) - len(line.lstrip(" "))
            row = line.lstrip(" ").replace(" ", " ")
            USED.setdefault(MONO.family, set()).update(row)
            body.append(f'<text x="{ax + indent * cw:.1f}" y="{ay + (i + 1) * lh:.1f}" {a("print", d0 + 0.3 + i * 0.035)}>{escape(row)}</text>')
        body.append("</g>")
    return svg(W, h, "".join(body), "Oleksandr Yeromin, product designer and design engineer. " + ABOUT)


def graph(days: list[tuple[date, int]]) -> str:
    h = 250
    d0 = DELAY["graph"]
    start = days[0][0] - timedelta(days=(days[0][0].weekday() + 1) % 7)  # weeks start on Sunday
    counts = dict(days)
    weeks = (days[-1][0] - start).days // 7 + 1
    pitch = (W - 88 + 3) / weeks
    cell = pitch - 3
    gx, gy = 44, 92
    nonzero = sorted(n for _, n in days if n)

    def level(n: int) -> int:
        if not n:
            return 0
        rank = sum(1 for v in nonzero if v <= n) / len(nonzero)
        return 1 + min(3, int(rank * 4 - 1e-9))

    body = [surface(W, h)]
    body.append(f'<g {a("rise", d0)}>{text(42, 62, "Every day, on GitHub", DISPLAY, 28, TEXT, "letter-spacing=\"-.6\"")}</g>')
    body.append(f'<g {a("fade", d0 + 0.1)}>{label(W - 44, 58, "Refreshed daily", anchor="end")}</g>')
    lw = 5 * pitch - 3
    lx = W - 44 - MONO.measure("more", 11) - 8 - lw
    legend_left = lx - 8 - MONO.measure("less", 11) - 12
    seen = set()
    for wk in range(weeks):
        x = gx + wk * pitch
        first = start + timedelta(days=wk * 7)
        # Month labels stop short of the legend, which shares their row.
        if first.day <= 7 and (first.year, first.month) not in seen and x + 24 < legend_left:
            seen.add((first.year, first.month))
            body.append(text(x, gy + 7 * pitch + 16, first.strftime("%b"), MONO, 11, FAINT))
        for dow in range(7):
            day = first + timedelta(days=dow)
            if day < days[0][0] or day > days[-1][0]:
                continue
            body.append(
                f'<rect x="{x:.2f}" y="{gy + dow * pitch:.2f}" width="{cell:.2f}" height="{cell:.2f}" rx="2.5" '
                f'fill="{LEVELS[level(counts.get(day, 0))]}" {a("cell", d0 + 0.15 + wk * 0.016)}/>'
            )
    # Legend, bottom right.
    ly = gy + 7 * pitch + 6
    body.append(f'<g {a("fade", d0 + 0.6)}>{text(lx - 8, ly + 10, "less", MONO, 11, FAINT, anchor="end")}')
    for i, c in enumerate(LEVELS):
        body.append(f'<rect x="{lx + i * pitch:.2f}" y="{ly:.2f}" width="{cell:.2f}" height="{cell:.2f}" rx="2.5" fill="{c}"/>')
    body.append(f'{text(lx + lw + 8, ly + 10, "more", MONO, 11, FAINT)}</g>')
    return svg(W, h, "".join(body), "Contribution graph, refreshed daily")


def activity(days: list[tuple[date, int]]) -> str:
    h = 330
    d0 = DELAY["activity"]
    s = stats(days)
    body = [surface(W, h)]
    body.append(f'<g {a("fade", d0)}>{label(44, 58, "The last 12 months on GitHub")}</g>')
    total = str(s["total"])
    tw = DISPLAY.measure(total, 46) - 1.6 * len(total)
    body.append(f'<g {a("rise", d0 + 0.08)}>{count_up(42, 108, total, DISPLAY, 46, TEXT, d0 + 0.2, "letter-spacing=\"-1.6\"")}'
                f'{text(42 + tw + 12, 108, "contributions", DISPLAY, 46, MUTED, "letter-spacing=\"-1.6\"")}</g>')
    months = sorted(s["months"].items())[-12:]
    top = max([n for _, n in months] + [1])
    cx, cw, base, chh = 44, 480, 280, 130
    step = cw / len(months)
    bw = step * 0.72
    best = max(range(len(months)), key=lambda i: months[i][1])
    for i, ((y, m), n) in enumerate(months):
        bh = max(4, chh * n / top) if n else 4
        bx = cx + i * step + (step - bw) / 2
        color = BLUE if i == best and n else ("#3a3a3a" if i < len(months) - 1 else "#2a2a2a")
        body.append(f'<rect x="{bx:.1f}" y="{base - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" fill="{color}" {a("grow", d0 + 0.2 + i * 0.05)}/>')
        body.append(text(bx + bw / 2, base + 22, date(y, m, 1).strftime("%b"), MONO, 11, FAINT, anchor="middle"))
        if i == best and n:
            body.append(f'<g {a("pop", d0 + 1.0)}>{text(bx + bw / 2, base - bh - 10, str(n), MONO, 12, BLUE, anchor="middle")}</g>')
    bd, bn = s["busiest"]
    items = [
        (plural(s["longest"], "day"), f'longest streak, current {s["current"]}'),
        (f'{s["active"]} / {s["days"]}', "days with a contribution"),
        (str(bn), f'on the busiest day, {bd.strftime("%b")} {bd.day}' if bn else "no busy day yet"),
    ]
    sx = 590
    for i, (big, small) in enumerate(items):
        y = 104 + i * 76
        body.append(f'<g {a("rise", d0 + 0.35 + i * 0.1)}>{text(sx, y, big, DISPLAY, 34, TEXT, "letter-spacing=\"-1\"")}{text(sx, y + 24, small, REG, 14, MUTED)}</g>')
        if i < len(items) - 1:
            body.append(f'<line x1="{sx}" x2="{W - 44}" y1="{y + 44}" y2="{y + 44}" stroke="{LINE}"/>')
    return svg(W, h, "".join(body), f'{s["total"]} contributions in the last 12 months, {s["active"]} active days')


@dataclass
class Tile:
    key: str
    label: str
    value: str
    word: str
    blurb: str
    href: str
    fill: str
    ink: str
    soft: str


def row_slot(pos: int) -> tuple[float, float, float]:
    """Width of a card in a row of three, and its left and right padding, so the three canvases
    are a third of the column each and the gaps between cards are exactly GAP."""
    cw = COL - GAP * 2 / 3
    return cw, [0, GAP / 3, GAP * 2 / 3][pos], [GAP * 2 / 3, GAP / 3, 0][pos]


def tile(t: Tile, pos: int) -> str:
    h = 214
    cw, left, right = row_slot(pos)
    d0 = DELAY["tile"] + pos * 0.14
    body = [f'<g {a("swing", d0)}>', surface(cw, h, t.fill, LINE if t.fill == CARD else None)]
    # A ring pulses out of the top-right corner a few times.
    if not STATIC:
        body.append(f'<circle cx="{cw - 34}" cy="34" r="54" fill="{t.ink}" fill-opacity=".12" {a("ring", d0 + 0.7)}/>')
    body.append(label(24, 40, t.label, t.soft))
    body.append(arrow(cw - 44, 22, t.ink, d0 + 1.2, 0.85))
    vsize = 52 if DISPLAY.measure(t.value, 52) < cw - 48 else 32
    body.append(count_up(22, 112, t.value, DISPLAY, vsize, t.ink, d0 + 0.12, f'letter-spacing="{-vsize * 0.035:.1f}"'))
    if t.word:
        vw = DISPLAY.measure(t.value, vsize) - vsize * 0.035 * len(t.value)
        body.append(text(22 + vw + 10, 112, t.word, DISPLAY, 30, t.ink, 'letter-spacing="-.8"'))
    for i, line in enumerate(wrap(t.blurb, MED, 14, cw - 48)[:3]):
        body.append(text(24, 152 + i * 20, line, MED, 14, t.soft))
    # A soft shine sweeps across once the tile has settled.
    if not STATIC:
        body.append(
            f'<defs><linearGradient id="s{pos}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity=".12"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<clipPath id="c{pos}"><rect width="{cw:.3f}" height="{h}" rx="20"/></clipPath></defs>'
            f'<g clip-path="url(#c{pos})"><g transform="rotate(18)"><rect x="-140" y="-60" width="110" height="{h + 120}" fill="url(#s{pos})" '
            f'{a("sweep", d0 + 1.4)}/></g></g>'
        )
    body.append("</g>")
    return svg(cw, h, "".join(body), f"{t.label}: {t.value} {t.word}. {t.blurb}".replace("  ", " "), left, right)


def section_title(s: str, accent: str, dark: bool) -> str:
    """A heading on the page itself (no card), drawn once for GitHub's dark theme and once for
    light; the README picks one with <picture>."""
    h = 54
    d0 = DELAY["title"]
    ink = TEXT if dark else INK
    rest = s.replace(accent, "").rstrip()
    rw = DISPLAY.measure(rest + " ", 28) - 0.6 * (len(rest) + 1)
    body = [f'<g {a("rise", d0)}>{text(2, 38, rest, DISPLAY, 28, ink, "letter-spacing=\"-.6\"")}'
            f'{text(2 + rw, 38, accent, DISPLAY, 28, BLUE, "letter-spacing=\"-.6\"")}</g>']
    return svg(W, h, "".join(body), s, bottom=4)


@dataclass
class Project:
    key: str
    name: str
    desc: str
    meta: str
    href: str
    mark: str


def project_card(p: Project, pos: int) -> str:
    h = 176
    cw, left, right = row_slot(pos)
    d0 = DELAY["project"] + pos * 0.12
    body = [f'<g {a("rise", d0)}>', surface(cw, h)]
    body.append(f'<rect x="24" y="31" width="9" height="9" rx="2" fill="{p.mark}"/>')
    body.append(text(42, 41, p.name, SEMI, 17, TEXT))
    body.append(arrow(cw - 44, 20, FAINT, d0 + 1.0, 0.8))
    for i, line in enumerate(wrap(p.desc, REG, 14, cw - 48)[:3]):
        body.append(text(24, 76 + i * 21, line, REG, 14, MUTED))
    body.append(text(24, h - 26, p.meta, MONO, 11, FAINT))
    body.append("</g>")
    return svg(cw, h, "".join(body), f"{p.name}: {p.desc}", left, right)


# --- main -------------------------------------------------------------------------------------------
TILES = [
    Tile("work", "Work", "5", "case studies", "Fintech, Web3, SaaS and EdTech, from research to shipped UI.",
         f"{SITE}/#projects", BLUE, "#ffffff", "#e6f0ff"),
    Tile("build", "Build", "27", "cursors", "Cursor Lab: tune a web cursor live and copy its code.",
         "https://cursor-lab-coral.vercel.app", PAPER, INK, "#3f3f46"),
    Tile("write", "Write", "@yrmn_design", "", "My Telegram channel on product design, UX/UI and AI.",
         "https://t.me/yrmn_design", CARD, TEXT, MUTED),
]


def projects(repos: list[dict]) -> list[Project]:
    lab = next((r for r in repos if r["name"] == "cursor-lab"), {})
    lang = (lab.get("primaryLanguage") or {}).get("name", "TypeScript")
    return [
        Project("cursor-lab", "cursor-lab", "An open-source workbench for custom web cursors: tune 27 of them live and copy the code.",
                f"{lang}  ·  ★ {lab.get('stargazerCount', 0)}", f"https://github.com/{LOGIN}/cursor-lab", BLUE),
        Project("yrmn", "yrmn.me", "This portfolio, designed and built end to end: Next.js, Tailwind and motion.",
                "Next.js  ·  live", SITE, PAPER),
        Project("atlas-swap", "Atlas Swap", "A crypto swap aggregator: live rates, insured deposits, one-tap swaps.",
                "Case study  ·  2026", f"{SITE}/#project-atlas-swap", GREEN),
    ]


def main() -> None:
    CARDS.mkdir(exist_ok=True)
    days, repos = load()
    out: dict[str, str] = {}

    def render(name: str, make) -> None:
        USED.clear()
        out[name] = make()

    render("hero.svg", hero)
    render("graph.svg", lambda: graph(days))
    render("activity.svg", lambda: activity(days))
    for i, t in enumerate(TILES):
        render(f"tile-{t.key}.svg", lambda t=t, i=i: tile(t, i))
    render("title-building-dark.svg", lambda: section_title("What I'm building", "building", True))
    render("title-building-light.svg", lambda: section_title("What I'm building", "building", False))
    for i, p in enumerate(projects(repos)):
        render(f"project-{p.key}.svg", lambda p=p, i=i: project_card(p, i))

    for old in CARDS.glob("*.svg"):  # drop cards that are no longer drawn
        if old.name not in out:
            old.unlink()
    for name, content in out.items():
        (CARDS / name).write_text(content, encoding="utf-8")
    sizes = ", ".join(f"{n} {len(c) // 1024}K" for n, c in out.items())
    print(f"{'static' if STATIC else 'animated'} cards: {sizes}")


if __name__ == "__main__":
    main()
