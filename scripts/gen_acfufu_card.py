#!/usr/bin/env python3
"""Generate assets/profile{,-zh}-{dark,light}.svg — Acfufu's profile card.

Engine cloned from the dahan8473 replica (gen_dahan_replica.py): terminal-card
layout + CSS keyframes (pet idle frame animation, stepped fade-ins,
prefers-reduced-motion collapse) with the subsetted IBM Plex Mono embedded
when the build cache has it. Profile cards: pet (qinglong HD sprite, base64
PNG frames from qinglong_hd_frames.py — the same <image>-swap mechanism as
codefufuai's card; the 4px-block mosaic lives on in qinglong_frames.py, now
only the IDLE_MS source of truth), stack. zh variants localize captions and
labels;
terminal commands stay English in both languages. Also emits the standalone
wall card (assets/wall{,-zh}-{dark,light}.svg): titlebar + `$ cat
/var/log/wall` + the latest messages from data/wall.json — kept out of the
profile picture so the README can place it under the token dashboard; the
README's markdown link rows remain the clickable entry points.

Retired in 2026-09: whoami, projects, git log sections and a links
card (reverted — it duplicated the README's markdown link rows). The git-log
snake now lives in the token dashboard's TOKEN
ACTIVITY heatmap (token-stats.py). Glossary: CONTEXT.md.

Content is Acfufu's: measured language shares (C#/Java appended as
also-used, below the measured cutoff), the tools row (everyday infra), and
the models row canon (mirrors the token dashboard's TOP MODELS families).
"""
import getpass
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qinglong_hd_frames import BOX, IDLE_MS, PNGS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
# per-user cache：共享 /tmp 固定名会被其他本地账户投毒——字体 b64 会被整文件
# 内嵌进公开 SVG（等于本地任意文件读外泄原语），图标 path 则可被注入涂改
CACHE = Path(tempfile.gettempdir()) / f"dahan-replica-cache-{getpass.getuser()}"
REPO_CACHE = ROOT / "assets" / "gen-cache"  # vendored copy so CI never needs the network

W = 960
H = 564
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

# measured: language bytes across all 30 public repos (github api, 2026-09);
# csharp/java are also-used but below the measured cutoff — no pct shown.
STACK = [
    ("typescript", "TypeScript", "60"), ("python", "Python", "13"),
    ("javascript", "JavaScript", "13"), ("swift", "Swift", "2"),
    ("cplusplus", "C++", "2"), ("rust", "Rust", "1"),
    ("html5", "HTML", "1"), ("c", "C", "1"),
    ("csharp", "C#", ""), ("java", "Java", ""),
]

# tools row: everyday infra around the languages — same grid, no pct. mlx
# has no vector anywhere (not in simple-icons, no official asset), so it
# gets a TS-style letter badge like the Z.ai mark.
TOOLS = [
    ("docker", "Docker"), ("mlx", "MLX"), ("pytorch", "PyTorch"),
    ("langgraph", "LangGraph"), ("nodedotjs", "Node.js"),
]

# simple-icons keeps losing brands to takedowns: openai left in v10, java in
# v7, csharp in v13 — pin the last release shipping each; the rest come from
# the live CDN.
ICON_URL_OVERRIDES = {
    "openai": "https://cdn.jsdelivr.net/npm/simple-icons@9.21.0/icons/openai.svg",
    "csharp": "https://cdn.jsdelivr.net/npm/simple-icons@12.4.0/icons/csharp.svg",
    "java": "https://cdn.jsdelivr.net/npm/simple-icons@6.4.0/icons/java.svg",
}

# models row canon: mirrors the token dashboard's TOP MODELS families (kimi
# and muse both appear in real usage: kimi-k3, muse-spark-*); when the two
# disagree, fix this line, not the dashboard. zai is the official badge from
# z-cdn.chatglm.cn/z-ai/static/logo.svg (30x30: rounded square + knocked-out
# Z), redrawn in card colors like the TS badge.
AI_MODELS = [
    ("zai", "Z.ai"), ("openai", "GPT"), ("claude", "Claude"),
    ("deepseek", "DeepSeek"), ("minimax", "MiniMax"),
    ("kimi", "Kimi"), ("meta", "Muse"),
]
ZAI_SQUARE = ("M24.51,28.51H5.49c-2.21,0-4-1.79-4-4V5.49c0-2.21,1.79-4,4-4h19.03"
              "c2.21,0,4,1.79,4,4v19.03C28.51,26.72,26.72,28.51,24.51,28.51z")
ZAI_KNOCKOUT = (
    "M15.47,7.1l-1.3,1.85c-0.2,0.29-0.54,0.47-0.9,0.47h-7.1V7.09C6.16,7.1,15.47,7.1,15.47,7.1z",
    "M14.53,22.91l1.31-1.86c0.2-0.29,0.54-0.47,0.9-0.47h7.09v2.33H14.53z",
)
ZAI_DIAG = "24.3,7.1 13.14,22.91 5.7,22.91 16.86,7.1"

