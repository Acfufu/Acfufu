#!/usr/bin/env python3
"""Generate assets/profile-{dark,light}.svg — Acfufu's profile card.

Engine cloned from the dahan8473 replica (gen_dahan_replica.py): five-card
terminal layout + CSS keyframes (per-cell snake fill wave over a 30.7s cycle,
92 relay counters, name glitch + glow, scan sweep, stepped fade-ins,
prefers-reduced-motion collapse) with the subsetted IBM Plex Mono embedded
when the build cache has it. One addition: a PET card (miku pixel sprite,
4-frame idle animation) — frames from miku_frames.py.

Content is Acfufu's: repos, measured language shares, typing lines, wall.
Contribution numbers are mocked (fixed seed) — swap make_grid()/assign_commits
for a real GitHub data pull when wiring automation.
"""
import io
import json
import random
import re
import sys
import urllib.request
import os
import json
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from miku_frames import CELL as MCELL, FRAMES, PALETTE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CACHE = Path("/tmp/dahan-replica-cache")  # shared: plex fonts + avatars + icons
REPO_CACHE = ROOT / "assets" / "gen-cache"  # vendored copy so CI never needs the network

W = 960
CARD_X, CARD_W, R = 4, 952, 12
TB_H = 38
CYCLE = 30.7
STEP_PCT = 0.326
BODY_HOLD = 5

DARK = {
    "card": "#0a0e14", "titlebar": "#111826", "border": "#22406a",
    "title": "#e6edf3", "user": "#58a6ff", "bright": "#a5d6ff",
    "bios": "#79c0ff", "menu": "#274966", "dim": "#3f7fb8",
    "desc": "#c9d1d9", "status": "#58a6ff", "ok": "#a5d6ff",
    "liv": "#f0d861", "typ": "#a5d6ff", "green": "#3fa060",
    "track": "#161b22", "g1": "#0f4526", "g2": "#166534",
    "g3": "#22a04a", "g4": "#3fdd78",
    "snakehead": "#c9e4ff", "snakeflash": "#79c0ff", "snake": "#58a6ff",
    "port": "#6cb6ff", "pet": "#f0d861",
}
LIGHT = dict(DARK, card="#ffffff", titlebar="#f6f8fa", border="#a9c4e4",
             title="#1f2328", user="#0969da", bright="#0a5cc2",
             bios="#0a5cc2", menu="#8c9bb0", dim="#3f7fb8",
             desc="#424a53", status="#0969da", ok="#0a5cc2",
             liv="#9a6700", typ="#0a5cc2", green="#1a7f37",
             track="#ebedf0", g1="#9be9a8", g2="#40c463",
             g3="#30a14e", g4="#216e39",
             snakehead="#54aeff", snakeflash="#0a5cc2", snake="#0969da",
             port="#3872b8", pet="#9a6700")

MONO = "'Plex',ui-monospace,'SF Mono',Menlo,Consolas,monospace"

PROJECTS = [
    ("dsh-desktop", "tauri shell that runs deepseek harness natively on macos · rust · ts", "working"),
    ("radar", "one swift workspace watching claude code, codex and swe-bench", "working"),
    ("readme-showcase", "readme design skills for codex, claude code and opencode", "open source"),
    ("reach-guard", "strict-mode wrapper that keeps agent web reads on a leash", "open source"),
    ("TokenTracker", "local-first ai token and cost tracker for coding tools", "fork · in use"),
    ("phoenix-cycling-18weapons", "zero-dependency single-file mini game", "finished"),
]

# measured: language bytes across all 30 public repos (github api, 2026-09)
STACK = [
    ("typescript", "TypeScript", "60"), ("python", "Python", "13"),
    ("javascript", "JavaScript", "13"), ("swift", "Swift", "2"),
    ("cplusplus", "C++", "2"), ("rust", "Rust", "1"),
    ("html5", "HTML", "1"), ("c", "C", "1"),
]
AGENT_STACK = "also C# / Java  |  agent stack: Claude Code / Codex / DeepSeek / Tauri / LiteLLM / Vim"

