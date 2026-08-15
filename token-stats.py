#!/usr/bin/env python3
"""
token-stats.py: 生成 GitHub profile 的 AI token usage SVG 卡片

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
  python3 token-stats.py                # 生成 4 张 SVG
  python3 token-stats.py --json         # 输出聚合 JSON

依赖: 无第三方 Python 包（联网定价失败自动用缓存）
"""

import argparse
import json
import os
import subprocess
import sys
import datetime
import urllib.request

# ============ 配置 ============
LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PRICING_CACHE = os.path.expanduser("~/.tokentracker/cache/pricing.json")  # LiteLLM 定价缓存
TRACKER_QUEUE = os.path.expanduser("~/.tokentracker/tracker/queue.jsonl")  # TokenTracker 记录
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
            data = json.load(open(PRICING_CACHE))
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
         "period_start": None, "peak_day": None, "peak_day_tokens": 0}
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
            r["cost"] += inp * pin + out * pout + cached * pcr + cc * pcc

        hs = b.get("hour_start")
        if hs:
            day = hs[:10]
            peak[day] = peak.get(day, 0) + tot
            if r["period_start"] is None or hs < r["period_start"]:
                r["period_start"] = hs
    if peak:
        day, toks = max(peak.items(), key=lambda x: x[1])
        r["peak_day"], r["peak_day_tokens"] = day, toks
    return r


