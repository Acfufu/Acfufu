#!/usr/bin/env python3
"""Generate assets/profile{,-zh}-{dark,light}.svg — Acfufu's profile card.

Engine cloned from the dahan8473 replica (gen_dahan_replica.py): terminal-card
layout + CSS keyframes (pet idle frame animation, stepped fade-ins,
prefers-reduced-motion collapse) with the subsetted IBM Plex Mono embedded
when the build cache has it. Profile cards: pet (blossom HD sprite, base64
PNG frames from blossom_hd_frames.py — a shared SMIL timeline plays frames at the
pack's native durations while a beat sheet selects idle/waving/waiting; the slot is baked at
generation time from Asia/Shanghai hours — night swaps idle's own keyTimes
to hold the blink frame = asleep, zero extra bytes) and gh stats.

Card 2 (2026-11-04, `cat stack` icon grid retired): a GitHub stats card in
the token dashboard's compact-bar dialect — left column of reference-style
stat rows with Nerd Font icons baked to paths (PUA glyphs can't ride on
viewer fonts), right column of third-party repo bars (solid = merged PRs,
faded = upstream patch commits, top-4 with fold) and a commit-weighted
language stacked bar. Numbers are real GitHub data baked at generation time
(one graphql + three search calls, cached to data/gh-stats.json with a 6h
TTL; on total fetch failure a baked FALLBACK_STATS snapshot keeps the card
alive — external data degrades, never breaks). The public-only scope is the
privacy stance: private contributions surface solely as the aggregate
"+N in private" footnote, never per-repo or in the language mix.

The standalone wall card (assets/wall{,-zh}-{dark,light}.svg): titlebar +
`$ cat /var/log/wall` + the latest messages from data/wall.json — kept out
of the profile picture so the README can place it under the token
dashboard; the README's markdown link rows remain the clickable entry
points. zh variants localize captions and labels; terminal commands stay
English in both.

Retired in 2026-09/11: whoami, projects, git log sections, a links card
(reverted — it duplicated the README's markdown link rows) and the stack
card (language/tool/model icon grid — replaced by the gh stats card). The
git-log snake now lives in the token dashboard's TOKEN ACTIVITY heatmap
(token-stats.py). Glossary: CONTEXT.md.
"""
import getpass
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from card_motion import animate_card
from blossom_hd_frames import BOX, STATES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
# per-user cache：共享 /tmp 固定名会被其他本地账户投毒——字体 b64 会被整文件
# 内嵌进公开 SVG（等于本地任意文件读外泄原语），图标 path 则可被注入涂改
CACHE = Path(tempfile.gettempdir()) / f"dahan-replica-cache-{getpass.getuser()}"
REPO_CACHE = ROOT / "assets" / "gen-cache"  # vendored copy so CI never needs the network

W = 960
H = 564  # card 1 back to 212 tall (codefufuai-whoami aligned): ground sprite 144x144 fills its slot
CARD_X, CARD_W, R = 4, 952, 12
TB_H = 38

DARK = {
    "card": "#0a0e14", "titlebar": "#111826", "border": "#22406a",
    "title": "#e6edf3", "user": "#58a6ff", "desc": "#c9d1d9",
    "ok": "#a5d6ff", "liv": "#f0d861", "green": "#3fa060",
    # token-dashboard dialect shades (token-stats.py PAL)
    "muted": "#6e7f95", "faint": "#57606a", "track": "#161b22",
}
LIGHT = dict(DARK, card="#ffffff", titlebar="#f6f8fa", border="#a9c4e4",
             title="#1f2328", user="#0969da", desc="#424a53",
             ok="#0a5cc2", liv="#9a6700", green="#1a7f37",
             muted="#8c9bb0", faint="#8c959f", track="#ebedf0")

MONO = "'Plex',ui-monospace,'SF Mono',Menlo,Consolas,monospace"

# ---- gh stats card (card 2) constants -------------------------------------
# Nerd Font glyphs baked to paths by nerd_glyphs.py (design round): PUA code
# points can't ride on viewer fonts inside SVG-as-<img>, so the outlines come
# from the local JetBrainsMono NL Nerd Font and are vendored here — same
# pipeline as the retired simple-icons marks. Codicon shapes are Microsoft
# CC-BY-4.0; octicons MIT; JetBrains Mono NF OFL.
NF_FILE = REPO_CACHE / "nerdfont_glyphs.json"
NF = json.loads(NF_FILE.read_text())
NF_S = 13.5 / NF["upem"]  # px per font unit: icons sit like a 13.5px character

