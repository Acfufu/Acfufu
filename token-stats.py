#!/usr/bin/env python3
# noqa: SIZE_OK — 自包含单文件 CLI 脚本（零依赖设计），刻意不分拆
"""
token-stats.py: 生成 GitHub profile 的 AI token usage SVG 卡片 + 自包含定时同步

数据源（双层匹配 + LiteLLM 当前定价）：
  1. 主层 tracker: ~/.tokentracker/tracker/queue.jsonl（TokenTracker 逐小时记录）
     - 数据源超集: codex / claude / opencode / gemini / workbuddy / zcode
     - 逐条含 input / cached / cache_creation / output / reasoning tokens + conversation_count
     - 缓存占比、输入输出拆分等统计直接由此计算
  2. 回退层 ccusage: 本机 CLI 会话聚合（tracker 文件缺失时使用）

成本：按 LiteLLM model_prices_and_context_window.json 当前定价逐条计算
  - 优先联网拉取最新定价；离线/失败回退 ~/.tokentracker/cache/pricing.json（缓存）
  - LiteLLM 未收录的国产/特殊模型用本地估算价（LOCAL_PRICING）

用法:
  python3 token-stats.py                # 立即同步 GitHub + 启动后台守护（默认每 24h 自动同步）
  python3 token-stats.py --once         # 只同步一次，不启动守护
  python3 token-stats.py --once --no-sync  # 只生成 SVG，不提交/推送（本地预览）
  python3 token-stats.py --stop         # 停止后台守护
  python3 token-stats.py --json         # 输出聚合 JSON
  python3 token-stats.py --interval 6   # 自定义守护间隔（小时）

守护特性（零系统级痕迹）：
  - 不注册 crontab / launchd；重启后自动停，不留任何系统文件
  - PID/日志在仓库内（.token-stats-daemon.pid / .token-stats-daemon.log），删仓库即全部消失
  - 单实例互斥：fcntl.flock 内核级锁，并发启动也只会有一个守护（无 TOCTOU 竞态）
  - 每 60s 自检仓库是否还在；删仓库 → 1 分钟内自行退出

依赖: 无第三方 Python 包（联网定价失败自动用缓存）
"""

import argparse
import datetime
import fcntl
import html
import json
import math
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.request

# ============ 配置 ============
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PRICING_CACHE = os.path.expanduser("~/.tokentracker/cache/pricing.json")  # LiteLLM 定价缓存
TRACKER_QUEUE = os.path.expanduser("~/.tokentracker/tracker/queue.jsonl")  # TokenTracker 记录
SESSION_QUEUE = os.path.expanduser("~/.tokentracker/tracker/session.queue.jsonl")  # 会话元数据（会话效率）
OUTCOMES_FILE = os.path.expanduser("~/.tokentracker/tracker/auto-outcomes.jsonl")  # 交付结果（性价比）
OUT_DEFAULT = "token-stats.svg"

# 本地兜底定价 $/M tokens（LiteLLM 未收录：国产/特殊模型，估算）
LOCAL_PRICING = {
    "minimax-m2.7": (0.30, 1.20, 0.03, 0.0),
    "minimax-m3":   (1.00, 4.00, 0.10, 0.0),
    "hy3":          (0.50, 1.50, 0.05, 0.0),
    "qwen3.7-plus": (0.60, 2.40, 0.06, 0.0),
    "auto":         (0.0, 0.0, 0.0, 0.0),
    "unknown":      (0.0, 0.0, 0.0, 0.0),
}

# 本机模型 → 官方命名映射（显示名）
MODEL_NAMES = {
    "gpt-5.6-sol": "GPT-5.6 Sol", "gpt-5.6-luna": "GPT-5.6 Luna",
    "gpt-5.6-terra": "GPT-5.6 Terra", "gpt-5.6": "GPT-5.6",
    "gpt-5.5": "GPT-5.5", "gpt-5.4": "GPT-5.4", "gpt-5.4-mini": "GPT-5.4 Mini",
    "gpt-5.3-codex-spark": "GPT-5.3 Codex Spark", "gpt-5": "GPT-5",
    "codex-auto-review": "Codex Auto Review",
    "deepseek-v4-flash": "DeepSeek V4 Flash", "deepseek-v4-pro": "DeepSeek V4 Pro",
    "MiniMax-M2.7": "MiniMax M2.7", "minimax-m2.7": "MiniMax M2.7",
    "minimax-m3": "MiniMax M3", "MiniMax-M3": "MiniMax M3",
    "claude-opus-4-7": "Claude Opus 4.7", "claude-opus-4-6": "Claude Opus 4.6",
    "claude-opus-4-5": "Claude Opus 4.5", "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-sonnet-4-5": "Claude Sonnet 4.5",
    "glm-5.2": "GLM-5.2", "GLM-5.2": "GLM-5.2", "glm-5.1": "GLM-5.1",
    "glm-5.2-x": "GLM-5.2 X", "GLM-5-Turbo": "GLM-5 Turbo",
    "kimi-k2.6": "Kimi K2.6", "mimo-v2.5": "MiMo V2.5",
    "gemini-3-flash-preview": "Gemini 3 Flash", "hy3": "Hunyuan Hy3",
    "qwen3.7-plus": "Qwen3.7 Plus",
}

AGENT_COLORS = {
    "codex": "#6c63ff", "claude": "#51cf66", "opencode": "#22b8cf",
    "gemini": "#4285F4", "other": "#8b949e",
}


# ============ 定价 ============
def get_pricing():
    """LiteLLM 定价索引。联网拉最新 → 失败用缓存文件；返回 {模型段: 定价条目}"""
    data = None
    try:
        with urllib.request.urlopen(LITELLM_URL, timeout=8) as r:
            data = json.load(r)
        print("[info] 已联网获取 LiteLLM 最新定价", file=sys.stderr)
    except Exception as e:
        print(f"[warn] 联网拉取定价失败（{e}），用缓存 {PRICING_CACHE}", file=sys.stderr)
    if data is None:
        try:
            with open(PRICING_CACHE) as f:
                data = json.load(f)
        except Exception as e:
            print(f"[warn] 定价缓存不可用（{e}），成本按 0 计", file=sys.stderr)
            return {}
    idx = {}
    for k, v in data.items():
        if k in ("_meta", "sample_spec") or not isinstance(v, dict):
            continue
        idx.setdefault(k.rsplit("/", 1)[-1].lower(), v)  # 按路径末段索引
    return idx


