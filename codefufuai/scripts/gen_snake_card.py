#!/usr/bin/env python3
"""Generate assets/snake{,-zh}-{dark,light}.svg — codefufuai's commit-wall snake.

The operator's token dashboard (token-stats.py in the profile repo) runs a
blue snake that really eats the TOKEN ACTIVITY heatmap; this card ports that
mechanism wholesale — plan_snake_route() verbatim (BFS foraging: nearest
food first, darker cells on tie, body as obstacle, safe_step anti-trap,
tail-chase escape), the pops-replay occupancy simulation (never slice the
route — tail-ride steps make the body a non-contiguous set), the per-cell
fill keyframes with the escape ghost ramp and the amber swap flash, the
prefix-sum relay counter, 10 steps/s with a 2.6s end pause, and the
prefers-reduced-motion collapse. What changes is the meal: instead of token
days, the grid is HER OWN GitHub contribution wall (GraphQL
contributionsCollection, fetched by refresh_cards.py into data/contribs.json)
in GitHub-green semantics — the wall every visitor recognizes — while the
snake stays the family blue.

Fasting is honest: an empty wall renders NO snake (真吃 or nothing) — just
the static grid, a blinking [FAST] tag and "$ commits eaten: 0". The first
contribution she lands becomes food. The dashed birth marker pins the day
the account was created; as the rolling year window slides, it drifts left.

--calendar defaults to data/contribs.json; --freeze T pins every animation
to t=T s (paused + negative delay) for screenshot forensics.
"""
import argparse
import getpass
import json
import sys
import tempfile
from collections import deque
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve_assets():
    """assets dir, relative to this script's repo root (scripts/..). Inside
    the operator's profile repo this script lives at codefufuai/scripts/, so
    ROOT is already the staging dir; the guard below only matters for the
    family's own generators (same tripwire: family gen script present)."""
    if (ROOT / "scripts" / "gen_acfufu_card.py").exists():
        return ROOT / "codefufuai" / "assets"
    return ROOT / "assets"


CACHE = Path(tempfile.gettempdir()) / f"dahan-replica-cache-{getpass.getuser()}"

W = 960
CARD_X, CARD_W, R = 4, 952, 12
TB_H = 38

MONO = "'Plex',ui-monospace,'SF Mono',Menlo,Consolas,monospace"

