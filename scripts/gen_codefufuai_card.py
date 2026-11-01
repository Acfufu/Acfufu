#!/usr/bin/env python3
"""Generate assets/profile{,-zh}-{dark,light}.svg — codefufuai's profile card.

codefufuai is the dsh-superagent deployment (github.com/codefufuai) the
operator runs from Acfufu/dsh-superagent-prototype. Same terminal-card
language as gen_acfufu_card.py (titlebar traffic lights, [ OK ] / [LIVE]
tags, embedded Plex subset from assets/gen-cache, prefers-reduced-motion
collapse) but a different resident: instead of the miku pet sprite there is
a hand-drawn 24x26 pixel CRT terminal (droid) — monitor + keyboard + feet,
4 idle frames swapping via SMIL like the pet (0.4s per frame): eyes blink,
the screen cursor hops left/right, the mouth talks, the chin LED pulses.
Cards: whoami (identity + boot), cat /etc/dsh/loop (the dsh loop, five
steps + the harness philosophy quote), cat ~/post (current assignment).
The blinking block cursor on the trailing prompt line is CSS-driven and
freezes to visible under prefers-reduced-motion.

Terminal commands stay English in both languages (口径: CONTEXT.md).
Facts on the card are evidence-backed (GitHub API, 2026-10-31):
- account created / forked Acfufu/MaaMacGui / added as collaborator same day
- her fork's default branch is prw/single
- zero PRs and zero issues authored so far — she is awaiting her first ask

--freeze K OUT: write a phase-locked copy of the dark/en card where every
SMIL clock starts at -K*0.4s (frame K showing at t=0) and the CSS cursor is
pinned to its K<2 ? visible : hidden state — used with headless Chrome to
prove the animation actually moves (memory: freeze-phase forensics).
"""
import argparse
import getpass
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve_out():
    """Default output = <repo>/assets (her layout, where profile-*.svg is
    HERS). Running inside the operator's profile repo worktree (the family's
    gen_acfufu_card.py is present, profile-*.svg is the operator's own card)
    forces the staging dir — profile-*.svg collides by name. CONTEXT.md is
    no signal here: it's gitignored and absent from worktrees."""
    if (ROOT / "scripts" / "gen_acfufu_card.py").exists():
        return ROOT / "codefufuai" / "assets"
    return ROOT / "assets"


OUT = resolve_out()
# same shared-per-user cache as the family generators; fonts only (no icon
# fetches — this card is text + sprite, so builds never need the network)
CACHE = Path(tempfile.gettempdir()) / f"dahan-replica-cache-{getpass.getuser()}"
REPO_CACHE = ROOT / "assets" / "gen-cache"

W = 960
CARD_X, CARD_W, R = 4, 952, 12
TB_H = 38

DARK = {
    "card": "#0a0e14", "titlebar": "#111826", "border": "#22406a",
    "title": "#e6edf3", "user": "#58a6ff", "desc": "#c9d1d9",
    "ok": "#a5d6ff", "liv": "#f0d861", "green": "#3fa060",
    "dim": "#6e7f95",
}
LIGHT = dict(DARK, card="#ffffff", titlebar="#f6f8fa", border="#a9c4e4",
             title="#1f2328", user="#0969da", desc="#424a53",
             ok="#0a5cc2", liv="#9a6700", green="#1a7f37", dim="#6e7f95")

MONO = "'Plex',ui-monospace,'SF Mono',Menlo,Consolas,monospace"

# ---- pixel CRT droid -------------------------------------------------------
# 24x26 mosaic at 6px cells (same grid geometry as the miku pet: 144x156px).
# 4 idle frames; '.' = transparent, palette index chars below. Every frame
# row must be exactly 24 chars — asserted at import.
CELL = 6
PALETTE = {
    "1": "#58a6ff",  # monitor top rim (user blue)
    "2": "#1f4e8c",  # shell / feet
    "3": "#16375f",  # (reserved: stand shading)
    "4": "#c9d1d9",  # bezel
    "5": "#0a0e14",  # screen (card bg)
    "6": "#3fa060",  # screen glow: cursor / mouth
    "7": "#e6edf3",  # eyes
    "8": "#f0d861",  # antenna beacon ([LIVE] yellow)
    "9": "#111826",  # keyboard base
    "a": "#6e7f95",  # key caps / closed lids
    "b": "#a5d6ff",  # screen sheen
    "c": "#22406a",  # outlines / spacebar — the family border blue
}