def price_key(model):
    """queue 模型名 → 定价索引 key（LiteLLM 段名；'(L)' 后缀 = 本地兜底表）"""
    m = (model or "").lower()
    return {
        "minimax-m2.7": "minimax-m2.7(L)", "minimax-m3": "minimax-m3(L)",
        "hy3": "hy3(L)", "qwen3.7-plus": "qwen3.7-plus(L)",
        "auto": "auto(L)", "unknown": "unknown(L)",
        "codex-auto-review": "gpt-5.6",     # 同族定价
        "glm-5-turbo": "glm-5.1",           # 缓存无 turbo，用 5.1
        "glm-5.2-x": "glm-5.2",
    }.get(m, m)


def price_for(idx, model):
    """返回 (input, output, cacheRead, cacheCreate) 每 token 单价；未知模型 None"""
    k = price_key(model)
    if k.endswith("(L)"):
        pin, pout, pcr, pcc = LOCAL_PRICING.get(k[:-3], (0.0, 0.0, 0.0, 0.0))
        return (pin / 1e6, pout / 1e6, pcr / 1e6, pcc / 1e6)
    e = idx.get(k)
    if e is None:
        return None
    pin = e.get("input_cost_per_token", 0) or 0
    pout = e.get("output_cost_per_token", 0) or 0
    pcr = e.get("cache_read_input_token_cost")
    pcr = pcr if pcr is not None else pin * 0.1   # 缺省: 读缓存 ~1/10 输入价
    pcc = e.get("cache_creation_input_token_cost")
    pcc = pcc if pcc is not None else pin          # 缺省: 写缓存 = 输入价
    return (pin, pout, pcr, pcc)


# ============ 数据获取 ============
def run_ccusage_json():
    """回退层：ccusage CLI JSON（tracker 缺失时用）"""
    try:
        out = subprocess.run(
            ["ccusage", "daily", "-j", "--no-color", "--by-agent"],
            capture_output=True, text=True, timeout=120,
        )
        return json.loads(out.stdout)
    except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        print(f"[warn] ccusage 不可用（{e}）", file=sys.stderr)
        return None


def _normalize_row(b):
    """复刻 TokenTracker local-api.normalizeQueueRow：legacy codex 行 input 含缓存需扣减；cursor 行 billable 补全"""
    src = b.get("source") or ""
    inp, cached, out = (b.get("input_tokens", 0) or 0), (b.get("cached_input_tokens", 0) or 0), (b.get("output_tokens", 0) or 0)
    if src in ("codex", "every-code") and cached > 0 and inp >= cached and b.get("total_tokens") == inp + out:
        b = dict(b, input_tokens=inp - cached)   # legacy 行：input 含 cache read，总=输入+输出
    if src == "cursor":
        tot, bill = b.get("total_tokens", 0) or 0, b.get("billable_total_tokens", 0) or 0
        if tot > 0 and bill < tot:
            b = dict(b, billable_total_tokens=tot)
    return b


def load_tracker():
    """主层：读 TokenTracker queue.jsonl（append-only，同 (source|model|hour_start) 取最后一条）
    逐条聚合 tokens / 成本 / 缓存拆分 / 对话 / 源 / 模型"""
    if not os.path.exists(TRACKER_QUEUE):
        print(f"[warn] 未找到 {TRACKER_QUEUE}，回退 ccusage", file=sys.stderr)
        return None
    idx = get_pricing()
    r = {"total_tokens": 0, "input": 0, "output": 0, "cached": 0, "cc": 0,
         "conversations": 0, "cost": 0.0, "by_agent": {}, "by_model": {},
         "by_model_cost": {}, "period_start": None, "peak_day": None,
         "peak_day_tokens": 0, "by_day": {}}
    dedup = {}
    for line in open(TRACKER_QUEUE):
        try:
            b = _normalize_row(json.loads(line))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(b, dict):
            continue
        key = (b.get("source") or "", b.get("model") or "", b.get("hour_start") or "")
        dedup[key] = b                      # last-wins（sync 重发累计值，只留最新）
    peak = {}
    for b in dedup.values():
        src = b.get("source") or "other"
        mdl = b.get("model") or "unknown"
        inp = b.get("input_tokens", 0) or 0
        cached = b.get("cached_input_tokens", 0) or 0
        cc = b.get("cache_creation_input_tokens", 0) or 0
        out = b.get("output_tokens", 0) or 0
        bill = b.get("billable_total_tokens")
        tot = bill if isinstance(bill, (int, float)) else (b.get("total_tokens") or 0)
        conv = b.get("conversation_count", 0) or 0

        r["total_tokens"] += tot
        r["input"] += inp
        r["output"] += out
        r["cached"] += cached
        r["cc"] += cc
        r["conversations"] += conv
        r["by_agent"][src] = r["by_agent"].get(src, 0) + tot
        r["by_model"][mdl] = r["by_model"].get(mdl, 0) + tot

        p = price_for(idx, mdl)
        if p:
            pin, pout, pcr, pcc = p
            c = inp * pin + out * pout + cached * pcr + cc * pcc
            r["cost"] += c
            r["by_model_cost"][mdl] = r["by_model_cost"].get(mdl, 0.0) + c

        hs = b.get("hour_start")
        if hs:
            try:
                ldt = datetime.datetime.fromisoformat(hs.replace("Z", "+00:00")).astimezone()
                day = ldt.date().isoformat()
                liso = ldt.isoformat(timespec="minutes")
            except ValueError:
                day, liso = hs[:10], hs
            peak[day] = peak.get(day, 0) + tot
            if r["period_start"] is None or liso < r["period_start"]:
                r["period_start"] = liso
    if peak:
        day, toks = max(peak.items(), key=lambda x: x[1])
        r["peak_day"], r["peak_day_tokens"] = day, toks
    r["by_day"] = peak
    return r


def _median(a):
    # stdlib 等价：排序取中位（奇数取中，偶数取两中位均值）
    return statistics.median(a)


