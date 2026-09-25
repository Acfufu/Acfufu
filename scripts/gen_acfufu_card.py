#!/usr/bin/env python3
"""Generate assets/profile{,-zh}-{dark,light}.svg — Acfufu's profile card.

Engine cloned from the dahan8473 replica (gen_dahan_replica.py): terminal-card
layout + CSS keyframes (pet 4-frame idle animation, stepped fade-ins,
prefers-reduced-motion collapse) with the subsetted IBM Plex Mono embedded
when the build cache has it. Profile cards: pet (miku pixel sprite, frames
from miku_frames.py), stack. zh variants localize captions and labels;
terminal commands stay English in both languages. Also emits the standalone
wall card (assets/wall{,-zh}-{dark,light}.svg): titlebar + `$ cat
/var/log/wall` + the latest messages from data/wall.json — kept out of the
profile picture so the README can place it under the token dashboard; the
README's markdown link rows remain the clickable entry points.

Retired in 2026-09: whoami, projects, git log sections and a links
card (reverted — it duplicated the README's markdown link rows). The git-log
snake now lives in the token dashboard's TOKEN
ACTIVITY heatmap (token-stats.py). Glossary: CONTEXT.md.

Content is Acfufu's: measured language shares, agent-stack canon (mirrors the
token dashboard's BY TOOL order + TOP MODELS families).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from miku_frames import CELL as MCELL, FRAMES, PALETTE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
CACHE = Path("/tmp/dahan-replica-cache")  # shared: plex fonts + icons
REPO_CACHE = ROOT / "assets" / "gen-cache"  # vendored copy so CI never needs the network

W = 960
H = 500
CARD_X, CARD_W, R = 4, 952, 12
TB_H = 38

DARK = {
    "card": "#0a0e14", "titlebar": "#111826", "border": "#22406a",
    "title": "#e6edf3", "user": "#58a6ff", "desc": "#c9d1d9",
    "ok": "#a5d6ff", "liv": "#f0d861", "green": "#3fa060",
}
LIGHT = dict(DARK, card="#ffffff", titlebar="#f6f8fa", border="#a9c4e4",
             title="#1f2328", user="#0969da", desc="#424a53",
             ok="#0a5cc2", liv="#9a6700", green="#1a7f37")

MONO = "'Plex',ui-monospace,'SF Mono',Menlo,Consolas,monospace"

# measured: language bytes across all 30 public repos (github api, 2026-09)
STACK = [
    ("typescript", "TypeScript", "60"), ("python", "Python", "13"),
    ("javascript", "JavaScript", "13"), ("swift", "Swift", "2"),
    ("cplusplus", "C++", "2"), ("rust", "Rust", "1"),
    ("html5", "HTML", "1"), ("c", "C", "1"),
]

# agent-stack canon: mirrors the token dashboard (BY TOOL usage order + TOP
# MODELS families); when the two disagree, fix this line, not the dashboard.
AGENT_STACK_EN = ("also C# / Java  |  agent stack: Codex / Zcode / Opencode / "
                  "Claude Code  |  models: GLM / GPT / DeepSeek / MiniMax")

PET = {
    "name": "miku",
    "url": "codex-pets.net/#/pets/miku",
    "owner": "tune",
    "likes": 45,
    "views": "2.2k",
    "states": 9,
    "tags": "anime / pixel / soft / mascot",
}

WALL = [
    ("Acfufu", "wall initialized", "Sep 7"),
]
WALL_FILE = ROOT / "data" / "wall.json"
WALL_SHOW = 2  # message rows that fit the standalone wall card


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

# UI strings per language; terminal commands (pets status miku, cat stack,
# cat reach) stay English in both. SVG links are not clickable — the README
# markdown rows carry the functional hrefs.
STR = {
    "en": dict(
        aria="acfufu terminal profile card",
        pet_desc="based on hatsune miku",
        pet_meta=f"creature · owner: {PET['owner']} · {PET['likes']} likes · {PET['views']} views",
        pet_states=f"{PET['states']} states · tags: {PET['tags']}",
        pet_mood="mood: idle · now: singing in the terminal",
        pet_open="> open in browser: ",
        stack_cap="by bytes · 30 public repos",
        agent_stack=AGENT_STACK_EN,
        wall_aria="acfufu wall",
        wall_cap="leave a message",
        wall_hint="[wall] open a pre-filled issue - your message lands here",
    ),
    "zh": dict(
        aria="acfufu 终端画像卡",
        pet_desc="原型：初音未来",
        pet_meta=f"生物 · 主人：{PET['owner']} · {PET['likes']} 赞 · {PET['views']} 浏览",
        pet_states=f"{PET['states']} 种状态 · 标签：{PET['tags']}",
        pet_mood="心情：idle · 此刻：在终端里唱歌",
        pet_open="> 浏览器打开：",
        stack_cap="按字节 · 30 个公开仓库",
        agent_stack="还有 C# / Java  |  agent 栈：Codex / Zcode / Opencode / Claude Code  |  模型：GLM / GPT / DeepSeek / MiniMax",
        wall_aria="acfufu 留言墙",
        wall_cap="留一句话",
        wall_hint="[wall] 打开预填 issue，留言会落到这里",
    ),
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


def get_icon_paths():
    icons = {}
    for slug, _label, _pct in STACK:
        svg = fetch(f"https://cdn.simpleicons.org/{slug}").decode()
        m = re.search(r'\bd="([^"]+)"', svg)
        icons[slug] = m.group(1) if m else ""
    return icons


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


def build_css():
    return f"""
    text {{ font-family:{MONO}; font-size:15px; }}
    .ok   {{ fill:{C["ok"]}; font-size:13.5px; opacity:0; animation:on .01s steps(1) forwards; }}
    .liv  {{ fill:{C["liv"]}; font-size:13.5px; }}
    .stlab{{ font-size:12px; fill:#6e7f95; }}
    .agst {{ font-size:12px; fill:#6e7f95; }}
    .snlab{{ font-size:9.5px; fill:{C["green"]}; }}
    .wcat {{ font-size:14px; fill:{C["user"]}; }}
    .wmsg {{ font-size:14px; fill:{C["desc"]}; }}
    @keyframes on    {{ to {{ opacity:1; }} }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation: none !important; }}
      .ok {{ opacity:1; }}
    }}
    """


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


def build(theme, zh=False):
    global C
    C = LIGHT if theme == "light" else DARK
    T = STR["zh"] if zh else STR["en"]

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" role="img" '
             f'aria-label="{T["aria"]}">')
    s.append(f"<style>{font_face_css() + build_css()}</style>")

    # ---- card 1: pet (y=2, h=212) ----
    y1, h1 = 2, 212
    card_rect(s, y1, h1)
    titlebar(s, y1, "pets status miku", PET["url"])
    s.append(pet_sprite(20, y1 + TB_H + 12))
    tx = 20 + 24 * MCELL + 34
    lines = [
        ("liv", f'[PET] <tspan fill="{C["title"]}" font-weight="700">miku · {esc(T["pet_desc"])}</tspan>'),
        ("ok", f"[ OK ] {esc(T['pet_meta'])}"),
        ("ok", f"[ OK ] {esc(T['pet_states'])}"),
        ("liv", f"[LIVE] {esc(T['pet_mood'])}"),
    ]
    for i, (cls, body) in enumerate(lines):
        s.append(f'<text class="{cls}" x="{tx}" y="{y1 + TB_H + 24 + i * 20}">{body}</text>')
    s.append(f'<text x="{tx}" y="{y1 + TB_H + 24 + 4 * 20}" font-size="12.5" fill="{C["user"]}">'
             f'{esc(T["pet_open"])}{PET["url"]}</text>')

    # ---- card 2: stack (y=230, h=268) ----
    y2, h2 = 230, 268
    card_rect(s, y2, h2)
    titlebar(s, y2, "cat stack", T["stack_cap"])
    icons = get_icon_paths()
    centers_x = [140, 360, 580, 800]
    rows_y = [y2 + 109, y2 + 200]
    for idx, (slug, label, pct) in enumerate(STACK):
        cx = centers_x[idx % 4]
        cy = rows_y[idx // 4]
        s.append(f'<g transform="translate({cx - 15},{cy - 50}) scale({30 / 24})">'
                 f'<path d="{icons[slug]}" fill="{C["user"]}" fill-rule="evenodd"/></g>')
        s.append(f'<text class="stlab" x="{cx}" y="{cy}" text-anchor="middle">{esc(label)} {pct}%</text>')
    s.append(f'<text class="agst" x="14" y="{y2 + 248}">{esc(T["agent_stack"])}</text>')

    s.append("</svg>")
    return "\n".join(s)


def build_wall(theme, zh=False):
    """Standalone wall card (README places it under the token dashboard):
    titlebar + $ cat /var/log/wall + the last WALL_SHOW messages, open-air
    style (transparent body) exactly like the retired in-profile section."""
    global C
    C = LIGHT if theme == "light" else DARK
    T = STR["zh"] if zh else STR["en"]
    h = 106
    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" role="img" '
             f'aria-label="{T["wall_aria"]}">')
    s.append(f"<style>{font_face_css() + build_css()}</style>")
    y = 2
    titlebar(s, y, "wall", T["wall_cap"])
    s.append(f'<text class="wcat" x="14" y="{y + 58}">$ cat /var/log/wall</text>')
    s.append(f'<text class="snlab" x="196" y="{y + 58}">{esc(T["wall_hint"])}</text>')
    for i, (user, msg, date) in enumerate(load_wall()[-WALL_SHOW:]):
        s.append(f'<text class="wmsg" x="26" y="{y + 80 + i * 17}">'
                 f'@{esc(truncate(user, 20))}: {esc(truncate(msg, 40))}  ({esc(date)})</text>')
    s.append("</svg>")
    return "\n".join(s)


def main():
    OUT.mkdir(exist_ok=True)
    for kind, fn in (("profile", build), ("wall", build_wall)):
        for theme in ("dark", "light"):
            for zh in (False, True):
                name = f"{kind}-zh-{theme}.svg" if zh else f"{kind}-{theme}.svg"
                p = OUT / name
                p.write_text(fn(theme, zh))
                print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