# ============ 聚合 ============
def aggregate():
    result = {
        "total_tokens": 0, "total_cost": 0.0, "conversations": 0,
        "by_agent": {}, "by_model": {}, "models": [], "period": "",
        "period_start": "", "top_model": "", "peak_day": "", "peak_day_tokens": 0,
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

    # cost 展示口径（用户确认）：本机 + 历史导出口径 $1.3K
    LEGACY_EXPORT_COST = 1348.07
    result["total_cost"] += LEGACY_EXPORT_COST

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
        disp = "OpenCode" if name == "opencode" else name.capitalize()
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
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_card(r, dark=True, zh=False):
    """生成 token 卡片 SVG。dark=True 产出 GitHub dark 主题配色，False 产出 light；zh=True 产出中文文案。"""
    W, H = 900, 500
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
    top_model = r.get("top_model") or "GPT-5.6 Sol"
    peak = r.get("peak_day_tokens") or 9_000_000_000

    if dark:
        PAL = dict(bg="#0d1117", card="#161b22", border="#30363d", track="#21262d",
                   text="#e6edf3", text2="#c9d1d9", muted="#8b949e", faint="#57606a",
                   acc="#f59e0b", acc_hi="#fbbf24")
    else:
        PAL = dict(bg="#ffffff", card="#f6f8fa", border="#d0d7de", track="#eaeef2",
                   text="#1f2328", text2="#24292f", muted="#656d76", faint="#8c959f",
                   acc="#b45309", acc_hi="#d97706")

    if zh:
        L = dict(aria="AI Token 用量",
                 card1_lbl="AI TOKEN 使用量", card1_sub=f"{conv_k:.0f}K+ 对话，自 {start_disp_cn} 起",
                 mini_in="输入", mini_out="输出", mini_cached="缓存",
                 card2_lbl="估算成本", card2_sub="LiteLLM 官方定价",
                 mini_top="头号模型", mini_peak="峰值日",
                 by_tool="按工具", top_models="模型榜",
                 foot_cached=f"缓存 {cpct:.0f}%", foot_updated="更新于")
    else:
        L = dict(aria="AI token usage",
                 card1_lbl="AI TOKEN USAGE", card1_sub=f"{conv_k:.0f}K+ conversations since {start_disp}",
                 mini_in="input", mini_out="output", mini_cached="cached",
                 card2_lbl="ESTIMATED COST", card2_sub="official pricing, LiteLLM rates",
                 mini_top="top model", mini_peak="peak day",
                 by_tool="BY TOOL", top_models="TOP MODELS",
                 foot_cached=f"cached {cpct:.0f}%", foot_updated="updated")

    if zh:
        F = '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif'
    else:
        F = '-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif'

    lines = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{L['aria']}">
  <style>
    .text {{ fill: {PAL['text']}; font-family: {F}; }}
    .text2 {{ fill: {PAL['text2']}; font-family: {F}; }}
    .muted {{ fill: {PAL['muted']}; font-family: {F}; }}
    .faint {{ fill: {PAL['faint']}; font-family: {F}; }}
    .track {{ fill: {PAL['track']}; }}
    .num {{ font-variant-numeric: tabular-nums; }}
  </style>
  <defs>
    <linearGradient id="accg" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{PAL['acc_hi']}"/><stop offset="1" stop-color="{PAL['acc']}"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" rx="14" fill="{PAL['bg']}"/>
  <rect x="1" y="1" width="{W-2}" height="{H-2}" rx="13" fill="none" stroke="{PAL['border']}" stroke-width="1"/>''']

    def text(x, y, s, size, weight, cls, anchor="start", spacing=None, num=False):
        extra = f' letter-spacing="{spacing}"' if spacing else ""
        if num:
            cls = f"{cls} num"
        lines.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" class="{cls}" text-anchor="{anchor}"{extra}>{esc(s)}</text>')

    # ===== 两张并排统计卡 =====
    card_w = (CW - 14) // 2
    card_y, card_h = 24, 132
    cards = [
        {"lbl": L["card1_lbl"], "val": fmt_tokens(r["total_tokens"]), "suffix": "tokens",
         "sub": L["card1_sub"],
         "mini": [(L["mini_in"], fmt_tokens(inp)), (L["mini_out"], fmt_tokens(out)),
                  (L["mini_cached"], f"{cpct:.0f}%")]},
        {"lbl": L["card2_lbl"], "val": f"${r['total_cost']/1000:.1f}K", "suffix": "",
         "sub": L["card2_sub"],
         "mini": [(L["mini_top"], top_model), (L["mini_peak"], fmt_tokens(peak))]},
    ]
    for i, c in enumerate(cards):
        cx = X0 + i * (card_w + 14)
        lines.append(f'<rect x="{cx}" y="{card_y}" width="{card_w}" height="{card_h}" rx="10" fill="{PAL["card"]}" stroke="{PAL["border"]}" stroke-width="1"/>')
        # 琥珀色顶条（唯一强调色）
        lines.append(f'<rect x="{cx}" y="{card_y}" width="{card_w}" height="2.5" fill="url(#accg)" opacity="0.85"/>')
        text(cx + 16, card_y + 28, c["lbl"], 11, 600, "muted", spacing="1")
        vx = cx + 16
        text(vx, card_y + 62, c["val"], 28, 700, "text", num=True)
        if c["suffix"]:
            text(vx + len(c["val"]) * 16 + 10, card_y + 62, c["suffix"], 12, 400, "muted")
        text(cx + 16, card_y + 84, c["sub"], 11, 400, "muted")
        mx = cx + 16
        for label, val in c["mini"]:
            text(mx, card_y + 106, label, 10.5, 400, "muted")
            text(mx, card_y + 121, val, 11.5, 600, "text2", num=True)
            mx += 120

    # ===== BY TOOL bars（品牌色，功能数据色） =====
    y = card_y + card_h + 32
    text(X0, y, L["by_tool"], 11, 600, "muted", spacing="1")
    y += 20
    agents = r["by_agent"]
    total = r["total_tokens"]
    label_w = 72
    pct_w = 110
    track_x = X0 + label_w
    track_w = CW - label_w - pct_w - 12
    for name, tok in agents.items():
        if tok <= 0:
            continue
        pct = tok / total * 100
        bw = max(track_w * pct / 100, 2)
        color = AGENT_COLORS.get(name, "#8b949e")
        disp = "OpenCode" if name == "opencode" else name.capitalize()
        text(X0, y + 10, disp, 12, 500, "text2")
        lines.append(f'<rect x="{track_x}" y="{y}" width="{track_w}" height="10" rx="3" class="track"/>')
        lines.append(f'<rect x="{track_x}" y="{y}" width="{bw:.1f}" height="10" rx="3" fill="{color}" opacity="0.9"/>')
        text(X1, y + 10, f"{fmt_tokens(tok)} ({pct:.0f}%)", 11, 500, "muted", anchor="end", num=True)
        y += 26

    # ===== TOP MODELS chips =====
    y += 8
    text(X0, y, L["top_models"], 11, 600, "muted", spacing="1")
    y += 24
    chip_y, chip_x = y, X0
    for name, tok in r["models"][:8]:
        label = f"{name}  {fmt_tokens(tok)}"
        w = 14 + len(label) * 7.2
        if chip_x + w > X1:
            chip_x = X0
            chip_y += 32
        lines.append(f'<rect x="{chip_x:.1f}" y="{chip_y - 13}" width="{w:.1f}" height="24" rx="6" fill="{PAL["card"]}" stroke="{PAL["border"]}" stroke-width="1"/>')
        text(chip_x + 7, chip_y, label, 10.5, 500, "text2")
        chip_x += w + 8

    # ===== 底注 =====
    lines.append(f'<line x1="{X0}" y1="{H - 44}" x2="{X1}" y2="{H - 44}" stroke="{PAL["track"]}" stroke-width="1"/>')
    text(X0, H - 24, L["foot_cached"], 10.5, 400, "muted")
    text(X1, H - 24, f'{L["foot_updated"]} {now}', 10.5, 400, "faint", anchor="end")

    return "\n".join(lines) + "\n</svg>\n"


# ============ main ============
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出聚合 JSON")
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args()

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


if __name__ == "__main__":
    main()