def load_sessions():
    """会话效率：本地会话元数据（编辑覆盖 / 一次完成率 / 单次编辑成本·Token），缺文件回退 None"""
    if not os.path.exists(SESSION_QUEUE):
        print(f"[warn] 未找到 {SESSION_QUEUE}，跳过会话效率", file=sys.stderr)
        return None
    n = edit = fp = 0
    cpe, tpe = [], []
    for line in open(SESSION_QUEUE):
        try:
            b = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        n += 1
        if (b.get("edit_turns") or 0) > 0:
            edit += 1
            if b.get("first_pass"):
                fp += 1
            if b.get("cost_per_edit") is not None:
                cpe.append(b["cost_per_edit"])
            if b.get("tokens_per_edit") is not None:
                tpe.append(b["tokens_per_edit"])
    if n == 0:
        return None
    return {"sessions": n, "edit_sessions": edit, "first_pass": fp,
            "cost_per_edit": _median(cpe) if cpe else None,
            "tokens_per_edit": _median(tpe) if tpe else None}


def load_outcomes():
    """研发性价比：auto-outcomes 交付记录（每模型已交付数/采纳率），缺文件回退 None"""
    if not os.path.exists(OUTCOMES_FILE):
        print(f"[warn] 未找到 {OUTCOMES_FILE}，跳过研发性价比", file=sys.stderr)
        return None
    per = {}
    n = acc = 0
    for line in open(OUTCOMES_FILE):
        try:
            b = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        mdl = b.get("model") or "unknown"
        m = per.setdefault(mdl, [0, 0])
        m[1] += 1
        if b.get("accepted"):
            m[0] += 1
            acc += 1
        n += 1
    return {"outcomes": n, "accepted": acc, "per_model": per}


# ============ 聚合 ============
def _agent_disp(name):
    """agent 源名 → 展示名（opencode 特例，其余 capitalize）"""
    return "OpenCode" if name == "opencode" else name.capitalize()


def aggregate():
    result = {
        "total_tokens": 0, "total_cost": 0.0, "conversations": 0,
        "by_agent": {}, "by_model": {}, "models": [], "period": "",
        "period_start": "", "top_model": "", "peak_day": "", "peak_day_tokens": 0,
        "daily": [],
        "sessions": None, "qpd": None,
        "stats": {"input": 0, "output": 0, "cached": 0, "cc": 0},
    }

    tr = load_tracker()          # 主层：tracker（数据源超集，权威）
    if tr:
        result["total_tokens"] = tr["total_tokens"]
        result["total_cost"] = tr["cost"]
        result["conversations"] = tr["conversations"]
        result["by_agent"] = tr["by_agent"]
        result["by_model"] = tr["by_model"]
        result["period_start"] = (tr["period_start"] or "")[:7]
        result["peak_day"] = tr["peak_day"]
        result["peak_day_tokens"] = tr["peak_day_tokens"]
        result["stats"] = {k: tr[k] for k in ("input", "output", "cached", "cc")}
        result["daily"] = sorted((tr.get("by_day") or {}).items())
        if tr["period_start"]:
            d = datetime.date.fromisoformat(tr["period_start"][:10])
            result["period"] = f"{tr['period_start'][:10]} ~ {datetime.date.today().isoformat()}"
    else:                        # 回退层：ccusage
        data = run_ccusage_json()
        if data:
            t = data.get("totals", {})
            result["total_tokens"] = t.get("totalTokens", 0)
            result["total_cost"] = t.get("totalCost", 0.0)
            days = data.get("daily", [])
            for day in days:
                for a in day.get("agents", []):
                    name = a.get("agent", "?")
                    result["by_agent"][name] = result["by_agent"].get(name, 0) + a.get("totalTokens", 0)
                    for mb in a.get("modelBreakdowns", []):
                        mn = mb.get("modelName", "?")
                        result["by_model"][mn] = result["by_model"].get(mn, 0) + (
                            mb.get("inputTokens", 0) + mb.get("outputTokens", 0)
                            + mb.get("cacheReadTokens", 0) + mb.get("cacheCreationTokens", 0))
            if days:
                result["period"] = f"{days[0].get('period', '?')} ~ {days[-1].get('period', '?')}"
                result["period_start"] = (days[0].get("period") or "")[:7]
                result["daily"] = sorted((d.get("period"), d.get("totalTokens", 0))
                                         for d in days if d.get("period"))

    # cost 展示口径（用户确认）：本机 + 历史导出口径 $1.3K
    LEGACY_EXPORT_COST = 1348.07
    result["total_cost"] += LEGACY_EXPORT_COST

    # 会话效率 / 研发性价比（本地 tracker 同源指标）
    result["sessions"] = load_sessions()
    result["qpd"] = load_outcomes()
    if result["qpd"]:
        spend = {}
        for mdl, c in ((tr.get("by_model_cost") or {}) if tr else {}).items():
            disp = MODEL_NAMES.get(mdl, mdl)
            spend[disp] = spend.get(disp, 0.0) + c
        rows = []
        for mdl, (a, t) in result["qpd"]["per_model"].items():
            disp = MODEL_NAMES.get(mdl, mdl)
            rows.append({"model": disp, "accepted": a, "outcomes": t,
                         "spend": spend.get(disp, 0.0)})
        rows = [x for x in rows if x["outcomes"] > 0]
        for x in rows:
            x["rate"] = x["accepted"] / x["outcomes"]
            x["cost_per"] = x["spend"] / x["accepted"] if x["accepted"] and x["spend"] > 0 else None
        rows.sort(key=lambda x: (x["cost_per"] is None, x["cost_per"] or 0))
        result["qpd"]["rows"] = rows[:6]

    # 模型榜（官方命名 + 排序）
    merged = {}
    for mn, tok in result["by_model"].items():
        name = MODEL_NAMES.get(mn, mn)
        merged[name] = merged.get(name, 0) + tok
    result["models"] = sorted(merged.items(), key=lambda x: -x[1])[:10]
    if result["models"]:
        result["top_model"] = result["models"][0][0]

    # by agent 排序 + 展示名归一
    agents = {}
    for name, tok in result["by_agent"].items():
        disp = _agent_disp(name)
        agents[disp] = agents.get(disp, 0) + tok
    result["by_agent"] = dict(sorted(agents.items(), key=lambda x: -x[1]))
    return result