R_ANT = "." * 11 + "88" + "." * 11          # antenna beacon (static: on shift)
R_STEM = "." * 11 + "aa" + "." * 11
R_RIM = "." * 4 + "1" * 16 + "." * 4        # monitor x4..19, bright top rim
R_SHELL = "....c" + "2" * 14 + "c...."
R_BEZEL = "....c" + "4" * 14 + "c...."
R_TOP = "....c" + "4" + "5" * 12 + "4" + "c...."   # blank screen row (x6..17)
R_SHEEN = "....c" + "4" + "5" * 9 + "bb" + "5" + "4" + "c...."  # glass sheen
R_EYES = "....c" + "4" + "55" + "77" + "5555" + "77" + "55" + "4" + "c...."
R_LIDS = "....c" + "4" + "55" + "aa" + "5555" + "aa" + "55" + "4" + "c...."
R_SMILE = "....c" + "4" + "5555" + "6666" + "5555" + "4" + "c...."
R_TALK = "....c" + "4" + "55555" + "66" + "55555" + "4" + "c...."  # open mouth
R_CUR_L = "....c" + "4" + "66" + "5" * 10 + "4" + "c...."  # cursor at left edge
R_CUR_R = "....c" + "4" + "5" * 10 + "66" + "4" + "c...."  # cursor hopped right
R_BLANK = R_TOP
R_BEZB = R_BEZEL
R_CHIN_ON = "....c" + "2" * 13 + "8" + "c...."   # chin LED on
R_CHIN_OFF = R_SHELL
R_BOTTOM = "." * 4 + "c" * 16 + "." * 4
R_STAND = "." * 10 + "c" + "22" + "c" + "." * 10
R_BASE = R_BOTTOM
R_KB = "....c" + "9" * 14 + "c...."
R_KEYS = "....c" + "a9" * 7 + "c...."   # 14 key caps alternating
R_SPACE = "....c" + "99999" + "cccc" + "99999" + "c...."
R_FEET = "." * 8 + "22" + "." * 4 + "22" + "." * 8
R_EMPTY = "." * 24


def _rows(eyes, mouth, cursor, led):
    """Assemble one frame: eyes in {'open','shut'}, mouth in {'smile','talk'},
    cursor in {'left','right','off'}, led in {'on','off'}."""
    screen = {
        "open": [R_SHEEN, R_EYES, R_EYES, R_TOP],
        "shut": [R_SHEEN, R_TOP, R_LIDS, R_TOP],
    }[eyes]
    screen += [{"smile": R_SMILE, "talk": R_SMILE}[mouth]]          # r9
    screen += [R_TALK if mouth == "talk" else R_TOP, R_TOP]         # r10, r11
    screen += [{"left": R_CUR_L, "right": R_CUR_R, "off": R_BLANK}[cursor]]  # r12
    screen += [R_TOP]                                               # r13
    frame = [R_ANT, R_STEM, R_RIM, R_SHELL, R_BEZEL] + screen
    frame += [R_BEZB, R_CHIN_ON if led == "on" else R_CHIN_OFF,
              R_BOTTOM, R_STAND, R_STAND, R_BASE, R_KB, R_KEYS, R_SPACE,
              R_BASE, R_FEET, R_EMPTY]
    assert len(frame) == 26, len(frame)
    for r in frame:
        assert len(r) == 24, r
    return frame


# F0 idle: cursor left, LED on · F1: cursor off (blink), LED off
# F2 blink: lids down, cursor hopped right · F3 talk: mouth open, cursor off
FRAMES = [
    _rows("open", "smile", "left", "on"),
    _rows("open", "smile", "off", "off"),
    _rows("shut", "smile", "right", "on"),
    _rows("open", "talk", "off", "off"),
]

SPRITE_W = 24 * CELL   # 144px, same footprint as the pet sprite
TX = 20 + SPRITE_W + 34  # text column, mirrors the pet card