PET = {
    "name": "miku",
    "desc": "based on hatsune miku",
    "kind": "creature",
    "owner": "tune",
    "likes": 45,
    "views": "2.2k",
    "states": 9,
    "tags": "anime / pixel / soft / mascot",
    "mood": "idle · now: singing in the terminal",
    "url": "codex-pets.net/#/pets/miku",
}

TYPING = [
    "shipping dsh-desktop v2",
    "watching three radars so my agents behave",
    "keeping a local daemon on a token budget",
    "open farrell-z.github.io",
]

SELFTEST = [
    ("OK", "building ai-native developer tools · shanghai"),
    ("OK", "typescript · python · javascript · swift · rust"),
    ("LIVE", "token daemon: on · stats regenerate daily"),
    ("LIVE", "last push: alas-launcher · 2d ago"),
]

WALL = [
    ("Acfufu", "wall initialized", "Sep 7"),
]

WALL_FILE = ROOT / "data" / "wall.json"
WALL_SHOW = 2  # rows that fit above the canvas edge (y6+80 / y6+97)


def dwidth(s):
    """Display columns; CJK counts double."""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def truncate(s, cols):
    out, w = "", 0
    for ch in s:
        cw = 2 if ord(ch) > 0x2E80 else 1
        if w + cw > cols:
            break
        out += ch
        w += cw
    return out


def load_wall():
    if WALL_FILE.exists():
        try:
            data = json.loads(WALL_FILE.read_text())
            return [(e["user"], e["msg"], e["date"]) for e in data]
        except Exception as e:
            print(f"[warn] {WALL_FILE}: {e}; using built-in WALL", file=sys.stderr)
    return WALL

MONTHS = ["sep", "oct", "nov", "dec", "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug"]