# ============ SVG 生成 ============
def fmt_tokens(n):
    if n >= 1e9: return f"{n/1e9:.1f}B"
    if n >= 1e6: return f"{n/1e6:.1f}M"
    if n >= 1e3: return f"{n/1e3:.0f}K"
    return str(n)


def esc(s):
    # stdlib 等价：html.escape(quote=False) 只转义 & < >，引号原样
    return html.escape(s, quote=False)


def _nice_max(v):
    """向上取整到 0.5B 粒度（4.14B → 4.5B），保底 1B"""
    step = 0.5e9
    return max(1e9, math.ceil(v / step) * step)


def _parse_daily(r):
    """r['daily'] [(ISO日期, 数值)] → {date: 数值}；坏日期跳过（外部数据边界）"""
    daily = {}
    for k, v in (r.get("daily") or []):
        try:
            daily[datetime.date.fromisoformat(k)] = v
        except ValueError:
            pass
    return daily


def trend_section(r, PAL, L):
    """USAGE TREND 区块：最近 30 天日柱 + 7日滚动均线 + 峰值日标注 + 图例
    + 输入/缓存/输出/写缓存拆分明细行。明细为全时段，图表仅窗口。"""
    out = []
    X0, X1 = 32, 868
    CW = X1 - X0
    today = datetime.date.today()

    daily = _parse_daily(r)

    # 窗口收缩：仅最近 30 天（chart 范围；拆分明细行仍为全时段）
    lo = today - datetime.timedelta(days=29)
    daily = {d: v for d, v in daily.items() if d >= lo}
    start = lo
    span_days = max((today - start).days, 1)

    days_sorted = sorted(daily)
    # 7日滚动均值：活跃日窗口（当前活跃日 + 前6个活跃日）
    roll = {}
    for i, d in enumerate(days_sorted):
        win = days_sorted[max(0, i - 6): i + 1]
        roll[d] = sum(daily[x] for x in win) / len(win)

    vmax = _nice_max(max(daily.values()) if daily else 0)
    plot_top, plot_bot = 528, 628
    PH = plot_bot - plot_top

    def px(d):
        return X0 + (d - start).days / span_days * CW

    def py(v):
        return plot_bot - (v / vmax) * PH

    out.append(f'<line x1="{X0}" y1="496" x2="{X1}" y2="496" stroke="{PAL["track"]}" stroke-width="1"/>')
    out.append(f'<text x="{X0}" y="514" font-size="11" font-weight="600" class="muted" letter-spacing="2">{L["trend"]}</text>')

    # 图例（右上，与标题同行）：色块=每日用量，线段=7日均值，圆点=峰值日
    leg_items = [(L["lg_bar"], "bar"), (L["lg_avg"], "line"), (L["lg_peak"], "dot")]
    lx = X1
    for lab, kind in reversed(leg_items):
        lw = len(lab) * 5.9 + 24
        lx -= lw
        if kind == "bar":
            out.append(f'<rect x="{lx}" y="508" width="10" height="10" rx="1" fill="{PAL["acc"]}"/>')
            tx = lx + 14
        elif kind == "line":
            out.append(f'<line x1="{lx}" y1="513" x2="{lx + 18}" y2="513" stroke="{PAL["acc_hi"]}" stroke-width="2" stroke-linecap="round"/>')
            tx = lx + 22
        else:
            out.append(f'<circle cx="{lx + 5}" cy="513" r="5" fill="{PAL["acc_hi"]}" stroke="{PAL["bg"]}" stroke-width="1.2"/>')
            tx = lx + 14
        out.append(f'<text x="{tx}" y="514" font-size="10" font-weight="500" class="muted">{lab}</text>')
        lx -= 12

    # Y 网格线（3 级 faint + 基线）
    for frac in (0.25, 0.5, 0.75):
        y = plot_bot - PH * frac
        out.append(f'<line x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}" stroke="{PAL["faint"]}" stroke-width="1" opacity="0.35"/>')
    out.append(f'<line x1="{X0}" y1="{plot_bot}" x2="{X1}" y2="{plot_bot}" stroke="{PAL["track"]}" stroke-width="1"/>')

    # 日柱（纵向渐变，零日跳过留空隙；峰值日 acc_hi 高亮）
    acc = PAL["acc"]
    grad_id = "tg" + ("d" if PAL.get("dark") else "l")
    out.append(f'<defs><linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">'
               f'<stop offset="0" stop-color="{acc}" stop-opacity="0.45"/>'
               f'<stop offset="1" stop-color="{acc}" stop-opacity="0.06"/></linearGradient></defs>')
    bw = CW / span_days * 0.72
    pk_day = max(daily, key=daily.get) if daily else None
    for d in days_sorted:
        v = daily[d]
        x = max(px(d) - bw / 2, X0)
        w = min(bw, X1 - x)
        y = py(v)
        fill = PAL["acc_hi"] if d == pk_day else f"url(#{grad_id})"
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{plot_bot - y:.1f}" rx="1" fill="{fill}"/>')

    # 叠加折线：7日滚动均线（平滑稀疏日尖峰），acc_hi 2px 圆角
    rpts = " ".join(f"{px(d):.1f},{py(roll[d]):.1f}" for d in days_sorted)
    out.append(f'<polyline points="{rpts}" fill="none" stroke="{PAL["acc_hi"]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" opacity="0.9"/>')

    # 峰值日标注（窗口内重算；圆点 + 日期 + 数值）
    if pk_day:
        xp, yp = px(pk_day), py(daily[pk_day])
        out.append(f'<circle cx="{xp:.1f}" cy="{yp:.1f}" r="4" fill="{PAL["acc_hi"]}" stroke="{PAL["bg"]}" stroke-width="2"/>')
        lbl = f'{pk_day.month}/{pk_day.day} · {fmt_tokens(daily[pk_day])}'
        anchor = "end" if xp > X1 - 90 else "start"
        lx = xp - 8 if anchor == "end" else xp + 8
        out.append(f'<text x="{lx:.1f}" y="{yp - 9:.1f}" font-size="10" font-weight="600" class="text2" text-anchor="{anchor}">{lbl}</text>')

    # X 周刻度（周一起始，M/D 标签；30 天窗口按周稀疏标（逐日标注会碰撞））
    wk0 = start - datetime.timedelta(days=start.weekday())
    last_lx = None
    dd = wk0
    while dd <= today:
        x = px(dd)
        if x >= X0:
            out.append(f'<line x1="{x:.1f}" y1="{plot_bot}" x2="{x:.1f}" y2="{plot_bot + 5}" stroke="{PAL["faint"]}" stroke-width="1" opacity="0.5"/>')
            if x < X1 - 22 and (last_lx is None or x - last_lx >= 34):
                out.append(f'<text x="{x:.1f}" y="646" font-size="9.5" font-weight="500" class="faint" text-anchor="middle">{dd.month}/{dd.day}</text>')
                last_lx = x
        dd += datetime.timedelta(days=7)

    # ccswitch 风格拆分明细行：输入/缓存/输出/写缓存（彩色圆点 + 数值 + 占比）
    st = r.get("stats", {})
    parts = [st.get("input", 0), st.get("cached", 0), st.get("output", 0), st.get("cc", 0)]
    stot = sum(parts)
    names = [L["c_in"], L["c_cached"], L["c_out"], L["c_cc"]]
    cell_w = CW / 4
    yl, yv = 668, 690
    for i, (v, nm) in enumerate(zip(parts, names)):
        share = v / stot * 100 if stot else 0
        x = X0 + cell_w * i + 16
        out.append(f'<circle cx="{x + 6}" cy="{yl - 5}" r="3.5" fill="{PAL["split"][i]}"/>')
        out.append(f'<text x="{x + 16}" y="{yl}" font-size="9.5" font-weight="600" class="faint" letter-spacing="1.5">{nm}</text>')
        out.append(f'<text x="{x + 16}" y="{yv}" font-size="15" font-weight="700" class="text num">{fmt_tokens(v)}'
                   f'<tspan font-size="11" font-weight="500" class="muted"> · {share:.1f}%</tspan></text>')
        if i < 3:
            out.append(f'<line x1="{X0 + cell_w * (i + 1):.1f}" y1="{yl - 6}" x2="{X0 + cell_w * (i + 1):.1f}" y2="{yv + 4}" stroke="{PAL["track"]}" stroke-width="1"/>')
    return out