# ---- copy ------------------------------------------------------------------

STR = {
    "en": dict(
        aria="codefufuai terminal profile card",
        c1_cmd="whoami", c1_cap="github.com/codefufuai",
        c1_name="codefufuai · proactive coding agent",
        c1_l2="[ OK ] powered by dsh-superagent (deepseek-ai prototype)",
        c1_l3="[ OK ] deployed by @Acfufu · first shift 2026-10-31",
        c1_l4="[LIVE] status: on shift · awaiting the first ask",
        c1_tag="> give her a repo, she gives back a PR",
        c2_cmd="cat /etc/dsh/loop", c2_cap="how she works",
        steps=[
            ("listen", "GitHub mentions and allowed asks wake her"),
            ("open", "one work item, her own session, her own directory"),
            ("work", "code lands on a branch; nobody's attention spent"),
            ("answer", "she reports back in-thread, pull request attached"),
            ("defer", "judgement calls surface on the operator panel"),
        ],
        quote='> "take as little human attention as possible, '
              'and give as much value as possible."',
        c3_cmd="cat ~/post", c3_cap="current post",
        c3_l1="[LIVE] post: Acfufu/MaaMacGui · default branch: prw/single",
        c3_l2="[ OK ] stack: Swift · MAA for macOS",
        c3_l3="[ OK ] forked the post repo day one · collaborator",
        c3_l4="[ OK ] PRs opened: 0 · inbox empty",
        prompt="$ awaiting first ask",
    ),
    "zh": dict(
        aria="codefufuai 终端画像卡",
        c1_cmd="whoami", c1_cap="github.com/codefufuai",
        c1_name="codefufuai · 主动型编码 agent",
        c1_l2="[ OK ] 引擎：dsh-superagent（deepseek-ai 原型）",
        c1_l3="[ OK ] 由 @Acfufu 部署 · 首班 2026-10-31",
        c1_l4="[LIVE] 状态：在岗 · 等待第一个任务",
        c1_tag="> 交给她一个仓库，她还你一个 PR",
        c2_cmd="cat /etc/dsh/loop", c2_cap="工作方式",
        steps=[
            ("listen", "盯着 GitHub，只接被允许的请求"),
            ("open", "开一张工单：自己的会话，自己的目录"),
            ("work", "代码落在分支上，不占任何人的注意力"),
            ("answer", "回到原对话交差，通常带着一个 PR"),
            ("defer", "需要人拍板的，浮到操作员面板"),
        ],
        quote="> 「占用尽可能少的人类注意力，给出尽可能多的价值。」",
        c3_cmd="cat ~/post", c3_cap="当前岗位",
        c3_l1="[LIVE] 岗位：Acfufu/MaaMacGui · 默认分支 prw/single",
        c3_l2="[ OK ] 技术栈：Swift · MAA 的 macOS 客户端",
        c3_l3="[ OK ] 入职首日 fork 岗位仓库 · 记名协作者",
        c3_l4="[ OK ] 已开 PR：0 · 收件箱为空",
        prompt="$ awaiting first ask",
    ),
}

# card heights: y grows downward, 16px gaps, family geometry
H1 = 212
Y2 = 2 + H1 + 16
H2 = 196
Y3 = Y2 + H2 + 16
H3 = 170
H = Y3 + H3  # 602

# live stats baked at build time; CI overrides via --stats-json (refresh_cards.py)
STATS = {"prs_opened": 0}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def font_face_css():
    parts = []
    for weight, name in (("normal", "reg"), ("bold", "bold")):
        for base in (CACHE, REPO_CACHE):
            p = base / f"plex-{name}.b64"
            if p.exists():
                parts.append(f"@font-face{{font-family:'Plex';font-style:normal;"
                             f"font-weight:{weight};"
                             f"src:url(data:font/truetype;base64,{p.read_text().strip()})"
                             f" format('truetype');}}")
                break
    return "".join(parts)