DARK = dict(bg="#0a0e14", titlebar="#111826", border="#22406a",
            text="#e6edf3", text2="#c9d1d9", muted="#6e7f95", faint="#57606a",
            user="#58a6ff", liv="#f0d861", acc="#f59e0b",
            snake=("#c9e4ff", "#79c0ff", "#58a6ff"), snake_tail=("#4485d4", "#3a6cb0"),
            HM=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"])
LIGHT = dict(DARK, bg="#ffffff", titlebar="#f6f8fa", border="#a9c4e4",
             text="#1f2328", text2="#424a53", muted="#8c9bb0", faint="#8c959f",
             user="#0969da", liv="#9a6700", acc="#b45309",
             snake=("#54aeff", "#0a5cc2", "#0969da"), snake_tail=("#3d8ae0", "#79b3ec"),
             HM=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"])

# count → 0-4 level (GitHub-semantic; her counts stay small for a long time)
def level(n):
    return 0 if n <= 0 else 1 if n <= 2 else 2 if n <= 5 else 3 if n <= 9 else 4


# ---- foraging path: ported verbatim from the operator's token-stats.py -----
def plan_snake_route(cells, base_len=3, caps=(40, 36, 32, 28, 24, 20, 16, 12)):
    """觅食式路径：像玩家操纵的蛇逐格狩猎，而不是固定扫描线。

    cells: {(col,row): 亮度级别}，只含真实渲染的格子，级别>0 视为食物。
    每轮选目标：离蛇头最近者优先、同距偏好更暗的格子（亮度进排序键是 +2*级别
    惩罚——亮格留到最后被吃，与热力图衰减层次一致）；对前 24 个候选逐个
    BFS 最短路（蛇身为障碍），走过去途中每吃一格身体长一节。每步落子前
    检查"走完后尾巴仍可达"（BFS 头→尾）防自困；被自己围死时改追尾巴
    腾空间。上限 cap 从大到小搜索，取还能吃完全盘的最大身长。

    返回 (route, eats, growth, pops, left)：route 为逐格坐标序列；eats 为
    [(route 下标, 格子)]；growth 为触发长节的 route 下标；pops[s] 为第 s 步
    弹出的尾节数（0/1，踩尾原步与普通挪动都会弹尾，渲染器据此重放蛇身）；
    left 为没吃到的食物数（0 = 全清）。棋盘无食物时返回 None。
    """
    food = {cr for cr, lev in cells.items() if lev > 0}
    if not food:
        return None
    cmax = max(c for c, _ in cells)

    def neighbors(cr):
        c, r = cr
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (c + dc, r + dr)
            if 0 <= nb[0] <= cmax and 0 <= nb[1] <= 6 and nb in cells:
                yield nb

    def bfs(src, goal, blocked):
        if src == goal:
            return [src]
        q, seen = deque([(src, [src])]), {src}
        while q:
            cur, path = q.popleft()
            for nb in neighbors(cur):
                if nb in seen or (nb in blocked and nb != goal):
                    continue
                if nb == goal:
                    return path + [nb]
                seen.add(nb)
                q.append((nb, path + [nb]))
        return None

    def solve(cap):
        start = min(food, key=lambda cr: (cr[0], abs(cr[1] - 3)))
        remaining = set(food)
        body = deque([start])
        occupied = {start}
        route, eats, growth = [start], [], []
        pops = [0]

        def eat(cr):
            remaining.discard(cr)
            eats.append((len(route) - 1, cr))
            if base_len + len(growth) < cap:
                growth.append(len(route) - 1)

        def step_to(cr):
            removed = 0
            if cr == body[0] and cr not in remaining:
                # 踩尾原步：先弹尾再进格，保持 occupied 与 body 同步
                occupied.discard(body.popleft())
                removed = 1
            route.append(cr)
            pops.append(0)
            body.append(cr)
            occupied.add(cr)
            if cr in remaining:
                eat(cr)
            while len(body) > base_len + len(growth):
                occupied.discard(body.popleft())
                removed = 1
            pops[len(pops) - 1] = removed

        eat(start)

        def safe_step(cr):
            # 长身后尾巴必须仍可达，否则这步会把路走死
            if len(body) < 8:
                return True
            new_occ = set(occupied) | {cr}
            new_tail = body[0]
            if cr not in remaining:  # 只有吃格子才净长一节
                new_occ.discard(body[0])
                new_tail = body[1] if len(body) > 1 else cr
            return bfs(cr, new_tail, new_occ - {new_tail, cr}) is not None

        stuck = 0
        while remaining and len(route) < 4000:
            head = body[-1]
            blocked = occupied - {head}
            path = None
            for cand in sorted(
                remaining,
                key=lambda cr: abs(cr[0] - head[0]) + abs(cr[1] - head[1]) + cells[cr] * 2,
            )[:24]:
                p_ = bfs(head, cand, blocked)
                if p_ and len(p_) > 1:
                    path = p_
                    break
            if path:
                aborted = False
                for cell in path[1:]:
                    if not safe_step(cell):
                        aborted = True
                        break
                    step_to(cell)
                if not aborted:
                    stuck = 0
                    continue
            # 被围：追尾巴一步步退，尾巴挪开就腾出空间。
            # 踩尾格合法（尾巴同拍挪走，尾格必非食物、不会长身），死角全靠它脱困。
            stuck += 1
            if stuck > 400:
                break
            head = body[-1]
            tail = body[0]
            tpath = bfs(head, tail, (occupied - {head}) - {tail})
            nxt = None
            if tpath and len(tpath) > 1 and (tpath[1] == tail or tpath[1] not in occupied) and safe_step(tpath[1]):
                nxt = tpath[1]
            else:
                free = [nb for nb in neighbors(head) if nb not in occupied or nb == tail]
                safe = [nb for nb in free if safe_step(nb)]
                pool = safe or free
                if pool:  # 哪边空间大往哪边挪
                    nxt = max(pool, key=lambda cr: sum(1 for n2 in neighbors(cr) if n2 not in occupied))
            if nxt is None:
                break
            step_to(nxt)

        return route, eats, growth, pops, len(remaining)

    for cap in caps:
        route, eats, growth, pops, left = solve(cap)
        if left == 0:
            break
    return route, eats, growth, pops, left


# ---- card ------------------------------------------------------------------

NC = 8          # relay counter segments
LBL_W = 140     # "$ commits eaten:" label width before the relay segments
SPS, PAUSE = 10, 26  # 10 格/秒；片尾停 2.6s 让吃空的棋盘和满格计数停留
CELL, GAP = 12, 4
PITCH = CELL + GAP
COLS = 53
BORN = "2026-10-31"  # account created (GitHub API)

STR = {
    "en": dict(
        aria="codefufuai contribution snake card",
        cmd="tail -f /var/log/contribs", cap="her own commit wall",
        eaten_lbl="$ commits eaten:",
        live_note="[LIVE] ci on · wall refreshed daily",
        fast_note="[FAST] wall is empty · her first landed commit becomes food",
        born="born 2026-10-31", less="Less", more="More",
    ),
    "zh": dict(
        aria="codefufuai 提交墙贪吃蛇卡",
        cmd="tail -f /var/log/contribs", cap="她自己的提交墙",
        eaten_lbl="$ 吃掉的 commit：",
        live_note="[LIVE] CI 在跑 · 提交墙每日刷新",
        fast_note="[FAST] 墙还是空的 · 她落下的第一个 commit 就是食物",
        born="出生 2026-10-31", less="少", more="多",
    ),
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def font_face_css():
    parts = []
    for weight, name in (("normal", "reg"), ("bold", "bold")):
        for base in (CACHE, ROOT / "assets" / "gen-cache"):
            p = base / f"plex-{name}.b64"
            if p.exists():
                parts.append(f"@font-face{{font-family:'Plex';font-style:normal;"
                             f"font-weight:{weight};"
                             f"src:url(data:font/truetype;base64,{p.read_text().strip()})"
                             f" format('truetype');}}")
                break
    return "".join(parts)


def load_calendar(path):
    """data/contribs.json = GraphQL contributionsCollection.contributionCalendar
    (refresh_cards.py fetches it). Missing file → empty wall (offline-safe)."""
    if not path.exists():
        print(f"[warn] {path} missing — rendering an empty wall", file=sys.stderr)
        return {}
    d = json.loads(path.read_text())
    if "data" in d:  # raw GraphQL envelope
        d = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    out = {}
    for w in d.get("weeks", []):
        for day in w.get("contributionDays", []):
            out[day["date"]] = day.get("contributionCount", 0)
    return out


def build(theme, zh=False, freeze=None, cal=None):
    C = LIGHT if theme == "light" else DARK
    T = STR["zh"] if zh else STR["en"]
    today = date.today()
    born = date.fromisoformat(BORN)

    # grid geometry: 53 columns centered
    grid_w = COLS * PITCH - GAP
    gx = (W - grid_w) // 2
    gy = TB_H + 26
    grid_h = 7 * PITCH - GAP

    # days on the wall: {(col,row): level}; future days of the current week
    # are not rendered (grid ends short, like GitHub's own partial column)
    cal = cal if cal is not None else load_calendar(ASSETS.parent / "data" / "contribs.json")
    start = today - timedelta(days=52 * 7 + (today.weekday() + 1) % 7)
    cells, counts = {}, {}
    for i in range(COLS):
        for row in range(7):
            dd = start + timedelta(days=i * 7 + row)
            if dd > today:
                break
            lev = level(cal.get(dd.isoformat(), 0))
            cells[(i, row)] = lev
            counts[(i, row)] = cal.get(dd.isoformat(), 0)

    born_col = next((i for i in range(COLS)
                     if start + timedelta(days=i * 7) <= born < start + timedelta(days=i * 7 + 7)), None)

    H = TB_H + 26 + grid_h + 30 + 18 + 16
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
         f'role="img" aria-label="{esc(T["aria"])}">']
    s.append(f"<style>{font_face_css()}\n"
             f"    text {{ font-family:{MONO}; font-size:15px; }}\n"
             + "".join(f"    .h{k} {{ fill: {c}; }}\n" for k, c in enumerate(C["HM"]))
             + "    .num {{ font-variant-numeric: tabular-nums; }}\n"
             + "@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }\n"
             + "</style>")
    s.append(f'<rect x="{CARD_X}" y="0" width="{CARD_W}" height="{H}" rx="{R}" '
             f'fill="{C["bg"]}" stroke="{C["border"]}"/>')
    s.append(f'<rect x="{CARD_X}" y="0" width="{CARD_W}" height="{TB_H}" rx="{R}" '
             f'fill="{C["titlebar"]}" stroke="{C["border"]}"/>')
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        s.append(f'<circle cx="{24 + i * 18}" cy="19" r="5.5" fill="{c}"/>')
    s.append(f'<text x="86" y="25.2">'
             f'<tspan fill="{C["user"]}" font-weight="700">codefufuai@farrell-z</tspan>'
             f'<tspan fill="{C["muted"]}"> ~ % </tspan>'
             f'<tspan fill="{C["text"]}">{esc(T["cmd"])}</tspan></text>')
    s.append(f'<text x="{CARD_X + CARD_W - 20}" y="25.2" fill="{C["muted"]}" '
             f'text-anchor="end">{esc(T["cap"])}</text>')

    # month labels: column whose first day starts a new month, ≥3 cols apart
    last_m, last_lab_col = None, -9
    mon = (lambda m: f"{m} 月") if zh else (lambda m: date(2024, m, 1).strftime("%b"))
    for i in range(COLS):
        dd = start + timedelta(days=i * 7)
        if dd > today:
            break
        if dd.month != last_m and i - last_lab_col >= 3:
            s.append(f'<text x="{gx + i * PITCH}" y="{gy - 8}" font-size="8.5" '
                     f'fill="{C["faint"]}">{esc(mon(dd.month))}</text>')
            last_m, last_lab_col = dd.month, i
        elif dd.month != last_m:
            last_m = dd.month

    # birth marker: dashed blue line through the creation column
    if born_col is not None:
        bx = gx + born_col * PITCH - 2
        s.append(f'<line x1="{bx}" y1="{gy - 3}" x2="{bx}" y2="{gy + grid_h + 3}" '
                 f'stroke="{C["user"]}" stroke-dasharray="3 4" opacity="0.75"/>')

    # ---- the meal: plan + render (真吃：无食物则无蛇) ----
    plan = plan_snake_route(cells)
    route, eats, growth, pops = plan[:4] if plan else ([], [], [], [])
    n = len(route)
    total = n + PAUSE
    dur = total / SPS

    def pct(x):
        return round(x / total * 100, 3)

    css = []
    if n:
        # 占用模拟 → 每格被蛇身占据的时间区间（按 pops 重放真实蛇身，
        # 踩尾原步会让蛇身不再是 route 的连续切片，不能按切片偷懒）
        intervals, open_iv = {}, {}
        body, prev = deque(), set()
        swaps = []
        for st in range(n):
            if body and route[st] == body[0]:
                swaps.append(st)
            body.append(route[st])
            if pops[st]:
                body.popleft()
            cur = set(body)
            for cr in cur - prev:
                open_iv[cr] = st
            for cr in prev - cur:
                intervals.setdefault(cr, []).append((open_iv.pop(cr), st))
            prev = cur
        for cr, s0 in open_iv.items():
            intervals.setdefault(cr, []).append((s0, total))

        eaten_at = {cr: st for st, cr in eats}
        snk_head, snk_flash, snk_body = C["snake"]
        snk_old1, snk_old2 = C["snake_tail"]
        RAMP = ((1, snk_flash), (5, snk_body), (13, snk_old1), (26, snk_old2))
        bg_hex = C["bg"]

        def _ghost(c, k=0.45):
            return "#" + "".join(f"{round(int(c[i:i + 2], 16) * (1 - k) + int(bg_hex[i:i + 2], 16) * k):02x}"
                                 for i in (1, 3, 5))

        ramp_ghost = tuple((age, _ghost(col)) for age, col in RAMP)
        runs = []
        for st in swaps:
            if runs and st - runs[-1][1] <= 3:
                runs[-1][1] = st
            else:
                runs.append([st, st])
        windows = [(max(0, a - 4), min(n, b + 4)) for a, b in runs]

        def _in_escape(a, b):
            return any(a < wb and b > wa for wa, wb in windows)

        for cr, ivs in intervals.items():
            base = C["HM"][cells[cr]]
            cls = f"m{cr[0]}_{cr[1]}"
            stops = [(0.0, base)]
            swap_hits = [x for x in swaps if route[x] == cr]
            for a, b in ivs:
                post = C["HM"][0] if eaten_at.get(cr, n) <= b else base
                pa = pct(a)
                stops.append((max(pa - 0.05, 0.0), None))
                stops.append((pa, snk_head))
                ramp = ramp_ghost if _in_escape(a, b) else RAMP
                for age, col in ramp:
                    if a + age < b:
                        stops.append((pct(a + age), col))
                for x in [x for x in swap_hits if a <= x < b]:
                    ps = pct(x)
                    stops.append((max(ps - 0.05, 0.0), None))
                    stops.append((ps, snk_head))
                    ramp2 = ramp_ghost if _in_escape(x, x + 1) else RAMP
                    for age, col in ramp2:
                        if x + age < b:
                            stops.append((pct(x + age), col))
                if b < total:
                    pb = pct(b)
                    stops.append((max(pb - 0.05, 0.0), None))
                    stops.append((pb, post))
            frames, last = [], base
            for p, col in stops:
                if col is None:
                    frames.append(f"{p:.3f}% {{ fill:{last}; }}")
                else:
                    frames.append(f"{p:.3f}% {{ fill:{col}; }}")
                    last = col
            frames.append(f"100% {{ fill:{last}; }}")
            anims = f"k{cls} {dur:.1f}s linear infinite"
            if swap_hits:
                pts = [(0.0, "transparent")]
                for x in swap_hits:
                    pts.append((max(pct(x) - 0.10, 0.0), "transparent"))
                    pts.append((pct(x), f"{C['acc']}; stroke-width: 2"))
                    pts.append((min(pct(x) + 0.12, 99.99), "transparent"))
                kf = " ".join(f"{p:.3f}% {{ stroke: {c2}; }}" for p, c2 in pts)
                css.append(f"@keyframes s{cls} {{ {kf} }}")
                anims += f", s{cls} {dur:.1f}s linear infinite"
            css.append(f"@keyframes k{cls} {{ {' '.join(frames)} }}\n"
                       f".{cls} {{ animation: {anims}; }}")

        # "$ commits eaten" 前缀和沿新路由累计
        pre, run = [0], 0
        for st, cr in enumerate(route):
            if eaten_at.get(cr) == st:
                run += counts[cr]
            pre.append(run)
        seg_w = (grid_w - LBL_W - 12) / NC
        nc = min(NC, n)  # degenerate meals (n < NC) still get a clean relay
        for k in range(nc):
            i0, i1 = round(k * n / nc), round((k + 1) * n / nc)
            if i1 <= i0:
                continue
            a, b = pct(i0), pct(i1)
            if i1 >= n:
                frames = f"0% {{ opacity:0; }} {a:.3f}% {{ opacity:1; }} 100% {{ opacity:1; }}"
            else:
                frames = f"0% {{ opacity:0; }} {a:.3f}% {{ opacity:1; }} {b:.3f}%,100% {{ opacity:0; }}"
            css.append(f"@keyframes r{k} {{ {frames} }}\n"
                       f".r{k} {{ opacity:0; animation: r{k} {dur:.1f}s steps(1,end) infinite; }}")

    if freeze is not None:
        css.append(f"* {{ animation-play-state: paused !important; "
                   f"animation-delay: -{freeze:.2f}s !important; }}")
    if css:
        s.append(f"<style>{''.join(css)}</style>")

    # cells (base fill; animated class overrides when the snake passes)
    for (i, row), lev in sorted(cells.items()):
        cls = f"m{i}_{row}" if n and (i, row) in (intervals if n else {}) else f"h{lev}"
        s.append(f'<rect x="{gx + i * PITCH}" y="{gy + row * PITCH}" width="{CELL}" '
                 f'height="{CELL}" rx="2" class="{cls}" fill="{C["HM"][lev]}"/>')

    # birth label — extends toward whichever side has room
    if born_col is not None:
        bx = gx + born_col * PITCH - 2
        right_room = (CARD_X + CARD_W - 20) - bx > 130
        lx, anchor = (bx + 6, "start") if right_room else (bx - 6, "end")
        s.append(f'<text x="{lx}" y="{gy + grid_h + 14}" font-size="8.5" '
                 f'fill="{C["user"]}" text-anchor="{anchor}" opacity="0.8">{esc(T["born"])}</text>')

    # legend (bottom-right, GitHub style) + status (bottom-left)
    row2 = gy + grid_h + 32
    sw, ly = 8, row2 - 7
    more_x = gx + grid_w - 4
    sw_x_end = more_x - 34  # swatches end clear of the "More" label
    sw_x0 = sw_x_end - (5 * sw + 4 * 2)
    s.append(f'<text x="{sw_x0 - 8}" y="{row2}" font-size="10" fill="{C["faint"]}" '
             f'text-anchor="end">{esc(T["less"])}</text>')
    for k in range(5):
        s.append(f'<rect x="{sw_x0 + k * (sw + 2)}" y="{ly}" width="{sw}" height="{sw}" '
                 f'rx="1.5" class="h{k}"/>')
    s.append(f'<text x="{more_x}" y="{row2}" font-size="10" fill="{C["faint"]}" '
             f'text-anchor="end">{esc(T["more"])}</text>')
    s.append(f'<text x="{gx}" y="{row2}" font-size="10.5" fill="{C["muted"]}">'
             f'{esc(T["live_note"] if n else T["fast_note"])}</text>')

    # counter row: relay when eating, static 0 when fasting
    row3 = row2 + 22
    if n:
        s.append(f'<text x="{gx}" y="{row3}" font-size="9.5" font-weight="500" '
                 f'fill="{C["muted"]}">{esc(T["eaten_lbl"])}</text>')
        nc = min(NC, n)  # same segmentation as the relay keyframes
        for k in range(nc):
            i0, i1 = round(k * n / nc), round((k + 1) * n / nc)
            if i1 <= i0:
                continue
            s.append(f'<text class="r{k} num" x="{gx + LBL_W + 12 + k * seg_w:.0f}" y="{row3}" '
                     f'font-size="12" font-weight="600" fill="{C["text2"]}">{pre[i1]}</text>')
    else:
        s.append(f'<text x="{gx}" y="{row3}" font-size="9.5" font-weight="500" '
                 f'fill="{C["muted"]}">{esc(T["eaten_lbl"])}</text>')
        s.append(f'<text x="{gx + LBL_W + 12}" y="{row3}" font-size="12" font-weight="600" '
                 f'fill="{C["text2"]}">0</text>')

    s.append("</svg>")
    return "\n".join(s)


ASSETS = resolve_assets()


def main():
    global ASSETS
    ap = argparse.ArgumentParser()
    ap.add_argument("--calendar", type=Path, default=None,
                    help="contribs.json (GraphQL envelope or bare calendar)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--freeze", type=float, default=None, metavar="SECONDS")
    ap.add_argument("--sim", action="store_true",
                    help="render the SIMULATED calendar from preview/ (never shipped)")
    a = ap.parse_args()
    out = a.out_dir or ASSETS
    cal = None
    if a.sim:
        sim = ROOT / "preview" / "codefufuai" / "sim-contribs.json"
        cal = load_calendar(sim)
        if not a.out_dir:
            out = ROOT / "preview" / "codefufuai"
    elif a.calendar:
        cal = load_calendar(a.calendar)
    out.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        for zh in (False, True):
            name = f"snake-zh-{theme}.svg" if zh else f"snake-{theme}.svg"
            p = out / name
            p.write_text(build(theme, zh, a.freeze, cal))
            print(f"wrote {p} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