PIXFONT = {
    "A": [".%%%.", "%...%", "%...%", "%%%%%", "%...%", "%...%", "%...%"],
    "C": [".%%%%", "%....", "%....", "%....", "%....", "%....", ".%%%%"],
    "F": ["%%%%.", "%....", "%....", "%%%%.", "%....", "%....", "%...."],
    "U": ["%...%", "%...%", "%...%", "%...%", "%...%", "%...%", ".%%%."],
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fetch(url):
    name = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-80:]
    for base in (CACHE, REPO_CACHE):
        p = base / name
        if p.exists():
            return p.read_bytes()
    CACHE.mkdir(exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "card-builder"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    (CACHE / name).write_bytes(data)
    return data


def font_face_css():
    parts = []
    for weight, name in (("normal", "reg"), ("bold", "bold")):
        b64 = None
        for base in (CACHE, REPO_CACHE):
            p = base / f"plex-{name}.b64"
            if p.exists():
                b64 = p.read_text().strip()
                break
        if b64:
            parts.append(f"@font-face{{font-family:'Plex';font-style:normal;font-weight:{weight};"
                         f"src:url(data:font/truetype;base64,{b64}) format('truetype');}}")
    return "".join(parts)


def get_ascii_portrait(cols=46, rows=44):
    png = fetch("https://github.com/Acfufu.png")
    im = Image.open(io.BytesIO(png)).convert("L")
    im = ImageOps.autocontrast(im)
    im = im.point(lambda v: int((v / 255) ** 0.6 * 255))
    im = im.resize((cols, rows))
    px = im.load()
    ramp = " .:-=+*#%@"
    return ["".join(ramp[px[x, y] * (len(ramp) - 1) // 255] for x in range(cols))
            for y in range(rows)]


def get_icon_paths():
    icons = {}
    for slug, _label, _pct in STACK:
        svg = fetch(f"https://cdn.simpleicons.org/{slug}").decode()
        m = re.search(r'\bd="([^"]+)"', svg)
        icons[slug] = m.group(1) if m else ""
    return icons


def make_grid(weeks=53, days=7, seed=42):
    rnd = random.Random(seed)
    grid = []
    for wk in range(weeks):
        row = []
        boost = 0.3 if wk > 47 else 0.0
        for d in range(days):
            r = rnd.random() + boost
            if d >= 5:
                r *= 0.35
            if r < 0.62:
                lvl = 0
            else:
                lvl = min(4, 1 + int((r - 0.62) * 6))
            row.append(lvl)
        grid.append(row)
    return grid


def snake_path(weeks=53, days=7, w0=4, w1=44):
    cells = []
    for i, wk in enumerate(range(w0, w1)):
        order = range(days) if i % 2 == 0 else range(days - 1, -1, -1)
        for d in order:
            cells.append((wk, d))
    return cells


def assign_commits(grid, path, total=486, seed=23):
    rnd = random.Random(seed)
    raw = [grid[w][d] * rnd.randint(1, 12) for w, d in path]
    s = sum(raw) or 1
    commits = {}
    for (w, d), r in zip(path, raw):
        commits[(w, d)] = max(1, round(r * total / s))
    diff = total - sum(commits.values())
    while diff != 0:
        w, d = rnd.choice(path)
        if diff > 0:
            commits[(w, d)] += 1
            diff -= 1
        elif commits[(w, d)] > 1:
            commits[(w, d)] -= 1
            diff += 1
    return commits


CAL_URL = "https://github.com/users/Acfufu/contributions"
GRID_W, GRID_H = 53, 7


def fetch_contributions():
    """Real contribution calendar as {(week,day): (level,count)} from the
    public profile graph; None (with a warning) when unavailable, unless
    STRICT_CONTRIB=1 which raises so CI never publishes mock data."""
    try:
        html = fetch(CAL_URL).decode("utf-8", "replace")
        cells = re.findall(
            r'id="contribution-day-component-(\d+)-(\d+)"[^>]*?data-level="(\d)"', html)
        tips = re.findall(r"<tool-tip[^>]*>(.*?)</tool-tip>", html, re.S)
        if not cells or len(tips) != len(cells):
            raise ValueError(f"calendar parse got {len(cells)} cells / {len(tips)} tooltips")
        data = {}
        for (d, w, lvl), tip in zip(cells, tips):  # id is component-{day}-{week}
            m = re.match(r"\s*(\d+)\s+contributions?", tip)
            data[(int(w), int(d))] = (int(lvl), int(m.group(1)) if m else 0)
        return data
    except Exception as e:
        if os.environ.get("STRICT_CONTRIB") == "1":
            raise
        print(f"[warn] contributions fetch failed ({e}); falling back to mock grid",
              file=sys.stderr)
        return None


def real_grid(contrib, path):
    """Right-align the calendar into the 53x7 grid so recent weeks stay at the
    right edge; commits along the snake path carry real counts."""
    weeks = max(w for w, _ in contrib) + 1
    off = GRID_W - weeks
    grid = [[0] * GRID_H for _ in range(GRID_W)]
    commits = {}
    for (w, d), (lvl, cnt) in contrib.items():
        wr = w + off
        if 0 <= wr < GRID_W:
            grid[wr][d] = lvl
            commits[(wr, d)] = cnt
    return grid, commits


def pet_sprite(x, y):
    """4-frame miku sprite, CSS-driven frame swap (0.4s per frame)."""
    out = [f'<g transform="translate({x},{y})">']
    n = len(FRAMES)
    for fi, frame in enumerate(FRAMES):
        base = "" if fi == 0 else ' opacity="0"'
        vals = ";".join("1" if k == fi else "0" for k in range(n))
        kt = ";".join(f"{k / n:.3f}" for k in range(n))
        out.append(f'<g{base}><animate attributeName="opacity" calcMode="discrete" '
                   f'values="{vals}" keyTimes="{kt}" dur="{0.4 * n}s" repeatCount="indefinite"/>')
        for ry, row in enumerate(frame):
            for rx, idx in enumerate(row):
                if idx == ".":
                    continue
                out.append(f'<rect x="{rx * MCELL}" y="{ry * MCELL}" width="{MCELL}" height="{MCELL}" '
                           f'fill="{PALETTE[int(idx, 16)]}"/>')
        out.append("</g>")
    out.append("</g>")
    return "".join(out)


def build_css(grid, commits, path):
    css = f"""
    text {{ font-family:{MONO}; font-size:15px; }}
    .h    {{ fill:{C["bios"]}; font-size:13px; }}
    .menu {{ fill:{C["menu"]}; font-size:12px; letter-spacing:2px; }}
    .sel  {{ fill:{C["bright"]}; font-size:12px; letter-spacing:2px; }}
    .px   {{ fill:{C["user"]}; }}
    .port {{ fill:{C["port"]}; font-size:5.5px; opacity:.95; }}
    .ok   {{ fill:{C["ok"]}; font-size:13.5px; opacity:0; animation:on .01s steps(1) forwards; }}
    .liv  {{ fill:{C["liv"]}; font-size:13.5px; }}
    .typ  {{ fill:{C["typ"]}; font-size:13px; }}
    .pr   {{ fill:{C["user"]}; font-size:13px; }}
    .stat {{ fill:{C["status"]}; font-size:14.5px; }}
    .stlab{{ font-size:12px; fill:#6e7f95; }}
    .snlab{{ font-size:9.5px; fill:{C["green"]}; }}
    .sncnt{{ font-size:9.5px; fill:{C["status"]}; }}
    .wcat {{ font-size:14px; fill:{C["status"]}; }}
    .wmsg {{ font-size:14px; fill:{C["desc"]}; }}
    .agst {{ font-size:12px; fill:#6e7f95; }}
    .d1 {{ animation-delay:.7s; }} .d2 {{ animation-delay:.9s; }}
    .d3 {{ animation-delay:1.1s; }} .d4 {{ animation-delay:1.3s; }}
    .cur   {{ animation:blink 1.1s steps(1) infinite; }}
    .glitch{{ animation:glitch 7s steps(1) 3s infinite; }}
    .sweep {{ animation:sweep 9s linear infinite; }}
    @keyframes on    {{ to {{ opacity:1; }} }}
    @keyframes blink {{ 50% {{ opacity:0; }} }}
    @keyframes glitch {{
      0%,96.5%,98%,100% {{ transform:translate(0,0); }}
      97%   {{ transform:translate(3px,-1px); }}
      97.5% {{ transform:translate(-3px,1px); }}
    }}
    @keyframes sweep {{ from {{ transform:translateY(-40px); }} to {{ transform:translateY(420px); }} }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation: none !important; }}
      .ok {{ opacity:1; }}
    }}
    """
    greens = {0: C["track"], 1: C["g1"], 2: C["g2"], 3: C["g3"], 4: C["g4"]}
    parts = [css]
    for i, (w, d) in enumerate(path):
        a = i * STEP_PCT
        b = a + STEP_PCT
        c = a + 2 * STEP_PCT
        e = a + (2 + BODY_HOLD) * STEP_PCT
        orig = greens[grid[w][d]]
        parts.append(
            f".s{i} {{ animation: k{i} {CYCLE}s linear infinite; }}\n"
            f"@keyframes k{i} {{\n"
            f"  0%,{a:.3f}% {{ fill:{orig}; }}\n"
            f"  {a + 0.05:.3f}% {{ fill:{C['snakehead']}; }}\n"
            f"  {b:.3f}% {{ fill:{C['snakeflash']}; }}\n"
            f"  {c:.3f}%,{e - 0.05:.3f}% {{ fill:{C['snake']}; }}\n"
            f"  {e:.3f}%,100% {{ fill:{C['track']}; }}\n"
            f"}}\n")
    prefix, run = [0], 0
    for w, d in path:
        run += commits.get((w, d), 0)
        prefix.append(run)
    total = prefix[-1]
    nc = 92
    for k in range(nc):
        i0 = round(k * len(path) / nc)
        i1 = round((k + 1) * len(path) / nc)
        a = i0 * STEP_PCT
        b = min(i1 * STEP_PCT, 100.0)
        parts.append(
            f".n{k} {{ opacity:0; animation:n{k} {CYCLE}s steps(1,end) infinite; }}\n"
            f"@keyframes n{k} {{ 0% {{ opacity:0; }} {a:.3f}% {{ opacity:1; }} "
            f"{b:.3f}%,100% {{ opacity:0; }} }}\n")
    return "\n".join(parts), prefix, nc, total


def titlebar(s, y, cmd, caption):
    s.append(f'<rect x="{CARD_X}" y="{y}" width="{CARD_W}" height="{TB_H}" rx="{R}" '
             f'fill="{C["titlebar"]}" stroke="{C["border"]}"/>')
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        s.append(f'<circle cx="{24 + i * 18}" cy="{y + 19}" r="5.5" fill="{c}"/>')
    s.append(f'<text x="86" y="{y + 25.2}">'
             f'<tspan fill="{C["user"]}" font-weight="700">acfufu@farrell-z</tspan>'
             f'<tspan fill="#6e7f95"> ~ % </tspan>'
             f'<tspan fill="{C["title"]}">{esc(cmd)}</tspan></text>')
    s.append(f'<text x="{CARD_X + CARD_W - 20}" y="{y + 25.2}" fill="#6e7f95" '
             f'text-anchor="end">{esc(caption)}</text>')


def card_rect(s, y, h):
    s.append(f'<rect x="{CARD_X}" y="{y}" width="{CARD_W}" height="{h}" rx="{R}" '
             f'fill="{C["card"]}" stroke="{C["border"]}"/>')


def pixel_name(s, x, y, text, dot=10.5, pitch=13):
    dots = []
    cx = x
    for ch in text:
        if ch == " ":
            cx += pitch * 2
            continue
        for gy, row in enumerate(PIXFONT[ch]):
            for gx, c in enumerate(row):
                if c == "%":
                    dots.append(f'<rect class="px" x="{cx + gx * pitch:.0f}" y="{y + gy * pitch}" '
                                f'width="{dot}" height="{dot}" rx="2"/>')
        cx += 5 * pitch + (pitch - dot)
    s.append('<g class="glitch">')
    s.append('<g filter="url(#glow)" opacity=".5"><use href="#pxname"/></g>')
    s.append(f'<g id="pxname">{"".join(dots)}</g>')
    s.append("</g>")


def build(theme, grid, commits, path):
    global C
    C = LIGHT if theme == "light" else DARK
    css, prefix, nc, total = build_css(grid, commits, path)
    css = font_face_css() + css

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 1560" width="{W}" role="img" '
             f'aria-label="acfufu terminal profile card">')
    s.append(f"<style>{css}</style>")
    s.append('<defs>'
             '<filter id="glow" x="-20%" y="-20%" width="140%" height="140%">'
             '<feGaussianBlur stdDeviation="3"/></filter>'
             '<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">'
             '<stop offset="0" stop-color="#a5d6ff" stop-opacity="0"/>'
             '<stop offset=".5" stop-color="#a5d6ff" stop-opacity=".07"/>'
             '<stop offset="1" stop-color="#a5d6ff" stop-opacity="0"/>'
             '</linearGradient>'
             '<clipPath id="frame"><rect x="4" y="2" width="952" height="433" rx="12"/></clipPath>'
             '</defs>')

    # ---- card 1: whoami ----
    y1, h1 = 2, 433
    card_rect(s, y1, h1)
    s.append('<g clip-path="url(#frame)">')
    titlebar(s, y1, "whoami", "who i am")
    s.append(f'<text class="h" x="36" y="{y1 + 86}">ACFUFU BIOS (TM)  COPYRIGHT (C) 2026</text>')
    s.append(f'<text class="menu" x="{CARD_X + CARD_W - 20}" y="{y1 + 86}" text-anchor="end">PORT......8080</text>')
    my = y1 + 118
    s.append(f'<text class="sel" x="36" y="{my}">&gt; WHOAMI</text>')
    mx = 150
    for m in ["PROJECTS", "STACK", "COMMITS", "PET", "WALL"]:
        s.append(f'<text class="menu" x="{mx}" y="{my}">{m}</text>')
        mx += len(m) * 7.2 + 36
    s.append(f'<text class="menu" x="{CARD_X + CARD_W - 20}" y="{my}" text-anchor="end">MEM TEST: 640K OK</text>')
    art = get_ascii_portrait()
    ax, ay, lh = 36, y1 + 138, 5.5
    for i, row in enumerate(art):
        s.append(f'<text class="port" x="{ax}" y="{ay + i * lh:.1f}" xml:space="preserve">{esc(row)}</text>')
    s.append(f'<text class="menu" x="36" y="{ay + len(art) * lh + 16}">[ SELF TEST: PASS ]</text>')
    pixel_name(s, 286, y1 + 132, "ACFUFU")
    for i, (tag, msg) in enumerate(SELFTEST):
        cls = "liv" if tag == "LIVE" else "ok"
        label = f"[ {tag} ]" if tag == "OK" else "[LIVE]"
        s.append(f'<text class="{cls} d{i + 1}" x="286" y="{y1 + 262 + i * 22}">'
                 f'{label}<tspan fill="{C["desc"]}"> {esc(msg)}</tspan></text>')
    s.append(f'<text class="pr" x="286" y="{y1 + 368}">$</text>')
    for li, line in enumerate(TYPING):
        wd = int(len(line) * 7.8)
        s.append(f'<clipPath id="tc{li}"><rect x="306" y="{y1 + 355}" height="21" width="{wd if li == 0 else 0}">'
                 f'<animate attributeName="width" values="0;{wd};{wd};0;0" '
                 f'keyTimes="0;0.09;0.22;0.25;1" dur="16s" begin="{li * 4}s" repeatCount="indefinite"/>'
                 f'</rect></clipPath>'
                 f'<g clip-path="url(#tc{li})"><text class="typ" x="306" y="{y1 + 368}" '
                 f'xml:space="preserve">{esc(line)}<tspan class="cur">_</tspan></text></g>')
    s.append('<rect class="sweep" x="4" y="2" width="960" height="34" fill="url(#scan)"/>')
    s.append('</g>')

    # ---- card 2: pet (y=451, h=212) ----
    y2, h2 = 451, 212
    card_rect(s, y2, h2)
    titlebar(s, y2, "pets status miku", PET["url"])
    sprite_h = len(FRAMES[0]) * MCELL
    s.append(pet_sprite(20, y2 + TB_H + 12))
    tx = 20 + 24 * MCELL + 34
    lines = [
        ("liv", f"[PET] <tspan fill=\"{C['title']}\" font-weight=\"700\">{esc(PET['name'])} · {esc(PET['desc'])}</tspan>"),
        ("ok", f"[ OK ] {esc(PET['kind'])} · owner: {esc(PET['owner'])} · {PET['likes']} likes · {PET['views']} views"),
        ("ok", f"[ OK ] {PET['states']} states · tags: {esc(PET['tags'])}"),
        ("liv", f"[LIVE] mood: {esc(PET['mood'])}"),
    ]
    for i, (cls, body) in enumerate(lines):
        s.append(f'<text class="{cls}" x="{tx}" y="{y2 + TB_H + 24 + i * 20}">{body}</text>')
    s.append(f'<text x="{tx}" y="{y2 + TB_H + 24 + 4 * 20}" font-size="12.5" fill="{C["user"]}">'
             f'&gt; open in browser: {PET["url"]}</text>')

    # ---- card 3: projects (y=679) no body ----
    y3 = 679
    titlebar(s, y3, "ls -t ~/projects", "what i'm building")
    for i, (name, desc, status) in enumerate(PROJECTS):
        ry = y3 + TB_H + 24 + i * 25
        s.append(f'<text x="14" y="{ry}">'
                 f'<tspan fill="#6e7f95">{esc(name)}</tspan>'
                 f'<tspan fill="{C["desc"]}">  {esc(desc)}</tspan></text>')
        s.append(f'<text class="stat" x="{CARD_X + CARD_W - 20}" y="{ry}" '
                 f'text-anchor="end">{esc(status)}</text>')

    # ---- card 4: stack (y=928, h=268) ----
    y4, h4 = 900, 268
    card_rect(s, y4, h4)
    titlebar(s, y4, "cat stack", "by bytes · 30 public repos")
    icons = get_icon_paths()
    centers_x = [140, 360, 580, 800]
    rows_y = [y4 + 109, y4 + 200]
    for idx, (slug, label, pct) in enumerate(STACK):
        cx = centers_x[idx % 4]
        cy = rows_y[idx // 4]
        s.append(f'<g transform="translate({cx - 15},{cy - 50}) scale({30 / 24})">'
                 f'<path d="{icons[slug]}" fill="{C["user"]}" fill-rule="evenodd"/></g>')
        s.append(f'<text class="stlab" x="{cx}" y="{cy}" text-anchor="middle">{esc(label)} {pct}%</text>')
    s.append(f'<text class="agst" x="14" y="{y4 + 248}">{esc(AGENT_STACK)}</text>')

    # ---- card 5: git log (y=1212, h=242) ----
    y5, h5 = 1184, 242
    card_rect(s, y5, h5)
    titlebar(s, y5, "git log", "commits this year")
    pitch, cell, x0, gy = 14, 11, 16, y5 + TB_H + 24
    mstep = 53 * pitch / len(MONTHS)
    for i, m in enumerate(MONTHS):
        s.append(f'<text class="snlab" x="{x0 + 4 + i * mstep:.0f}" y="{gy - 10}">{m}</text>')
    greens = {0: C["track"], 1: C["g1"], 2: C["g2"], 3: C["g3"], 4: C["g4"]}
    for i, (w, d) in enumerate(path):
        s.append(f'<rect class="s{i}" x="{x0 + w * pitch}" y="{gy + d * pitch}" '
                 f'width="{cell}" height="{cell}" rx="2.5" fill="{greens[grid[w][d]]}"/>')
    for w in range(len(grid)):
        for d in range(len(grid[0])):
            if (w, d) in path:
                continue
            s.append(f'<rect x="{x0 + w * pitch}" y="{gy + d * pitch}" width="{cell}" height="{cell}" '
                     f'rx="2.5" fill="{greens[grid[w][d]]}"/>')
    ly = gy + 93
    s.append(f'<text class="snlab" x="16" y="{ly}">$ commits eaten:</text>')
    for k in range(nc):
        i1 = round((k + 1) * len(path) / nc)
        s.append(f'<text class="sncnt n{k}" x="118" y="{ly}">{min(prefix[i1], total)}/{total}</text>')
    lx = 593
    s.append(f'<text class="snlab" x="{lx}" y="{ly}">less</text>')
    for i, f in enumerate([C["g1"], C["g2"], C["g3"], C["g4"]]):
        s.append(f'<rect x="{lx + 30 + i * 14}" y="{ly - 9}" width="{cell}" height="{cell}" rx="2.5" fill="{f}"/>')
    s.append(f'<text class="snlab" x="{lx + 30 + 4 * 14 + 6}" y="{ly}">more</text>')

    # ---- card 6: wall (y=1470) no body ----
    y6 = 1442
    titlebar(s, y6, "wall", "leave a message")
    s.append(f'<text class="wcat" x="14" y="{y6 + 58}">$ cat /var/log/wall</text>')
    s.append(f'<text class="snlab" x="196" y="{y6 + 58}">'
             f'[wall] open a pre-filled issue - your message lands here</text>')
    for i, (user, msg, date) in enumerate(load_wall()[-WALL_SHOW:]):
        s.append(f'<text class="wmsg" x="26" y="{y6 + 80 + i * 17}">'
                 f'@{esc(truncate(user, 20))}: {esc(truncate(msg, 40))}  ({esc(date)})</text>')

    s.append("</svg>")
    return "\n".join(s)


def main():
    contrib = fetch_contributions()
    path = snake_path()
    if contrib:
        grid, commits = real_grid(contrib, path)
        total = sum(commits.get(c, 0) for c in path)
        src = f"real ({CAL_URL})"
    else:
        grid = make_grid()
        commits = assign_commits(grid, path)
        total = sum(commits.values())
        src = "mock (fixed seed)"
    print(f"git log: total={total} source={src}")
    OUT.mkdir(exist_ok=True)
    for theme in ("dark", "light"):
        p = OUT / f"profile-{theme}.svg"
        p.write_text(build(theme, grid, commits, path))
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