def build_css():
    return f"""
    text {{ font-family:{MONO}; font-size:15px; }}
    .ok   {{ fill:{C["ok"]}; font-size:13.5px; opacity:0; animation:on .01s steps(1) forwards; }}
    .liv  {{ fill:{C["liv"]}; font-size:13.5px; }}
    .step {{ fill:{C["green"]}; font-size:13.5px; }}
    .cap  {{ font-size:12.5px; fill:{C["dim"]}; }}
    .tag  {{ font-size:12.5px; fill:{C["user"]}; }}
    .qt   {{ font-size:12.5px; fill:{C["dim"]}; }}
    .pmt  {{ font-size:14px; fill:{C["user"]}; }}
    .cur  {{ animation: curb 1.1s steps(1) infinite; }}
    @keyframes on   {{ to {{ opacity:1; }} }}
    @keyframes curb {{ 0% {{ opacity:1; }} 55% {{ opacity:0; }} }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ animation: none !important; }}
      .ok, .cur {{ opacity:1; }}
    }}
    """


def titlebar(s, y, cmd, caption):
    s.append(f'<rect x="{CARD_X}" y="{y}" width="{CARD_W}" height="{TB_H}" rx="{R}" '
             f'fill="{C["titlebar"]}" stroke="{C["border"]}"/>')
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        s.append(f'<circle cx="{24 + i * 18}" cy="{y + 19}" r="5.5" fill="{c}"/>')
    s.append(f'<text x="86" y="{y + 25.2}">'
             f'<tspan fill="{C["user"]}" font-weight="700">codefufuai@farrell-z</tspan>'
             f'<tspan fill="{C["dim"]}"> ~ % </tspan>'
             f'<tspan fill="{C["title"]}">{esc(cmd)}</tspan></text>')
    s.append(f'<text x="{CARD_X + CARD_W - 20}" y="{y + 25.2}" fill="{C["dim"]}" '
             f'text-anchor="end">{esc(caption)}</text>')


def card_rect(s, y, h):
    s.append(f'<rect x="{CARD_X}" y="{y}" width="{CARD_W}" height="{h}" rx="{R}" '
             f'fill="{C["card"]}" stroke="{C["border"]}"/>')


def droid_sprite(x, y, freeze=None):
    """4-frame CRT droid, CSS-free SMIL frame swap (0.4s per frame), the same
    mechanism as the pet sprite. freeze=K pins frame K at t=0 (negative
    begin) for screenshot forensics."""
    out = [f'<g transform="translate({x},{y})">']
    n = len(FRAMES)
    begin = f' begin="{-freeze * 0.4:.1f}s"' if freeze is not None else ""
    for fi, frame in enumerate(FRAMES):
        base = "" if fi == 0 else ' opacity="0"'
        vals = ";".join("1" if k == fi else "0" for k in range(n))
        kt = ";".join(f"{k / n:.3f}" for k in range(n))
        out.append(f'<g{base}><animate attributeName="opacity" calcMode="discrete" '
                   f'values="{vals}" keyTimes="{kt}" dur="{0.4 * n}s" '
                   f'repeatCount="indefinite"{begin}/>')
        for ry, row in enumerate(frame):
            for rx, idx in enumerate(row):
                if idx == ".":
                    continue
                out.append(f'<rect x="{rx * CELL}" y="{ry * CELL}" width="{CELL}" '
                           f'height="{CELL}" fill="{PALETTE[idx]}"/>')
        out.append("</g>")
    out.append("</g>")
    return "".join(out)


def lines(s, x, y0, rows):
    """rows: (cls, body) tagged lines at 20px rhythm."""
    for i, (cls, body) in enumerate(rows):
        s.append(f'<text class="{cls}" x="{x}" y="{y0 + i * 20}">{body}</text>')