def svg_card(r, dark=True, zh=False):
    """生成 token 卡片 SVG：英雄头部 + 活跃热力图 + 双栏条形图（工具/模型）+ 使用趋势 + 页脚。"""
    W, H = 900, 754
    PAD = 32
    X0, X1 = PAD, W - PAD
    CW = X1 - X0
    now = datetime.date.today().isoformat()

    # 数据驱动的迷你统计（真实缓存拆分 / 峰值 / 对话数，缺数据时回退旧值）
    st = r.get("stats", {})
    inp, out = st.get("input", 0), st.get("output", 0)
    cached, cc = st.get("cached", 0), st.get("cc", 0)
    denom = inp + out + cached + cc
    cpct = cached / denom * 100 if denom else 95.0
    conv_k = r.get("conversations", 214000) / 1000
    start = r.get("period_start") or "2026-03"
    try:
        d = datetime.date.fromisoformat(start + "-01")
        start_disp = f"{d.strftime('%b %Y')}"
        start_disp_cn = f"{d.year} 年 {d.month} 月"
    except ValueError:
        start_disp, start_disp_cn = start, start

    if dark:
        PAL = dict(bg="#0d1117", card="#161b22", border="#30363d", track="#21262d",
                   text="#e6edf3", text2="#c9d1d9", muted="#8b949e", faint="#57606a",
                   acc="#f59e0b", acc_hi="#fbbf24", dark=True,
                   split=["#fbbf24", "#f59e0b", "#fde68a", "#8b949e"])
        HM = ["#21262d", "#4a3a12", "#7d5a17", "#b9821d", "#fbbf24"]   # 琥珀色阶（0-4）
    else:
        PAL = dict(bg="#ffffff", card="#f6f8fa", border="#d0d7de", track="#eaeef2",
                   text="#1f2328", text2="#24292f", muted="#656d76", faint="#8c959f",
                   acc="#b45309", acc_hi="#d97706", dark=False,
                   split=["#d97706", "#b45309", "#f59e0b", "#8c959f"])
        HM = ["#ebedf0", "#f5e0b0", "#e8c26a", "#d69b2f", "#b45309"]

    if zh:
        L = dict(aria="AI Token 用量",
                 hero_lbl="AI TOKEN 使用量", hero_sub=f"{conv_k:.0f}K+ 对话 · 自 {start_disp_cn} 起",
                 cost_lbl="估算成本", cost_sub="LiteLLM 官方定价",
                 heatmap="TOKEN 活跃热力图", less="少", more="多", today="今日",
                 by_tool="按工具", top_models="模型榜",
                 trend="使用趋势", c_in="输入", c_cached="缓存读", c_out="输出", c_cc="缓存写",
                 lg_bar="每日用量", lg_avg="7日均值", lg_peak="峰值日",
                 foot_stats=f"输入 {fmt_tokens(inp)} · 输出 {fmt_tokens(out)} · 缓存 {cpct:.0f}% · {conv_k:.0f}K 对话",
                 foot_updated="更新于",
                 wd={1: "一", 3: "三", 5: "五"})
        def mon_label(m):
            return f"{m} 月"
    else:
        L = dict(aria="AI token usage",
                 hero_lbl="AI TOKEN USAGE", hero_sub=f"{conv_k:.0f}K+ conversations since {start_disp}",
                 cost_lbl="ESTIMATED COST", cost_sub="official pricing · LiteLLM rates",
                 heatmap="TOKEN ACTIVITY", less="Less", more="More", today="TODAY",
                 by_tool="BY TOOL", top_models="TOP MODELS",
                 trend="USAGE TREND", c_in="INPUT", c_cached="CACHED", c_out="OUTPUT", c_cc="CACHE WRITE",
                 lg_bar="Daily", lg_avg="7d avg", lg_peak="Peak",
                 foot_stats=f"input {fmt_tokens(inp)} · output {fmt_tokens(out)} · cached {cpct:.0f}% · {conv_k:.0f}K conversations",
                 foot_updated="updated",
                 wd={1: "Mon", 3: "Wed", 5: "Fri"})
        def mon_label(m):
            return datetime.date(2024, m, 1).strftime("%b")

    if zh:
        F = '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif'
    else:
        F = '-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif'

    hm_cls = "\n".join(f"    .h{k} {{ fill: {c}; }}" for k, c in enumerate(HM))
    lines = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{L['aria']}">
  <style>
    .text {{ fill: {PAL['text']}; font-family: {F}; }}
    .text2 {{ fill: {PAL['text2']}; font-family: {F}; }}
    .muted {{ fill: {PAL['muted']}; font-family: {F}; }}
    .faint {{ fill: {PAL['faint']}; font-family: {F}; }}
    .track {{ fill: {PAL['track']}; }}
    .num {{ font-variant-numeric: tabular-nums; }}
{hm_cls}
  </style>
  <rect width="{W}" height="{H}" rx="14" fill="{PAL['bg']}"/>
  <rect x="1" y="1" width="{W-2}" height="{H-2}" rx="13" fill="none" stroke="{PAL['border']}" stroke-width="1"/>''']

    def text(x, y, s, size, weight, cls, anchor="start", spacing=None, num=False):
        extra = f' letter-spacing="{spacing}"' if spacing else ""
        if num:
            cls = f"{cls} num"
        lines.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" class="{cls}" text-anchor="{anchor}"{extra}>{esc(s)}</text>')

    # ===== 英雄头部：左大数字 + 右成本（编辑不对称） =====
    text(X0, 46, L["hero_lbl"], 11, 600, "muted", spacing="2")
    hv = fmt_tokens(r["total_tokens"])
    text(X0, 92, hv, 42, 700, "text", num=True)
    text(X0 + len(hv) * 23 + 14, 88, "tokens", 13, 600, "muted")
    text(X0, 114, L["hero_sub"], 11.5, 400, "muted")
    text(X1, 46, L["cost_lbl"], 11, 600, "muted", anchor="end", spacing="2")
    text(X1, 88, f"${r['total_cost']/1000:.1f}K", 30, 700, "text", anchor="end", num=True)
    text(X1, 114, L["cost_sub"], 11.5, 400, "muted", anchor="end")

    # ===== TOKEN ACTIVITY 热力图（GitHub contribution 风格，琥珀色阶） =====
    lines.append(f'<line x1="{X0}" y1="128" x2="{X1}" y2="128" stroke="{PAL["track"]}" stroke-width="1"/>')
    text(X0, 146, L["heatmap"], 11, 600, "muted", spacing="2")

    daily = _parse_daily(r)
    today_d = datetime.date.today()
    start_d = None
    try:
        start_d = datetime.date.fromisoformat((r.get("period_start") or "")[:10])
    except ValueError:
        start_d = None
    if start_d is None:
        start_d = min(daily) if daily else today_d - datetime.timedelta(days=167)

    pos = sorted([v for v in daily.values() if v > 0])
    if pos:
        n = len(pos)
        th = [pos[min(n - 1, int(n * 0.4))], pos[min(n - 1, int(n * 0.7))], pos[min(n - 1, int(n * 0.9))]]

        def lvl(v):
            if v <= 0:
                return 0
            if v > th[2]:
                return 4
            if v > th[1]:
                return 3
            if v > th[0]:
                return 2
            return 1
    else:
        lvl = lambda v: 0

    cell, pitch = 10, 13
    week0 = start_d - datetime.timedelta(days=(start_d.weekday() + 1) % 7)  # 周日开头
    cols = []
    ws = week0
    while ws <= today_d:
        cols.append(ws)
        ws += datetime.timedelta(days=7)
    ncol = len(cols)
    hm_w = ncol * pitch
    grid_x = X0 + (CW - hm_w) // 2
    hm_y = 170

    # 月份标签（列对应周一→该月起始列）
    prev_m = None
    for i, ws in enumerate(cols):
        m = ws.month
        label_it = (i == 0 and m != prev_m) or (i > 0 and m != prev_m)
        if label_it and i > 0 and ws < start_d:
            label_it = False
        if label_it:
            x = grid_x + i * pitch
            if x < X1 - 26:
                lines.append(f'<text x="{x}" y="162" font-size="9.5" font-weight="500" class="faint" text-anchor="start">{mon_label(m)}</text>')
        prev_m = m
    for row, lb in L["wd"].items():
        lines.append(f'<text x="{grid_x - 8}" y="{hm_y + row * pitch + 8}" font-size="9" font-weight="500" class="faint" text-anchor="end">{lb}</text>')
    for i, ws in enumerate(cols):
        x = grid_x + i * pitch
        for row in range(7):
            dd = ws + datetime.timedelta(days=row)
            if dd < start_d or dd > today_d:
                continue
            lev = lvl(daily.get(dd, 0))
            lines.append(f'<rect x="{x}" y="{hm_y + row * pitch}" width="{cell}" height="{cell}" rx="2" class="h{lev}"/>')
    # 图例（网格右下，GitHub 风格）
    sw, lg_y = 8, hm_y + 7 * pitch + 18
    sw_x_end = grid_x + hm_w - 30
    sw_x0 = sw_x_end - (5 * sw + 4 * 2)
    text(sw_x0 - 8, lg_y + 8, L["less"], 10, 500, "faint", anchor="end")
    for k in range(5):
        lines.append(f'<rect x="{sw_x0 + k * (sw + 2)}" y="{lg_y}" width="{sw}" height="{sw}" rx="1.5" class="h{k}"/>')
    text(grid_x + hm_w - 4, lg_y + 8, L["more"], 10, 500, "faint", anchor="end")
    # 今日实时计数（网格右侧垂直居中；与热力图同源，随同步刷新）
    sx = grid_x + hm_w + 26
    t_label = L["today"]
    text(sx, hm_y + 36, t_label.upper() if not zh else t_label, 9.5, 600, "faint", spacing="2" if not zh else None)
    text(sx, hm_y + 54, fmt_tokens(daily.get(today_d, 0)), 13, 600, "text2", num=True)

    # ===== 双栏：BY TOOL 条 | TOP MODELS 条（同构条形图） =====
    col_gap, left_w = 28, 400
    rgt_x = X0 + left_w + col_gap
    rgt_w = X1 - rgt_x
    text(X0, 304, L["by_tool"], 11, 600, "muted", spacing="2")
    text(rgt_x, 304, L["top_models"], 11, 600, "muted", spacing="2")
    y0 = 318
    agents = r["by_agent"]
    total = r["total_tokens"]

    # 左栏：工具（品牌色）
    label_w, pct_w = 72, 96
    track_x = X0 + label_w
    track_w = left_w - label_w - pct_w
    for i, (name, tok) in enumerate(agents.items()):
        if tok <= 0:
            continue
        pct = tok / total * 100 if total else 0
        bw = max(track_w * pct / 100, 2)
        color = AGENT_COLORS.get(name.lower(), "#8b949e")
        text(X0, y0 + 10 + i * 26, _agent_disp(name), 12, 500, "text2")
        lines.append(f'<rect x="{track_x}" y="{y0 + i * 26}" width="{track_w}" height="10" rx="3" class="track"/>')
        lines.append(f'<rect x="{track_x}" y="{y0 + i * 26}" width="{bw:.1f}" height="10" rx="3" fill="{color}" opacity="0.9"/>')
        text(X0 + left_w, y0 + 10 + i * 26, f"{fmt_tokens(tok)} ({pct:.0f}%)", 11, 500, "muted", anchor="end", num=True)

    # 右栏：模型（琥珀强调色）
    rlabel_w, rpct_w = 126, 84
    rtrack_x = rgt_x + rlabel_w
    rtrack_w = rgt_w - rlabel_w - rpct_w
    for i, (name, tok) in enumerate(r["models"][:6]):
        pct = tok / total * 100 if total else 0
        bw = max(rtrack_w * pct / 100, 2)
        text(rgt_x, y0 + 10 + i * 26, name, 12, 500, "text2")
        lines.append(f'<rect x="{rtrack_x}" y="{y0 + i * 26}" width="{rtrack_w}" height="10" rx="3" class="track"/>')
        lines.append(f'<rect x="{rtrack_x}" y="{y0 + i * 26}" width="{bw:.1f}" height="10" rx="3" fill="{PAL["acc"]}" opacity="0.9"/>')
        text(X1, y0 + 10 + i * 26, f"{fmt_tokens(tok)} ({pct:.0f}%)", 11, 500, "muted", anchor="end", num=True)

    # ===== 使用趋势（最近 30 天窗口：日柱 + 7日均线 + 拆分） =====
    lines.extend(trend_section(r, PAL, L))

    # ===== 页脚 =====
    lines.append(f'<line x1="{X0}" y1="706" x2="{X1}" y2="706" stroke="{PAL["track"]}" stroke-width="1"/>')
    text(X0, 734, L["foot_stats"], 10.5, 400, "muted", num=True)
    text(X1, 734, f'{L["foot_updated"]} {now}', 10.5, 400, "faint", anchor="end")

    return "\n".join(lines) + "\n</svg>\n"


# ============ main ============
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出聚合 JSON")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--once", action="store_true", help="只同步一次，不启动守护")
    ap.add_argument("--stop", action="store_true", help="停止后台守护")
    ap.add_argument("--interval", type=float, default=24.0, help="守护同步间隔（小时）")
    ap.add_argument("--no-sync", action="store_true", help="只生成 SVG，不提交/推送 GitHub")
    args = ap.parse_args()

    if args.stop:
        stop_daemon()
        return

    r = aggregate()
    if args.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return

    svg_dark = svg_card(r, dark=True)
    svg_light = svg_card(r, dark=False)
    svg_zh_dark = svg_card(r, dark=True, zh=True)
    svg_zh_light = svg_card(r, dark=False, zh=True)
    for name, svg in (("token-stats-dark.svg", svg_dark),
                      ("token-stats-light.svg", svg_light),
                      ("token-stats-zh-dark.svg", svg_zh_dark),
                      ("token-stats-zh-light.svg", svg_zh_light)):
        with open(name, "w") as f:
            f.write(svg)
        print(f"✅ 已生成 {name}")
    with open(args.out, "w") as f:  # 默认输出 = 英文 dark 版，兼容旧引用
        f.write(svg_dark)
    print(f"   tokens: {fmt_tokens(r['total_tokens'])} | cost: ${r['total_cost']:,.0f} | conversations: {r['conversations']:,}")
    print(f"   cached: {r['stats']['cached']/max(sum(r['stats'].values()),1)*100:.0f}% | peak: {r['peak_day']} {fmt_tokens(r['peak_day_tokens'])}")
    print(f"   by agent: {', '.join(f'{k} {fmt_tokens(v)}' for k, v in r['by_agent'].items())}")
    print(f"   top: {', '.join(f'{n} {fmt_tokens(t)}' for n, t in r['models'][:5])}")

    if not args.no_sync:
        git_sync()
    if not args.once:
        start_daemon(args.interval)


# ============ 自包含定时守护 ============
PID_FILE = os.path.join(REPO_DIR, ".token-stats-daemon.pid")
LOG_FILE = os.path.join(REPO_DIR, ".token-stats-daemon.log")
CHECK_EVERY = 60          # 秒：仓库存在性自检间隔
CYCLE_TIMEOUT = 600       # 秒：单周期超时


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_cmd(pid):
    """ps 取进程命令行；失败/不存在返回空串（校验 pid 身份，防 PID 复用误判）"""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                             capture_output=True, text=True, timeout=5)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _lock_daemon():
    """原子抢占守护独占锁（fcntl.flock 内核级互斥，无 TOCTOU 竞态）。

    返回持有锁的 fd；抢不到返回 None（已有守护在跑）。
    守护存活期间必须持有该 fd —— 锁随进程消亡自动释放，pid 文件残留无害。
    """
    fd = os.open(PID_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    return fd


def _unpushed_commits():
    """本地产出、远程还没有的提交数（`HEAD --not --remotes`，离线也准，无需 fetch）。

    推送失败后 commit 已在本地、工作区无 diff——只有数未推送提交才能发现需要重试。
    异常时按 1 处理（宁多推不少推）。
    """
    try:
        out = subprocess.run(["git", "rev-list", "--count", "HEAD", "--not", "--remotes"],
                             capture_output=True, text=True, timeout=15)
        return max(int(out.stdout.strip() or 0), 0)
    except Exception:
        return 1


README_FILES = ("README.md", "README.zh-CN.md")
# (属性, 文件名)：README 里引用的 token-stats 图片（GitHub 重写相对路径时保留 query）
_README_IMGS = (
    ("srcset", "token-stats-dark.svg"),
    ("src", "token-stats-light.svg"),
    ("srcset", "token-stats-zh-dark.svg"),
    ("src", "token-stats-zh-light.svg"),
)


def _bump_readme_cache_bust(version):
    """给 README 图片引用追加 `?v=<version>`（幂等：旧 v 会被替换）。

    GitHub 渲染 README 时把相对路径重写为恒定 URL（`/raw/main/...`），各层
    HTTP 缓存按 URL 命中 → 内容变了 URL 没变就吃到旧缓存。加 query 后每次
    刷新 URL 都变 → 必 MISS。只在真正提交时调用，配合 git_sync 的跳过语义。
    """
    for fname in README_FILES:
        path = os.path.join(REPO_DIR, fname)
        try:
            with open(path) as f:
                text = f.read()
        except OSError:
            print(f"   ⚠️ 读取失败，跳过 {fname}")
            continue
        for attr, img in _README_IMGS:
            text = re.sub(rf'({attr}="{re.escape(img)})(\?v=[^"]*)?(")',
                          rf"\1?v={version}\3", text)
        with open(path, "w") as f:
            f.write(text)
    print(f"   README 缓存参数已更新 v={version}")


def git_sync():
    """提交 SVG/README 变更并推送。

    - 工作区有变更（SVG 或 README）→ 重写 README 的 ?v= 缓存参数 → commit
    - 存在未推送提交（含上次推送失败遗留）→ push，同周期内退避重试 3 次；
      仍失败则留到下轮周期继续重试（不会因"无数据变化"漏推）。
    """
    svg_dirty = subprocess.run(["git", "diff", "--quiet", "--", "token-stats*.svg"]).returncode != 0
    readme_dirty = subprocess.run(["git", "diff", "--quiet", "--", "README.md", "README.zh-CN.md"]).returncode != 0
    if not svg_dirty and not readme_dirty:
        print("   无数据变化，跳过提交")
    else:
        _bump_readme_cache_bust(int(time.time()))
        subprocess.run(["git", "add", "token-stats*.svg", "README.md", "README.zh-CN.md"], check=True)
        subprocess.run(["git", "commit", "-m", "chore: refresh token stats"], check=True)
        print("   已提交，推送中…")
    if _unpushed_commits() <= 0:
        return
    for attempt in range(1, 4):
        r = subprocess.run(["git", "push", "origin", "HEAD"])
        if r.returncode == 0:
            print("   推送成功")
            return
        print(f"   推送失败（第 {attempt} 次），30s 后重试…", flush=True)
        time.sleep(30)
    print("   推送失败（已重试 3 次，下轮周期自动重试）")


def daemon_loop(interval_hours, lock_fd):
    """守护主循环。lock_fd 必须持有到进程退出（flock 锁随 fd 释放）。"""
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
    chunks = max(1, int(interval_hours * 3600 / CHECK_EVERY))
    print(f"守护启动 interval={interval_hours}h pid={os.getpid()}", flush=True)
    while os.path.exists(os.path.join(REPO_DIR, ".git")):
        try:
            subprocess.run([sys.executable, os.path.abspath(__file__), "--once"],
                           timeout=CYCLE_TIMEOUT, check=True)
        except Exception as e:
            print(f"周期失败: {e}", flush=True)
        for _ in range(chunks):
            time.sleep(CHECK_EVERY)
            if not os.path.exists(os.path.join(REPO_DIR, ".git")):
                break
        if not os.path.exists(os.path.join(REPO_DIR, ".git")):
            print("仓库已删除，守护退出", flush=True)
            break
    del lock_fd


def start_daemon(interval_hours):
    fd = _lock_daemon()
    if fd is None:
        pid = ""
        try:
            pid = open(PID_FILE).read().strip()
        except OSError:
            pass
        print(f"   后台守护已在运行 (pid {pid})，无需重启" if pid else "   后台守护已在运行，无需重启")
        return
    pid = os.fork()
    if pid > 0:
        os.write(fd, str(pid).encode())
        os.close(fd)          # parent 释放；锁由守护子进程继续持有
        print(f"   后台守护已启动 pid={pid}（每 {interval_hours:g}h 自动同步；重启电脑后自动停止，再跑本脚本即恢复）")
        return
    os.setsid()
    os.chdir(REPO_DIR)
    os.umask(0o022)
    if fd < 3:
        fd = os.dup2(fd, 3)   # 锁 fd 挪高位：closed-stdio 启动时 os.open 可能返回 0，会被下方 dup2 覆盖导致锁丢失
    with open(LOG_FILE, "a") as f:
        os.dup2(f.fileno(), 0)
        os.dup2(f.fileno(), 1)
        os.dup2(f.fileno(), 2)
    daemon_loop(interval_hours, fd)
    os._exit(0)


def stop_daemon():
    fd = os.open(PID_FILE, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        pass                      # 锁被守护持有 → 有守护
    else:
        os.close(fd)              # 抢到锁 → 无守护（残留 pid 文件由下次启动覆盖）
        print("后台守护未在运行")
        return
    try:
        pid = int(open(PID_FILE).read().strip())
    except (ValueError, OSError):
        pid = 0
    os.close(fd)
    if pid <= 0 or not _pid_alive(pid) or "token-stats" not in _pid_cmd(pid):
        print(f"锁被持有但无法确认守护身份 (pid={pid or '空'})，请手动排查")
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass                      # 并发 stop 已杀：锁随后释放，等锁循环兜底
    for _ in range(40):           # 等锁释放（守护退出即释放，比等 pid 死亡更可靠）
        time.sleep(0.25)
        try:
            t = os.open(PID_FILE, os.O_RDWR)
        except FileNotFoundError:
            print("后台守护已停止")
            return
        try:
            fcntl.flock(t, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(t)
            continue
        try:
            os.remove(PID_FILE)   # 必须持锁删除：先 close 再 remove 会让新守护抢走锁后
        except FileNotFoundError:  # 又被 unlink，锁落到孤儿 inode → 后续可双守护
            pass
        os.close(t)
        print("后台守护已停止")
        return
    print("进程仍未退出，请手动 kill")


if __name__ == "__main__":
    main()