# one hue per third-party repo (reference-card confetti); languages use the
# official linguist colors
REPO_PAL = ["#58a6ff", "#f0883e", "#3fb950", "#bc8cff", "#f85149", "#39c5cf", "#db61a2"]
LINGUIST = {"JavaScript": "#f1e05a", "Python": "#3572A5", "Swift": "#F05138",
            "Rust": "#dea584", "Go": "#00ADD8", "Shell": "#89e051",
            "TypeScript": "#3178c6", "C#": "#178600", "C++": "#f34b7d"}

# stats source: one graphql (contributions + per-repo breakdown) + three
# search calls, cached with a TTL — the daemon rebakes on slot flips and the
# search API is rate-limited. CI's Actions token sees public data only,
# which IS the card's privacy stance; restricted (private) contributions
# surface solely as the aggregate footnote, never per-repo / per-language.
GH_USER = "Acfufu"
GH_STATS_CACHE = ROOT / "data" / "gh-stats.json"
GH_TTL = 6 * 3600

# baked 2026-11-04 snapshot — last resort when every fetch path fails, so
# the card degrades to slightly stale numbers instead of breaking the
# wall.yml pipeline (same contract as load_tier's calm fallback)
FALLBACK_STATS = {
    "followers": 52, "repos": 42, "stars": 2,
    "commits": 2164, "priv": 2205, "total": 4535,
    "merged_all": 47, "merged_30": 43, "issues_all": 42,
    "upstream": 32, "contributed": 2, "merged_tp": 31,
    "tp": [("xiufengsun/TokenTracker", {"prs": 30, "patches": 32}),
           ("openchamber/openchamber", {"prs": 1, "patches": 0})],
    "langs": [("JavaScript", 48.6137), ("Python", 31.7006), ("Swift", 7.4861),
              ("Rust", 6.4695), ("Go", 5.4991), ("Other", 0.2311)],
}

PET = {
    "name": "blossom",
    "url": "~/.codex/pets/fufu-blossom",
    "owner": "acfufu",
    "states": 9,
    "frames": 57,
    "tags": "blossom / pixel / soft / mascot",
}

# pet macro-loop — one clock. The beat sheet plays each state at the pack's
# native frame durations, restarting each segment at its first frame. The slot
# is BAKED at generation from Asia/Shanghai hours — fixed +08:00 offset, no
# DST, and NEVER runner-local time (wall.yml CI runs in UTC). The intensity
# tier comes from data/mood.json (written by the token-stats daemon from
# yesterday's tokens vs their 30-day median); missing/stale/invalid falls
# back to calm — the schedule degrades, never breaks.
CST = timezone(timedelta(hours=8))
SLEEP_MS = [600, 150, 150, 4000, 150, 800]  # night: idle's blink frame held = asleep
MOOD_FILE = ROOT / "data" / "mood.json"
TIERS = ("hot", "calm", "quiet")

