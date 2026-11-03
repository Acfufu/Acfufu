#!/usr/bin/env python3
"""Generate assets/profile{,-zh}-{dark,light}.svg — Acfufu's profile card.

Engine cloned from the dahan8473 replica (gen_dahan_replica.py): terminal-card
layout + CSS keyframes (pet idle frame animation, stepped fade-ins,
prefers-reduced-motion collapse) with the subsetted IBM Plex Mono embedded
when the build cache has it. Profile cards: pet (blossom HD sprite, base64
PNG frames from blossom_hd_frames.py — two SMIL clocks: frames flip at the
pack's native durations inside each state, while a beat-sheet overlay walks
the macro cycle flashing idle/waving/jumping/waiting; the slot is baked at
generation time from Asia/Shanghai hours — night swaps idle's own keyTimes
to hold the blink frame = asleep, zero extra bytes; qinglong's frames live
on retired in qinglong_hd_frames.py, the 4px-block mosaic in
qinglong_frames.py), stack. zh variants localize captions and
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blossom_hd_frames import BOX, STATES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
# per-user cache：共享 /tmp 固定名会被其他本地账户投毒——字体 b64 会被整文件
# 内嵌进公开 SVG（等于本地任意文件读外泄原语），图标 path 则可被注入涂改
CACHE = Path(tempfile.gettempdir()) / f"dahan-replica-cache-{getpass.getuser()}"
REPO_CACHE = ROOT / "assets" / "gen-cache"  # vendored copy so CI never needs the network

W = 960
H = 602  # grew with the pet slot: shared 144x200 sprite bbox (+38 vs the 564 era)
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
    "name": "blossom",
    "url": "~/.codex/pets/fufu-blossom",
    "owner": "acfufu",
    "states": 9,
    "frames": 57,
    "tags": "blossom / pixel / soft / mascot",
}

# pet macro-loop — two clocks. Frame clock: every state flips at the pack's
# own animation-spec durations. State clock: a beat sheet walks the macro
# cycle, flashing overlay states over the always-on idle base (segment =
# integer native loops, gaps fall through to idle, never a blank). The slot
# is BAKED at generation from Asia/Shanghai hours — fixed +08:00 offset, no
# DST, and NEVER runner-local time (wall.yml CI runs in UTC). The intensity
# tier comes from data/mood.json (written by the token-stats daemon from
# yesterday's tokens vs their 30-day median); missing/stale/invalid falls
# back to calm — the schedule degrades, never breaks.
CST = timezone(timedelta(hours=8))
SLEEP_MS = [600, 150, 150, 4000, 150, 800]  # night: idle's blink frame held = asleep
MOOD_FILE = ROOT / "data" / "mood.json"
TIERS = ("hot", "calm", "quiet")

# beat sheets per (slot, tier); (state, native loops). failed is the
# quiet-evening easter egg — the one state that trips mid-stargaze.
BEAT = {
    "morning": {
        "hot":   [("idle", 1), ("waving", 1), ("idle", 2), ("jumping", 1),
                  ("idle", 2), ("waving", 1), ("idle", 3), ("jumping", 1), ("idle", 3)],
        "calm":  [("idle", 2), ("waving", 1), ("idle", 2), ("waving", 1),
                  ("idle", 3), ("jumping", 1), ("idle", 4)],
        "quiet": [("idle", 3), ("waving", 1), ("idle", 4), ("waving", 1), ("idle", 5)],
    },
    "day": {
        "hot":   [("idle", 2), ("jumping", 1), ("idle", 2), ("waving", 1),
                  ("idle", 2), ("jumping", 1), ("idle", 3), ("waiting", 1), ("idle", 3)],
        "calm":  [("idle", 3), ("waving", 1), ("idle", 3), ("jumping", 1),
                  ("idle", 4), ("waiting", 1), ("idle", 5)],
        "quiet": [("idle", 5), ("waving", 1), ("idle", 5), ("waiting", 1), ("idle", 6)],
    },
    "evening": {
        "hot":   [("idle", 2), ("waiting", 1), ("idle", 2), ("waving", 1),
                  ("idle", 3), ("waiting", 1), ("idle", 3), ("waving", 1), ("idle", 3)],
        "calm":  [("idle", 3), ("waiting", 1), ("idle", 3), ("waiting", 1),
                  ("idle", 4), ("waving", 1), ("idle", 4)],
        "quiet": [("idle", 4), ("waiting", 1), ("idle", 4), ("waving", 1),
                  ("idle", 4), ("failed", 1), ("idle", 4)],
    },
}

MOOD = {
    ("morning", "hot"): ("mood: playful · now: bouncing good-mornings",
                         "心情：playful · 此刻：蹦跳着道早安"),
    ("morning", "calm"): ("mood: idle · now: morning greetings among the blossoms",
                          "心情：idle · 此刻：在花间道早安"),
    ("morning", "quiet"): ("mood: idle · now: a slow sleepy hello",
                           "心情：idle · 此刻：懒洋洋地说早安"),
    ("day", "hot"): ("mood: playful · now: sprinting the flower field",
                     "心情：playful · 此刻：在花田里跑酷"),
    ("day", "calm"): ("mood: idle · now: tending the blossoms",
                      "心情：idle · 此刻：在花田里巡逻"),
    ("day", "quiet"): ("mood: sleepy · now: dozing among the blossoms",
                       "心情：sleepy · 此刻：在花间打盹"),
    ("evening", "hot"): ("mood: lively · now: chasing the last sunbeams",
                         "心情：lively · 此刻：追着晚霞跑"),
    ("evening", "calm"): ("mood: idle · now: waiting for the stars",
                          "心情：idle · 此刻：在花间等星星"),
    ("evening", "quiet"): ("mood: wistful · now: stargazing (mind the step)",
                           "心情：wistful · 此刻：等星星时摔了一跤"),
    ("night", "hot"): ("mood: asleep · now: napping under the flowers (shh)",
                       "心情：asleep · 此刻：在花下睡着（嘘）"),
    ("night", "calm"): ("mood: asleep · now: napping under the flowers (shh)",
                        "心情：asleep · 此刻：在花下睡着（嘘）"),
    ("night", "quiet"): ("mood: asleep · now: napping under the flowers (shh)",
                         "心情：asleep · 此刻：在花下睡着（嘘）"),
}


def current_slot():
    h = datetime.now(CST).hour
    if 6 <= h < 9:
        return "morning"
    if 9 <= h < 18:
        return "day"
    if 18 <= h < 22:
        return "evening"
    return "night"


def load_tier():
    """当日强度档（hot/calm/quiet），读 token-stats 守护写的 data/mood.json。
    缺失 / 非当日 / 坏行一律回退 calm：外部数据只降级观感，不弄坏卡片。"""
    try:
        d = json.loads(MOOD_FILE.read_text())
    except Exception:
        return "calm"
    today = datetime.now(CST).date().isoformat()
    if isinstance(d, dict) and d.get("date") == today and d.get("tier") in TIERS:
        return d["tier"]
    return "calm"

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
        pet_desc="tiny mint-haired blossom (fufu mint style)",
        pet_meta=f"custom codex pet · owner: {PET['owner']} · codex v1 atlas",
        pet_states=f"{PET['states']} states · {PET['frames']} frames · tags: {PET['tags']}",
        pet_mood="mood: idle · now: tending the blossoms",
        pet_open="> installed at: ",
        stack_cap="by bytes · 30 public repos",  # 一次性测量（2026-09 github api），改行前先复测
        models_label="MODELS",
        wall_aria="acfufu wall",
        wall_cap="leave a message",
        wall_hint="[wall] open a pre-filled issue - your message lands here",
    ),
    "zh": dict(
        aria="acfufu 终端画像卡",
        pet_desc="薄荷花语小伙伴（Fufu Mint 风格）",
        pet_meta=f"自制 codex 宠物 · 主人：{PET['owner']} · codex v1 图集",
        pet_states=f"{PET['states']} 种状态 · {PET['frames']} 帧 · 标签：花语 / 像素 / 软萌 / 吉祥物",
        pet_mood="心情：idle · 此刻：在花间打盹",
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


def _flip_images(ms, pngs, freeze_frame=None):
    """One <image> per frame, SMIL discrete opacity at the given durations.
    freeze_frame pins that loop step at t=0 (negative begin at the step's
    midpoint — at the exact start the discrete flip already lands on the
    next frame) for screenshot forensics."""
    n = len(pngs)
    total_ms = sum(ms)
    kt = ";".join(f"{sum(ms[:i]) / total_ms:.5f}" for i in range(n))
    begin = f' begin="{-((sum(ms[:freeze_frame]) + ms[freeze_frame] / 2) / 1000):.3f}s"' \
        if freeze_frame is not None else ""
    out = []
    for fi, b64 in enumerate(pngs):
        base = "" if fi == 0 else ' opacity="0"'
        vals = ";".join("1" if k == fi else "0" for k in range(n))
        out.append(f'<image{base} width="{BOX[0]}" height="{BOX[1]}" '
                   f'href="data:image/png;base64,{b64}">'
                   f'<animate attributeName="opacity" calcMode="discrete" '
                   f'values="{vals}" keyTimes="{kt}" dur="{total_ms}ms" '
                   f'repeatCount="indefinite"{begin}/></image>')
    return out


def pet_scene(x, y, slot, tier, freeze=None):
    """Idle base layer + beat-sheet overlay groups. freeze=(state, frame)
    pins an overlay state visible and one of its frames at t=0 (two-level
    negative begin: the group's macro window midpoint + the frame's native
    step midpoint)."""
    fstate, fframe = freeze if freeze else (None, None)
    sheet = BEAT[slot][tier] if slot in BEAT else []  # night: no overlays, idle sleeps
    idle_ms = SLEEP_MS if slot == "night" else STATES["idle"][0]
    out = [f'<g transform="translate({x},{y})">']
    out += _flip_images(idle_ms, STATES["idle"][1],
                        fframe if (fstate == "idle" or slot == "night") else None)
    macro = sum(sum(STATES[st][0]) * loops for st, loops in sheet)
    windows = {}  # state -> [(start_ms, end_ms)] on the macro cycle
    t = 0
    for st, loops in sheet:
        cyc = sum(STATES[st][0]) * loops
        if st != "idle":
            windows.setdefault(st, []).append((t, t + cyc))
        t += cyc
    for st, wins in windows.items():
        ms, pngs = STATES[st]
        vals, kt = ["0"], [0.0]
        for s0, s1 in wins:
            vals += ["1", "0"]
            kt += [s0 / macro, s1 / macro]
        obegin = fbegin = ""
        if fstate == st:
            s0, s1 = wins[0]
            obegin = f' begin="{-((s0 + (s1 - s0) / 2) / 1000):.3f}s"'
            fbegin = True
        out.append(f'<g opacity="0"><animate attributeName="opacity" '
                   f'calcMode="discrete" values="{";".join(vals)}" '
                   f'keyTimes="{";".join(f"{v:.5f}" for v in kt)}" '
                   f'dur="{macro}ms" repeatCount="indefinite"{obegin}/>')
        out += _flip_images(ms, pngs, fframe if fbegin else None)
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


def build(theme, zh=False, slot="day", tier="calm", freeze=None):
    global C
    C = LIGHT if theme == "light" else DARK
    T = dict(STR["zh"] if zh else STR["en"])
    T["pet_mood"] = MOOD.get((slot, tier), MOOD[(slot, "calm")])[1 if zh else 0]

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" role="img" '
             f'aria-label="{T["aria"]}">')
    s.append(f"<style>{font_face_css() + build_css()}</style>")

    # ---- card 1: pet (y=2, h=250; slot grew 144x160 -> 144x200 with the shared sprite bbox) ----
    y1, h1 = 2, 250
    card_rect(s, y1, h1)
    titlebar(s, y1, "pets status blossom", PET["url"])
    s.append(pet_scene(20, y1 + TB_H + 8, slot, tier, freeze))
    tx = 20 + BOX[0] + 34
    # bake metadata — all real values known at generation time (no runtime
    # SMIL clock to query, so no invented live numbers)
    on_card = "idle (asleep)" if slot == "night" else \
        "idle + " + "/".join(dict.fromkeys(st for st, _ in BEAT[slot][tier] if st != "idle"))
    loop_s = sum(SLEEP_MS) / 1000 if slot == "night" else \
        sum(sum(STATES[st][0]) * loops for st, loops in BEAT[slot][tier]) / 1000
    baked = datetime.now(CST).strftime("%H:%M") + "+08"
    lines = [
        ("liv", f'[PET] <tspan fill="{C["title"]}" font-weight="700">{PET["name"]} · {esc(T["pet_desc"])}</tspan>'),
        ("ok", f"[ OK ] {esc(T['pet_meta'])}"),
        ("ok", f"[ OK ] {esc(T['pet_states'])}"),
        ("liv", f"[LIVE] {esc(T['pet_mood'])}"),
        ("ok", f"[ OK ] baked {baked} · slot {slot} · tier {tier} · loop {loop_s:.1f}s"),
        ("ok", f"[ OK ] on card: {on_card}"),
    ]
    ty0 = y1 + TB_H + 26
    for i, (cls, body) in enumerate(lines):
        s.append(f'<text class="{cls}" x="{tx}" y="{ty0 + i * 23}">{body}</text>')
    s.append(f'<text x="{tx}" y="{ty0 + len(lines) * 23 + 4}" font-size="12.5" fill="{C["user"]}">'
             f'{esc(T["pet_open"])}{PET["url"]}</text>')

    # ---- card 2: stack (y=268, h=332) ----
    y2, h2 = 268, 332
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
    ap.add_argument("--slot", choices=("morning", "day", "evening", "night"),
                    default=None, help="bake this beat sheet instead of the "
                    "Asia/Shanghai clock slot (preview/forensics)")
    ap.add_argument("--tier", choices=TIERS, default=None,
                    help="bake this intensity tier instead of data/mood.json "
                    "(preview/forensics)")
    ap.add_argument("--freeze", type=str, default=None, metavar="STATE,FRAME",
                    help="pin the pet at overlay state STATE frame FRAME "
                         "(e.g. waving,1; screenshot forensics; profile only)")
    a = ap.parse_args()
    freeze = None
    if a.freeze:
        st, fr = a.freeze.split(",")
        if st not in STATES:
            ap.error(f"--freeze state must be one of {', '.join(STATES)}")
        freeze = (st, int(fr))
    slot = a.slot or current_slot()
    tier = a.tier or load_tier()
    print(f"slot={slot} tier={tier}")
    out = a.out_dir or OUT
    out.mkdir(parents=True, exist_ok=True)
    for kind, fn in (("profile", build), ("wall", build_wall)):
        for theme in ("dark", "light"):
            for zh in (False, True):
                name = f"{kind}-zh-{theme}.svg" if zh else f"{kind}-{theme}.svg"
                p = out / name
                kw = {"slot": slot, "tier": tier, "freeze": freeze} if kind == "profile" else {}
                p.write_text(fn(theme, zh, **kw))
                print(f"wrote {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