PET = {
    "name": "qinglong",
    "url": "~/.codex/pets/fufu-qinglong",
    "owner": "acfufu",
    "states": 9,
    "frames": 57,
    "tags": "dragon / pixel / soft / mascot",
}

WALL = [
    ("Acfufu", "wall initialized", "Sep 7"),
]
WALL_FILE = ROOT / "data" / "wall.json"
WALL_SHOW = 2  # message rows that fit the standalone wall card


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
        except Exception as e:
            print(f"[warn] {WALL_FILE}: {e}; using built-in WALL", file=sys.stderr)
        else:
            rows = []
            for e in data:
                # 逐条校验：坏条目跳过而非整体回退 built-in（那会让真实留言全部消失）
                if isinstance(e, dict) and all(isinstance(e.get(k), str) and e[k]
                                               for k in ("user", "msg", "date")):
                    rows.append((e["user"], e["msg"], e["date"]))
                else:
                    print(f"[warn] {WALL_FILE}: skip invalid entry {e!r:.80}", file=sys.stderr)
            return rows
    return WALL

# UI strings per language; terminal commands (pets status qinglong, cat
# stack, cat reach) stay English in both. SVG links are not clickable — the
# README markdown rows carry the functional hrefs.
STR = {
    "en": dict(
        aria="acfufu terminal profile card",
        pet_desc="tiny jade dragon (fufu mint style)",
        pet_meta=f"custom codex pet · owner: {PET['owner']} · codex v1 atlas",
        pet_states=f"{PET['states']} states · {PET['frames']} frames · tags: {PET['tags']}",
        pet_mood="mood: idle · now: napping on a cloud",
        pet_open="> installed at: ",
        stack_cap="by bytes · 30 public repos",  # 一次性测量（2026-09 github api），改行前先复测
        models_label="MODELS",
        wall_aria="acfufu wall",
        wall_cap="leave a message",
        wall_hint="[wall] open a pre-filled issue - your message lands here",
    ),
    "zh": dict(
        aria="acfufu 终端画像卡",
        pet_desc="Fufu Mint 风格小青龙",
        pet_meta=f"自制 codex 宠物 · 主人：{PET['owner']} · codex v1 图集",
        pet_states=f"{PET['states']} 种状态 · {PET['frames']} 帧 · 标签：青龙 / 像素 / 软萌 / 吉祥物",
        pet_mood="心情：idle · 此刻：在云端打盹",
        pet_open="> 安装于：",
        stack_cap="按字节 · 30 个公开仓库",
        models_label="模型",
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
    ai_slugs = [slug for slug, _label in AI_MODELS if slug != "zai"]
    tool_slugs = [slug for slug, _label in TOOLS if slug != "mlx"]
    icons = {}
    for slug in [slug for slug, _label, _pct in STACK] + tool_slugs + ai_slugs:
        url = ICON_URL_OVERRIDES.get(slug, f"https://cdn.simpleicons.org/{slug}")
        try:
            m = re.search(r'\bd="([^"]+)"', fetch(url).decode())
            icons[slug] = m.group(1) if m else ""
        except Exception as e:
            # 单个图标失败不炸整条 wall 管线（否则 8 张卡全部停更、issue 悬死）：
            # gen-cache 已覆盖全部所需图标，此路仅新图标/CDN 变故才走
            print(f"[warn] icon {slug}: {e}", file=sys.stderr)
            icons[slug] = ""
    return icons


def pet_sprite(x, y, freeze=None):
    """6-frame qinglong HD sprite: one <image> per base64 PNG, SMIL discrete
    opacity windows at the pack's own idle durations (IDLE_MS) — the same
    mechanism as codefufuai's pet card. freeze=K pins loop step K at t=0
    (negative begin) for screenshot forensics."""
    n = len(PNGS)
    total_ms = sum(IDLE_MS)
    kt = ";".join(f"{sum(IDLE_MS[:i]) / total_ms:.4f}" for i in range(n))
    # pin at the MIDDLE of step freeze: negative begin exactly at the step's
    # start lands on its end boundary, where discrete already flips to the
    # next frame (f1/f2 froze identical that way)
    begin = f' begin="{-((sum(IDLE_MS[:freeze]) + IDLE_MS[freeze] / 2) / 1000):.3f}s"' \
        if freeze is not None else ""
    out = [f'<g transform="translate({x},{y})">']
    for fi, b64 in enumerate(PNGS):
        base = "" if fi == 0 else ' opacity="0"'
        vals = ";".join("1" if k == fi else "0" for k in range(n))
        out.append(f'<image{base} width="{BOX[0]}" height="{BOX[1]}" '
                   f'href="data:image/png;base64,{b64}">'
                   f'<animate attributeName="opacity" calcMode="discrete" '
                   f'values="{vals}" keyTimes="{kt}" dur="{total_ms}ms" '
                   f'repeatCount="indefinite"{begin}/></image>')
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


def build(theme, zh=False, freeze=None):
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
    titlebar(s, y1, "pets status qinglong", PET["url"])
    s.append(pet_sprite(20, y1 + TB_H + 12, freeze))
    tx = 20 + BOX[0] + 34
    lines = [
        ("liv", f'[PET] <tspan fill="{C["title"]}" font-weight="700">{PET["name"]} · {esc(T["pet_desc"])}</tspan>'),
        ("ok", f"[ OK ] {esc(T['pet_meta'])}"),
        ("ok", f"[ OK ] {esc(T['pet_states'])}"),
        ("liv", f"[LIVE] {esc(T['pet_mood'])}"),
    ]
    for i, (cls, body) in enumerate(lines):
        s.append(f'<text class="{cls}" x="{tx}" y="{y1 + TB_H + 24 + i * 20}">{body}</text>')
    s.append(f'<text x="{tx}" y="{y1 + TB_H + 24 + 4 * 20}" font-size="12.5" fill="{C["user"]}">'
             f'{esc(T["pet_open"])}{PET["url"]}</text>')

    # ---- card 2: stack (y=230, h=332) ----
    y2, h2 = 230, 332
    card_rect(s, y2, h2)
    titlebar(s, y2, "cat stack", T["stack_cap"])
    icons = get_icon_paths()
    centers_x = (128, 304, 480, 656, 832)
    for idx, (slug, label, pct) in enumerate(STACK):
        top = y2 + (54 if idx < 5 else 118)
        cx = centers_x[idx % 5]
        s.append(f'<g transform="translate({cx - 15},{top}) scale({30 / 24})">'
                 f'<path d="{icons[slug]}" fill="{C["user"]}" fill-rule="evenodd"/></g>')
        text = f"{label} {pct}%" if pct else label
        s.append(f'<text class="stlab" x="{cx}" y="{top + 47}" text-anchor="middle">{esc(text)}</text>')
    for idx, (slug, label) in enumerate(TOOLS):
        top = y2 + 182
        cx = centers_x[idx % 5]
        if slug == "mlx":
            s.append(f'<rect x="{cx - 15}" y="{top}" width="30" height="30" rx="6" '
                     f'fill="{C["user"]}"/>')
            s.append(f'<text x="{cx}" y="{top + 18.5}" font-size="9.5" font-weight="700" '
                     f'fill="{C["card"]}" text-anchor="middle" letter-spacing="0.3">MLX</text>')
        else:
            s.append(f'<g transform="translate({cx - 15},{top}) scale({30 / 24})">'
                     f'<path d="{icons[slug]}" fill="{C["user"]}" fill-rule="evenodd"/></g>')
        s.append(f'<text class="stlab" x="{cx}" y="{top + 47}" text-anchor="middle">{esc(label)}</text>')
    s.append(f'<line x1="20" y1="{y2 + 254}" x2="{CARD_X + CARD_W - 20}" y2="{y2 + 254}" '
             f'stroke="{C["border"]}" stroke-dasharray="5 6"/>')
    # models row: brand marks under the dashed divider; Z.ai drawn as its
    # official badge (rounded square + knocked-out Z), 30x30 source fitted
    # to the same 24px box as the other marks
    for (slug, label), cx in zip(AI_MODELS,
                                 (156, 264, 372, 480, 588, 696, 804)):
        if slug == "zai":
            s.append(f'<g transform="translate({cx - 12},{y2 + 266}) '
                     f'scale({24 / 27.02}) translate(-1.49,-1.49)">'
                     f'<path d="{ZAI_SQUARE}" fill="{C["user"]}"/>'
                     f'<polygon points="{ZAI_DIAG}" fill="{C["card"]}"/>'
                     + "".join(f'<path d="{d}" fill="{C["card"]}"/>' for d in ZAI_KNOCKOUT)
                     + "</g>")
        else:
            s.append(f'<g transform="translate({cx - 12},{y2 + 266})">'
                     f'<path d="{icons[slug]}" fill="{C["user"]}" fill-rule="evenodd"/></g>')
        s.append(f'<text class="stlab" x="{cx}" y="{y2 + 307}" text-anchor="middle">{esc(label)}</text>')
    s.append(f'<text class="snlab" x="20" y="{y2 + 307}">{esc(T["models_label"])}</text>')

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
                 f'@{esc(truncate(user, 20))}: {esc(truncate(msg, 40))}  ({esc(truncate(date, 12))})</text>')
    s.append("</svg>")
    return "\n".join(s)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="default: assets/ (use preview dirs for scratch)")
    ap.add_argument("--freeze", type=int, default=None, metavar="STEP",
                    help="pin the pet sprite at loop step STEP (screenshot "
                         "forensics; profile cards only)")
    a = ap.parse_args()
    out = a.out_dir or OUT
    out.mkdir(parents=True, exist_ok=True)
    for kind, fn in (("profile", build), ("wall", build_wall)):
        for theme in ("dark", "light"):
            for zh in (False, True):
                name = f"{kind}-zh-{theme}.svg" if zh else f"{kind}-{theme}.svg"
                p = out / name
                kw = {"freeze": a.freeze} if kind == "profile" else {}
                p.write_text(fn(theme, zh, **kw))
                print(f"wrote {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