# beat sheets per (slot, tier); (state, native loops). jumping is NOT cast:
# its atlas apex reaches y=3 and would force a 200px slot with a permanent
# 56px void over the idle pet (see blossom_hd_frames) — the tight
# codefufuai-style card won. failed is the quiet-evening easter egg.
BEAT = {
    "morning": {
        "hot":   [("idle", 1), ("waving", 1), ("idle", 2), ("waving", 1),
                  ("idle", 3), ("waving", 1), ("idle", 3)],
        "calm":  [("idle", 2), ("waving", 1), ("idle", 2), ("waving", 1),
                  ("idle", 3), ("waving", 1), ("idle", 4)],
        "quiet": [("idle", 3), ("waving", 1), ("idle", 4), ("waving", 1), ("idle", 5)],
    },
    "day": {
        "hot":   [("idle", 2), ("waving", 1), ("idle", 2), ("waiting", 1),
                  ("idle", 2), ("waving", 1), ("idle", 3), ("waiting", 1), ("idle", 3)],
        "calm":  [("idle", 3), ("waving", 1), ("idle", 3), ("waiting", 1),
                  ("idle", 4), ("waving", 1), ("idle", 5)],
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
    ("morning", "hot"): ("mood: playful · now: chirpy good-mornings",
                         "心情：playful · 此刻：元气满满道早安"),
    ("morning", "calm"): ("mood: idle · now: morning greetings among the blossoms",
                          "心情：idle · 此刻：在花间道早安"),
    ("morning", "quiet"): ("mood: idle · now: a slow sleepy hello",
                           "心情：idle · 此刻：懒洋洋地说早安"),
    ("day", "hot"): ("mood: playful · now: frolicking in the flower field",
                     "心情：playful · 此刻：在花田里撒欢"),
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

# UI strings per language; terminal commands (pets status blossom, gh
# stats, cat /var/log/wall) stay English in both. SVG links are not
# clickable — the README markdown rows carry the functional hrefs.
STR = {
    "en": dict(
        aria="acfufu terminal profile card",
        pet_desc="tiny mint-haired blossom (fufu mint style)",
        pet_meta=f"custom codex pet · owner: {PET['owner']} · codex v1 atlas",
        pet_states=f"{PET['states']} states · {PET['frames']} frames · tags: {PET['tags']}",
        pet_mood="mood: idle · now: tending the blossoms",
        pet_open="> installed at: ",
        stats_cap="rest v3 + graphql · search api",
        stats_header="@acfufu · {followers} followers · {repos} repos · baked {baked}",
        stats_rows=[("prs", "Merged Pull Requests", "merged_all"),
                    ("calendar", "Merged PRs (30 days)", "merged_30"),
                    ("feather", "Upstream Patch Commits", "upstream"),
                    ("history", "Total Contributions (last year)", "total"),
                    ("commit", "Total Commits (last year)", "commits"),
                    ("repo", "Contributed to (last year)", "contributed"),
                    ("issue", "Issues Opened", "issues_all"),
                    ("star", "Total Stars Earned", "stars")],
        tp_hdr="{n} merged in {m} third-party repos",
        tp_label="THIRD-PARTY",
        cap_tp="{tot} total · {n} repos",
        tp_foot="faded = upstream patch commits · {detail}",
        tp_foot_fold="faded = patch commits · +{k} more repos · {m} merged",
        lg_label="LANGUAGES · BY COMMITS",
        cap_lg="{commits} commits · public",
        lg_more="+{k} langs",
        lg_foot="primary language per repo · weighted by commits · public only",
        priv_foot="+{priv} commits in private repos · not in per-repo stats",
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
        stats_cap="rest v3 + graphql · search api",
        stats_header="@acfufu · {followers} 关注者 · {repos} 仓库 · 烤于 {baked}",
        stats_rows=[("prs", "合并 Pull Request", "merged_all"),
                    ("calendar", "近 30 天合并", "merged_30"),
                    ("feather", "上游补丁提交", "upstream"),
                    ("history", "总贡献（近一年）", "total"),
                    ("commit", "总提交（近一年）", "commits"),
                    ("repo", "参与仓库（近一年）", "contributed"),
                    ("issue", "发起议题", "issues_all"),
                    ("star", "累计获星", "stars")],
        tp_hdr="{n} 次合并 · {m} 个三方仓库",
        tp_label="三方仓库",
        cap_tp="{tot} 合计 · {n} 个仓库",
        tp_foot="淡段 = 上游补丁提交 · {detail}",
        tp_foot_fold="淡段 = 补丁提交 · 另折叠 {k} 仓 · {m} 次合并",
        lg_label="提交语言",
        cap_lg="{commits} 次提交 · 公开",
        lg_more="其余 {k} 种",
        lg_foot="按仓库主语言 · 以提交数加权 · 仅公开提交",
        priv_foot="私库另有 {priv} 次提交 · 未计入分仓统计",
        wall_aria="acfufu 留言墙",
        wall_cap="留一句话",
        wall_hint="[wall] 打开预填 issue，留言会落到这里",
    ),
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(n):
    return f"{n:,}"


def _gh_token():
    """Actions 注入 GH_TOKEN；本地 daemon 走 gh cli 的凭据。都拿不到返回
    None —— load_gh_stats 据此直接走兜底快照，不打无凭据的 API。"""
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _gh_api(path=None, query=None):
    tok = _gh_token()
    hdr = {"User-Agent": "card-builder"}
    if tok:
        hdr["Authorization"] = f"Bearer {tok}"
    if query:  # graphql POST
        req = urllib.request.Request("https://api.github.com/graphql",
                                     data=json.dumps({"query": query}).encode(),
                                     headers=dict(hdr, **{"Content-Type": "application/json"}))
    else:  # REST GET
        req = urllib.request.Request(f"https://api.github.com/{path}", headers=hdr)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def fetch_gh_stats():
    """Real GitHub numbers, public scope: one graphql (followed repos,
    contributions, per-repo commit breakdown) + three search calls (merged
    PRs all-time / last 30 days + per-repo grouping, issues). 429/网络异常
    向上抛，由 load_gh_stats 落到旧缓存或兜底快照。"""
    q = (
        "query { user(login: \"%s\") { followers { totalCount } "
        "repositories(first: 100, ownerAffiliations: OWNER, isFork: false) { "
        "totalCount nodes { stargazerCount } } "
        "contributionsCollection { totalCommitContributions restrictedContributionsCount "
        "contributionCalendar { totalContributions } "
        "commitContributionsByRepository { contributions { totalCount } "
        "repository { nameWithOwner owner { login } primaryLanguage { name } } } } } "
        "}" % GH_USER)
    assert q.count("{") == q.count("}"), "graphql brace imbalance"
    u = _gh_api(query=q)["data"]["user"]
    since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    merged = _gh_api("search/issues?q=author:%s+type:pr+is:merged&per_page=1" % GH_USER)
    merged30 = _gh_api("search/issues?q=author:%s+type:pr+is:merged+merged:%%3E=%s&per_page=1"
                       % (GH_USER, since))
    issues = _gh_api("search/issues?q=author:%s+type:issue&per_page=1" % GH_USER)
    pr_items = _gh_api("search/issues?q=author:%s+type:pr+is:merged&per_page=100" % GH_USER)
    return {
        "followers": u["followers"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "stars": sum(n["stargazerCount"] for n in u["repositories"]["nodes"]),
        "commits": u["contributionsCollection"]["totalCommitContributions"],
        "priv": u["contributionsCollection"]["restrictedContributionsCount"],
        "total": u["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "byrepo": [(r["repository"]["nameWithOwner"], r["repository"]["owner"]["login"],
                    r["repository"]["primaryLanguage"]["name"] if r["repository"]["primaryLanguage"] else None,
                    r["contributions"]["totalCount"])
                   for r in u["contributionsCollection"]["commitContributionsByRepository"]],
        "merged_all": merged["total_count"],
        "merged_30": merged30["total_count"],
        "issues_all": issues["total_count"],
        "merged_pr_urls": [it["repository_url"] for it in pr_items.get("items", [])],
    }


def normalize_gh_stats(raw):
    """Raw payload → card numbers: third-party union (merged-PR repos ∪
    patch-commit repos), commit-weighted primary-language mix, aggregate
    counts. Private own repos never enter tp/langs — the graphql only
    attributes public contributions per-repo, and that IS the stance."""
    lang_w = {}
    tp_commits = {}
    upstream = 0
    for name, owner, lang, n in raw["byrepo"]:
        if owner != GH_USER:
            upstream += n
            tp_commits[name] = tp_commits.get(name, 0) + n
        if lang and n:
            lang_w[lang] = lang_w.get(lang, 0) + n
    merged_by_repo = {}
    for url in raw["merged_pr_urls"]:
        name = "/".join(url.rsplit("/", 2)[-2:])
        if not name.startswith(f"{GH_USER}/"):
            merged_by_repo[name] = merged_by_repo.get(name, 0) + 1
    tp = {name: {"prs": merged_by_repo.get(name, 0), "patches": tp_commits.get(name, 0)}
          for name in set(tp_commits) | set(merged_by_repo)}
    tot = sum(lang_w.values()) or 1
    langs = sorted(lang_w.items(), key=lambda kv: -kv[1])
    if len(langs) > 5:  # 折叠小语种：卡面只留头部 5 + Other（与仪表盘长尾同法）
        rest = sum(v for _, v in langs[5:])
        langs = langs[:5] + [("Other", rest)]
    return {
        "followers": raw["followers"], "repos": raw["repos"], "stars": raw["stars"],
        "commits": raw["commits"], "priv": raw["priv"], "total": raw["total"],
        "merged_all": raw["merged_all"], "merged_30": raw["merged_30"],
        "issues_all": raw["issues_all"],
        "upstream": upstream, "contributed": len(tp),
        "merged_tp": sum(v["prs"] for v in tp.values()),
        "tp": sorted(tp.items(), key=lambda kv: -(kv[1]["prs"] + kv[1]["patches"])),
        "langs": [(name, v / tot * 100) for name, v in langs],
    }


def load_gh_stats():
    """新鲜缓存 → 直读；过期 → 重取并写回；取数失败 → 旧缓存兜底；
    连缓存都没有 → 内置快照。外部数据只降级新鲜度，不弄坏卡片。"""
    cache = GH_STATS_CACHE
    if cache.exists() and time.time() - cache.stat().st_mtime < GH_TTL:
        try:
            return json.loads(cache.read_text())
        except Exception as e:
            print(f"[warn] {cache}: {e}", file=sys.stderr)
    try:
        st = normalize_gh_stats(fetch_gh_stats())
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(st, ensure_ascii=False))
        return st
    except Exception as e:
        print(f"[warn] gh stats fetch failed ({e}); falling back", file=sys.stderr)
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:
            pass
    return FALLBACK_STATS


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


def pet_timeline(slot, tier):
    """Build one repeating timeline, restarting each state at its first frame."""
    sheet = BEAT[slot][tier] if slot in BEAT else [("idle", 1)]
    timeline = []
    for state, loops in sheet:
        ms = SLEEP_MS if slot == "night" else STATES[state][0]
        for _ in range(loops):
            timeline.extend((state, frame, duration) for frame, duration in enumerate(ms))
    return timeline


def pet_scene(x, y, slot, tier, freeze=None):
    """Display exactly one sprite frame using a shared macro-cycle clock.

    A second, static image is used when reduced motion is requested. The freeze
    option shifts the shared clock to the middle of a requested frame for
    screenshot forensics; it does not alter the animation's normal timeline.
    """
    timeline = pet_timeline(slot, tier)
    total = sum(duration for _, _, duration in timeline)
    begin = ""
    if freeze:
        elapsed = 0
        for state, frame, duration in timeline:
            if (state, frame) == freeze:
                begin = f' begin="{-((elapsed + duration / 2) / 1000):.3f}s"'
                break
            elapsed += duration
        else:
            raise ValueError(f"frame {freeze!r} is not present in this timeline")

    # Each sprite is present only once. Every opacity animation uses the same
    # clock and boundary list, so no underlying frame can show through.
    boundaries = []
    elapsed = 0
    for state, frame, duration in timeline:
        boundaries.append((elapsed, state, frame))
        elapsed += duration
    frames = dict.fromkeys((state, frame) for _, state, frame in boundaries)
    out = [f'<g transform="translate({x},{y})"><g class="pet-animated">']
    for state, frame in frames:
        changes = []
        previous = None
        for start, current_state, current_frame in boundaries:
            visible = int((state, frame) == (current_state, current_frame))
            if visible != previous:
                changes.append((start, visible))
                previous = visible
        times = ";".join(f"{start / total:.8f}" for start, _ in changes)
        values = ";".join(str(visible) for _, visible in changes)
        png = STATES[state][1][frame]
        out.append(f'<image opacity="{changes[0][1]}" width="{BOX[0]}" height="{BOX[1]}" '
                   f'href="data:image/png;base64,{png}">'
                   f'<animate attributeName="opacity" calcMode="discrete" '
                   f'values="{values}" keyTimes="{times}" dur="{total}ms" '
                   f'repeatCount="indefinite"{begin}/></image>')
    static_frame = 3 if slot == "night" else 0
    png = STATES["idle"][1][static_frame]
    out.append(f'</g><image class="pet-static" width="{BOX[0]}" height="{BOX[1]}" '
               f'href="data:image/png;base64,{png}"/></g>')
    return "".join(out)


def build_css():
    # gh-stats dialect classes: appended after the base rules on purpose —
    # build_css's `text { font-size:15px }` element rule BEATS presentation
    # attributes, so every non-15px text on the stats card must carry a
    # class (same-specificity later-declared rule wins the cascade).
    return f"""
    text {{ font-family:{MONO}; font-size:15px; }}
    .ok   {{ fill:{C["ok"]}; font-size:13.5px; opacity:0; animation:on .01s steps(1) forwards; }}
    .liv  {{ fill:{C["liv"]}; font-size:13.5px; }}
    .stlab{{ font-size:12px; fill:#6e7f95; }}
    .agst {{ font-size:12px; fill:#6e7f95; }}
    .snlab{{ font-size:9.5px; fill:{C["green"]}; }}
    .wcat {{ font-size:14px; fill:{C["user"]}; }}
    .wmsg {{ font-size:14px; fill:{C["desc"]}; }}
    .shdr  {{ font-size:12.5px; fill:{C["desc"]}; }}
    .slab2 {{ font-size:11px; fill:{C["muted"]}; font-weight:600; letter-spacing:2; }}
    .scap  {{ font-size:10.5px; fill:{C["faint"]}; }}
    .hname {{ font-size:12.5px; fill:{C["title"]}; font-weight:600; }}
    .hval  {{ font-size:12px; fill:{C["muted"]}; }}
    .sfoot {{ font-size:10.5px; fill:{C["muted"]}; }}
    .lgn   {{ font-size:12px; fill:{C["desc"]}; font-weight:500; }}
    .bval  {{ font-size:15px; fill:{C["title"]}; font-weight:700; }}
    .rv    {{ opacity:0; animation:on .01s steps(1) forwards; }}
    .hbar  {{ transform-box:fill-box; transform-origin:left center; animation:growx .45s ease-out backwards; }}
    @keyframes on    {{ to {{ opacity:1; }} }}
    @keyframes growx {{ from {{ transform:scaleX(0); }} }}
    .pet-static {{ display:none; }}
    @media (prefers-reduced-motion: reduce) {{
      .pet-animated {{ display:none; }}
      .pet-static {{ display:inline; }}
      * {{ animation: none !important; }}
      .ok, .rv {{ opacity:1; }}
      .hbar {{ animation:none; }}
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

    # ---- card 1: pet (y=2, h=212 — same geometry as codefufuai's whoami card;
    #      ground sprite 144x144 content fills the slot, head ~16px under the titlebar) ----
    y1, h1 = 2, 212
    card_rect(s, y1, h1)
    titlebar(s, y1, "pets status blossom", PET["url"])
    s.append(pet_scene(20, y1 + TB_H + 16, slot, tier, freeze))
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
    ty0 = y1 + TB_H + 24
    for i, (cls, body) in enumerate(lines):
        s.append(f'<text class="{cls}" x="{tx}" y="{ty0 + i * 20}">{body}</text>')
    s.append(f'<text x="{tx}" y="{ty0 + len(lines) * 20 + 4}" font-size="12.5" fill="{C["user"]}">'
             f'{esc(T["pet_open"])}{PET["url"]}</text>')

    # ---- card 2: gh stats (y=230, h=332) — token dashboard's compact-bar
    #      dialect: 10px rx3 seamless segments, section labels 11px/600/
    #      muted/ls2 with faint right captions, dot legends in measured flow,
    #      10.5px muted footnotes. Numbers baked from load_gh_stats(). ----
    y2, h2 = 230, 332
    card_rect(s, y2, h2)
    titlebar(s, y2, "gh stats", T["stats_cap"])
    ST = load_gh_stats()
    baked = datetime.now(CST).strftime("%H:%M")
    RX, PAD2, RIGHT = 478, 20, 940
    s.append(f'<text class="liv" x="{PAD2}" y="{y2 + 62}" style="animation-delay:.05s">'
             f'[LIVE] <tspan fill="{C["title"]}" font-weight="700">'
             f'{T["stats_header"].format(followers=ST["followers"], repos=ST["repos"], baked=baked)}'
             f'</tspan></text>')

    # ---- left column: reference stat rows (nf icon · label · bold value) ----
    for i, (ico, lab, key) in enumerate(T["stats_rows"]):
        ry = y2 + 90 + i * 26
        dly = f"animation-delay:{.15 + i * .06:.2f}s"
        gph = NF["glyphs"][ico]
        s.append(f'<g class="ok" style="{dly}">'
                 f'<g transform="translate({PAD2},{ry}) scale({NF_S:.5f},-{NF_S:.5f})">'
                 f'<path d="{gph["d"]}" fill="{C["user"]}"/></g>'
                 f'<text x="42" y="{ry}" fill="{C["desc"]}">{esc(lab)}</text></g>')
        s.append(f'<text class="rv bval" x="430" y="{ry}" text-anchor="end" style="{dly}">'
                 f'{fmt(ST[key])}</text>')
    priv = T["priv_foot"].format(priv=fmt(ST["priv"]))
    s.append(f'<text class="rv sfoot" x="{PAD2}" y="{y2 + 306}" style="animation-delay:.7s">'
             f'<tspan fill="{C["green"]}" font-weight="600">[ OK ]</tspan> {esc(priv)}</text>')

    # ---- vertical divider + right column ----
    s.append(f'<line x1="450" y1="{y2 + 56}" x2="450" y2="{y2 + 316}" '
             f'stroke="{C["border"]}" stroke-width="1" opacity="0.6"/>')
    s.append(f'<text class="shdr" x="{RX}" y="{y2 + 62}" style="animation-delay:.3s">'
             f'{esc(T["tp_hdr"].format(n=ST["merged_tp"], m=len(ST["tp"])))}</text>')

    def flow_legend(x, y, w, items, delay0=1.3):
        """dashboard _legend_svg dialect: r4.5 dots + 12px w500 names + muted
        pct, measured flow (iw = 12 + len*7.2 + 7.2 + len(pct)*7.2, item gap
        34, 20px rows)."""
        ly = y
        line, rows, end_x = [], [], 0
        for name, pct, color in items:
            s_pct = "" if pct is None else f"{pct:.1f}%"
            iw = 12 + len(name) * 7.2 + ((7.2 + len(s_pct) * 7.2) if s_pct else 0)
            px = end_x + 34 if line else 0
            if line and px + iw > w:
                rows.append(line)
                line, px = [], 0
            line.append((px, name, s_pct, color))
            end_x = px + iw
        if line:
            rows.append(line)
        for ln in rows:
            for px, name, s_pct, color in ln:
                s.append(f'<circle cx="{x + px + 4.5:.1f}" cy="{ly - 4:.1f}" r="4.5" '
                         f'fill="{color}" style="animation-delay:{delay0:.2f}s" class="rv"/>')
                tail = f'<tspan fill="{C["muted"]}"> {s_pct}</tspan>' if s_pct else ""
                s.append(f'<text class="rv lgn" x="{x + px + 14:.1f}" y="{ly}" '
                         f'style="animation-delay:{delay0 + .05:.2f}s">'
                         f'{esc(name)}{tail}</text>')
            ly += 20

    # growth policy: top-4 repos as bars (24px rows), the rest fold into the
    # footnote aggregate (dashboard's BY TOOL fold precedent); the languages
    # zone is bottom-anchored (foot at y2+306) and compresses to one legend
    # row once 3+ bars push it down — layout verified for 1..4 shown repos
    TP_MAX, STEP = 4, 24
    shown, fold = ST["tp"][:TP_MAX], ST["tp"][TP_MAX:]
    bar_x0, bar_x1 = RX + 118, RIGHT
    maxv = max((v["prs"] + v["patches"] for _, v in shown), default=1)
    s.append(f'<text class="slab2" x="{RX}" y="{y2 + 84}" style="animation-delay:.35s">'
             f'{esc(T["tp_label"])}</text>')
    s.append(f'<text class="scap" x="{RIGHT}" y="{y2 + 84}" text-anchor="end" '
             f'style="animation-delay:.35s">'
             f'{esc(T["cap_tp"].format(tot=fmt(ST["upstream"] + ST["merged_tp"]), n=len(ST["tp"])))}</text>')
    for i, (name, v) in enumerate(shown):
        by = y2 + 96 + i * STEP
        color = REPO_PAL[i % len(REPO_PAL)]
        w_pr = (v["prs"] / maxv) * (bar_x1 - bar_x0)
        w_pa = (v["patches"] / maxv) * (bar_x1 - bar_x0)
        s.append(f'<text class="rv hname" x="{RX}" y="{by + 9.8}" '
                 f'style="animation-delay:{.4 + i * .08:.2f}s">{esc(name.split("/")[1])}</text>')
        s.append(f'<rect x="{bar_x0}" y="{by}" width="{bar_x1 - bar_x0}" height="10" rx="3" '
                 f'fill="{C["track"]}"/>')
        if w_pr > 0:
            s.append(f'<rect class="hbar" x="{bar_x0}" y="{by}" width="{w_pr:.1f}" height="10" rx="3" '
                     f'fill="{color}" style="animation-delay:{.45 + i * .08:.2f}s"/>')
        if w_pa > 0:
            s.append(f'<rect class="hbar" x="{bar_x0 + w_pr:.1f}" y="{by}" width="{w_pa:.1f}" '
                     f'height="10" rx="3" fill="{color}" opacity="0.28" '
                     f'style="animation-delay:{.55 + i * .08:.2f}s"/>')
        s.append(f'<text class="rv hval" x="{RIGHT}" y="{by + 9.5}" text-anchor="end" '
                 f'style="animation-delay:{.5 + i * .08:.2f}s">{v["prs"] + v["patches"]}</text>')
    foot_y = y2 + 96 + (len(shown) - 1) * STEP + 24
    if fold:
        foot = T["tp_foot_fold"].format(k=len(fold),
                                        m=sum(v["prs"] for _, v in fold))
    else:
        detail = " · ".join(f"{name.split('/')[1]} {v['patches']}"
                            for name, v in shown if v["patches"])
        foot = T["tp_foot"].format(detail=detail)
    s.append(f'<text class="rv sfoot" x="{RX}" y="{foot_y}" '
             f'style="animation-delay:.8s">{esc(foot)}</text>')

    # ---- languages: single stacked bar + dot legend, bottom-anchored ----
    comp = len(shown) >= 3
    div_y = y2 + 306 - (56 if comp else 76) - 16
    s.append(f'<line x1="{RX}" y1="{div_y}" x2="{RIGHT}" y2="{div_y}" '
             f'stroke="{C["track"]}" stroke-width="1"/>')
    lg_y = div_y + 16
    s.append(f'<text class="slab2" x="{RX}" y="{lg_y}" style="animation-delay:.9s">'
             f'{esc(T["lg_label"])}</text>')
    s.append(f'<text class="scap" x="{RIGHT}" y="{lg_y}" text-anchor="end" '
             f'style="animation-delay:.9s">{esc(T["cap_lg"].format(commits=fmt(ST["commits"])))}</text>')
    s.append(f'<defs><clipPath id="lgbar{theme}"><rect x="{RX}" y="{lg_y + 10}" '
             f'width="{RIGHT - RX}" height="10" rx="3"/></clipPath></defs><g clip-path="url(#lgbar{theme})">')
    cx = RX
    for i, (name, pct) in enumerate(ST["langs"]):
        w = (pct / 100) * (RIGHT - RX)
        w = max(w, 2) if i < len(ST["langs"]) - 1 else (RIGHT - cx)
        s.append(f'<rect class="hbar" x="{cx:.1f}" y="{lg_y + 10}" width="{max(w, 0.5):.1f}" '
                 f'height="10" fill="{LINGUIST.get(name, C["muted"])}" '
                 f'style="animation-delay:{1 + i * .08:.2f}s"/>')
        cx += w
    s.append('</g>')
    items = [(n, p, LINGUIST.get(n, C["muted"])) for n, p in ST["langs"]]
    if comp and len(items) > 3:
        rest = items[3:]
        items = items[:3] + [(T["lg_more"].format(k=len(rest)),
                              sum(p for _, p, _ in rest), C["muted"])]
    flow_legend(RX, lg_y + 40, RIGHT - RX, items)
    s.append(f'<text class="rv sfoot" x="{RX}" y="{y2 + 306}" style="animation-delay:1.6s">'
             f'{esc(T["lg_foot"])}</text>')
    s.append(f'<rect class="cur" x="928.5" y="{y2 + 313}" width="7.5" height="14" '
             f'fill="{C["green"]}"/>')

    s.append("</svg>")
    return animate_card("\n".join(s), "profile", theme)


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
    return animate_card("\n".join(s), "wall", theme)


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
    if freeze and freeze[0] != "idle":
        cast = {s for s, _ in BEAT[slot][tier]} if slot in BEAT else set()
        if freeze[0] not in cast:
            ap.error(f"--freeze {freeze[0]} is not cast by the {slot}/{tier} beat sheet")
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