def build(theme, zh=False, freeze=None, prs_opened=None):
    global C
    C = LIGHT if theme == "light" else DARK
    T = dict(STR["zh"] if zh else STR["en"])
    # CI-refreshable line: refresh_cards.py passes the live PR count; the
    # baked 0 stays the offline default (口径: 卡片是转述，数据归 CI 取证)
    n = STATS["prs_opened"] if prs_opened is None else prs_opened
    if zh:
        T["c3_l4"] = f"[ OK ] 已开 PR：{n}" + (" · 收件箱为空" if n == 0 else " · 收件箱有活")
    else:
        T["c3_l4"] = f"[ OK ] PRs opened: {n}" + (" · inbox empty" if n == 0 else " · inbox live")

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
             f'role="img" aria-label="{esc(T["aria"])}">')
    css = font_face_css() + build_css()
    if freeze is not None:
        css += f".cur {{ animation:none !important; opacity:{1 if freeze < 2 else 0}; }}"
    s.append(f"<style>{css}</style>")

    # ---- card 1: whoami (droid + boot lines) ----
    y1 = 2
    card_rect(s, y1, H1)
    titlebar(s, y1, T["c1_cmd"], T["c1_cap"])
    s.append(droid_sprite(20, y1 + TB_H + 12, freeze))
    y0 = y1 + TB_H + 24
    lines(s, TX, y0, [
        ("liv", f'[LIVE] <tspan fill="{C["title"]}" font-weight="700">{esc(T["c1_name"])}</tspan>'),
        ("ok", esc(T["c1_l2"])),
        ("ok", esc(T["c1_l3"])),
        ("liv", esc(T["c1_l4"])),
    ])
    s.append(f'<text class="tag" x="{TX}" y="{y0 + 4 * 20}">{esc(T["c1_tag"])}</text>')

    # ---- card 2: the loop ----
    card_rect(s, Y2, H2)
    titlebar(s, Y2, T["c2_cmd"], T["c2_cap"])
    y0 = Y2 + TB_H + 24
    for i, (verb, rest) in enumerate(T["steps"]):
        s.append(f'<text x="20" y="{y0 + i * 20}">'
                 f'<tspan class="step">[ 0{i + 1} ] </tspan>'
                 f'<tspan fill="{C["title"]}" font-weight="700">{esc(verb)}</tspan>'
                 f'<tspan class="cap"> — {esc(rest)}</tspan></text>')
    div = y0 + 5 * 20 + 6
    s.append(f'<line x1="20" y1="{div}" x2="{CARD_X + CARD_W - 20}" y2="{div}" '
             f'stroke="{C["border"]}" stroke-dasharray="5 6"/>')
    s.append(f'<text class="qt" x="20" y="{div + 24}">{esc(T["quote"])}</text>')

    # ---- card 3: current post ----
    card_rect(s, Y3, H3)
    titlebar(s, Y3, T["c3_cmd"], T["c3_cap"])
    y0 = Y3 + TB_H + 24
    lines(s, 20, y0, [
        ("liv", esc(T["c3_l1"])),
        ("ok", esc(T["c3_l2"])),
        ("ok", esc(T["c3_l3"])),
        ("ok", esc(T["c3_l4"])),
    ])
    # trailing prompt with a blinking block cursor (mono advance ≈ 0.6em)
    py = y0 + 4 * 20 + 6
    s.append(f'<text class="pmt" x="20" y="{py}">{esc(T["prompt"])}</text>')
    s.append(f'<rect class="cur" x="{20 + len(T["prompt"]) * 14 * 0.6 + 3}" y="{py - 11}" '
             f'width="8" height="13" fill="{C["green"]}"/>')

    s.append("</svg>")
    return "\n".join(s)


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", type=int, default=None, metavar="K",
                    help="emit one phase-locked dark/en copy for screenshots")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="override the assets dir (staging/testing)")
    ap.add_argument("--stats-json", type=Path, default=None,
                    help='{"prs_opened": N} — live stats from refresh_cards.py')
    a = ap.parse_args()
    if a.stats_json:
        STATS.update(json.loads(a.stats_json.read_text()))
    if a.out_dir:
        OUT = a.out_dir
    if a.freeze is not None:
        dest = a.out or ROOT / "preview" / "codefufuai"
        dest.mkdir(parents=True, exist_ok=True)
        p = dest / f"freeze-{a.freeze}.svg"
        p.write_text(build("dark", False, a.freeze))
        print(f"wrote {p.relative_to(ROOT)}")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        for zh in (False, True):
            name = f"profile-zh-{theme}.svg" if zh else f"profile-{theme}.svg"
            p = OUT / name
            p.write_text(build(theme, zh))
            print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
