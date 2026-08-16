"""Regression tests for token-stats.py — pin observable behavior before slop removal.

Zero third-party deps (unittest only), consistent with the script's no-dependency design.
Pure functions are tested directly; file/network boundaries are patched with temp files.
"""
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

# token-stats.py (hyphen) is not a valid module name — load by file path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SPEC = importlib.util.spec_from_file_location(
    "token_stats", os.path.join(os.path.dirname(_HERE), "token-stats.py"))
token_stats = importlib.util.module_from_spec(_SPEC)
_sys_argv = sys.argv
sys.argv = ["token-stats.py"]  # argparse only touches argv inside main(); keep import side-effect free
_SPEC.loader.exec_module(token_stats)
sys.argv = _sys_argv


class TestFmtTokens(unittest.TestCase):
    def test_scales(self):
        self.assertEqual(token_stats.fmt_tokens(1.5e9), "1.5B")
        self.assertEqual(token_stats.fmt_tokens(2_300_000), "2.3M")
        self.assertEqual(token_stats.fmt_tokens(5_000), "5K")
        self.assertEqual(token_stats.fmt_tokens(999), "999")


class TestEsc(unittest.TestCase):
    def test_escapes_xml_chars(self):
        self.assertEqual(token_stats.esc('<a & b > c'), '&lt;a &amp; b &gt; c')
        self.assertEqual(token_stats.esc("plain"), "plain")


class TestNiceMax(unittest.TestCase):
    def test_rounds_up_to_half_billion(self):
        self.assertEqual(token_stats._nice_max(0), 1e9)
        self.assertEqual(token_stats._nice_max(4.14e9), 4.5e9)
        self.assertEqual(token_stats._nice_max(5e9), 5e9)


class TestPriceKey(unittest.TestCase):
    def test_local_fallback_mapping(self):
        self.assertEqual(token_stats.price_key("minimax-m2.7"), "minimax-m2.7(L)")
        self.assertEqual(token_stats.price_key("hy3"), "hy3(L)")
        self.assertEqual(token_stats.price_key("auto"), "auto(L)")

    def test_alias_mapping(self):
        self.assertEqual(token_stats.price_key("codex-auto-review"), "gpt-5.6")
        self.assertEqual(token_stats.price_key("glm-5-turbo"), "glm-5.1")
        self.assertEqual(token_stats.price_key("glm-5.2-x"), "glm-5.2")

    def test_unknown_passthrough_lowercased(self):
        self.assertEqual(token_stats.price_key("GPT-5.6"), "gpt-5.6")
        self.assertEqual(token_stats.price_key(None), "")


class TestPriceFor(unittest.TestCase):
    def test_local_pricing_per_token(self):
        p = token_stats.price_for({}, "minimax-m2.7")
        self.assertEqual(p, (0.30 / 1e6, 1.20 / 1e6, 0.03 / 1e6, 0.0))

    def test_unknown_model_returns_none(self):
        self.assertIsNone(token_stats.price_for({}, "no-such-model"))

    def test_litellm_entry_with_default_cache_rates(self):
        idx = {"gpt-5.6": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}}
        self.assertEqual(token_stats.price_for(idx, "gpt-5.6"),
                         (1e-6, 2e-6, 1e-7, 1e-6))  # read = 10% input, write = input

    def test_litellm_explicit_cache_rates_win(self):
        idx = {"m": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6,
                     "cache_read_input_token_cost": 3e-7, "cache_creation_input_token_cost": 4e-7}}
        self.assertEqual(token_stats.price_for(idx, "m"), (1e-6, 2e-6, 3e-7, 4e-7))


class TestNormalizeRow(unittest.TestCase):
    def test_legacy_codex_subtracts_cached_from_input(self):
        b = {"source": "codex", "input_tokens": 100, "cached_input_tokens": 40,
             "output_tokens": 50, "total_tokens": 150}
        out = token_stats._normalize_row(b)
        self.assertEqual(out["input_tokens"], 60)
        self.assertEqual(out["total_tokens"], 150)

    def test_modern_codex_row_unchanged(self):
        b = {"source": "codex", "input_tokens": 100, "cached_input_tokens": 40,
             "output_tokens": 50, "total_tokens": 190}  # total != input+output
        out = token_stats._normalize_row(b)
        self.assertEqual(out["input_tokens"], 100)

    def test_cursor_fills_billable_when_missing(self):
        b = {"source": "cursor", "total_tokens": 100, "billable_total_tokens": 60}
        out = token_stats._normalize_row(b)
        self.assertEqual(out["billable_total_tokens"], 100)

    def test_cursor_full_billable_unchanged(self):
        b = {"source": "cursor", "total_tokens": 100, "billable_total_tokens": 120}
        out = token_stats._normalize_row(b)
        self.assertEqual(out["billable_total_tokens"], 120)


class TestMedian(unittest.TestCase):
    def test_odd(self):
        self.assertEqual(token_stats._median([3, 1, 2]), 2)

    def test_even(self):
        self.assertEqual(token_stats._median([1, 2, 3, 4]), 2.5)


PRICING = {"gpt-5.6": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}}


class TestLoadTracker(unittest.TestCase):
    def _run(self, lines):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(lines) + "\n")
            path = f.name
        try:
            with mock.patch.object(token_stats, "TRACKER_QUEUE", path), \
                 mock.patch.object(token_stats, "get_pricing", return_value=PRICING):
                return token_stats.load_tracker()
        finally:
            os.unlink(path)

    def test_aggregates_dedup_last_wins_and_prices(self):
        r = self._run([
            # legacy codex row: input includes cached read
            json.dumps({"source": "codex", "model": "gpt-5.6", "hour_start": "2026-08-01T01:00:00+08:00",
                        "input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 50,
                        "total_tokens": 150, "conversation_count": 2}),
            # same key → last wins
            json.dumps({"source": "codex", "model": "gpt-5.6", "hour_start": "2026-08-01T01:00:00+08:00",
                        "input_tokens": 200, "cached_input_tokens": 0, "output_tokens": 50,
                        "total_tokens": 250, "conversation_count": 1}),
            # unknown model: counted but unpriced
            json.dumps({"source": "opencode", "model": "deepseek-v4-flash",
                        "hour_start": "2026-08-02T10:00:00Z",
                        "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                        "conversation_count": 3}),
            "not json\n",
        ])
        self.assertEqual(r["total_tokens"], 265)
        self.assertEqual(r["input"], 210)
        self.assertEqual(r["output"], 55)
        self.assertEqual(r["cached"], 0)
        self.assertEqual(r["cc"], 0)
        self.assertEqual(r["conversations"], 4)
        self.assertAlmostEqual(r["cost"], 0.0003)
        self.assertEqual(r["by_agent"], {"codex": 250, "opencode": 15})
        self.assertEqual(r["by_model"], {"gpt-5.6": 250, "deepseek-v4-flash": 15})
        self.assertEqual(r["by_model_cost"], {"gpt-5.6": 0.0003})
        self.assertEqual(r["peak_day"], "2026-08-01")
        self.assertEqual(r["peak_day_tokens"], 250)
        self.assertEqual(r["by_day"], {"2026-08-01": 250, "2026-08-02": 15})
        self.assertEqual(r["period_start"], "2026-08-01T01:00+08:00")

    def test_billable_total_tokens_preferred(self):
        r = self._run([
            json.dumps({"source": "codex", "model": "gpt-5.6", "hour_start": "2026-08-01T00:00:00+08:00",
                        "input_tokens": 10, "output_tokens": 10, "total_tokens": 20,
                        "billable_total_tokens": 18, "conversation_count": 1}),
        ])
        self.assertEqual(r["total_tokens"], 18)


class TestLoadSessions(unittest.TestCase):
    def _run(self, lines):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(lines) + "\n")
            path = f.name
        try:
            with mock.patch.object(token_stats, "SESSION_QUEUE", path):
                return token_stats.load_sessions()
        finally:
            os.unlink(path)

    def test_median_edits_and_first_pass(self):
        r = self._run([
            json.dumps({"edit_turns": 2, "first_pass": True, "cost_per_edit": 0.5, "tokens_per_edit": 100}),
            json.dumps({"edit_turns": 0, "first_pass": False, "cost_per_edit": None, "tokens_per_edit": None}),
            json.dumps({"edit_turns": 3, "first_pass": False, "cost_per_edit": 1.5, "tokens_per_edit": 300}),
            "bad json\n",
        ])
        self.assertEqual(r["sessions"], 3)
        self.assertEqual(r["edit_sessions"], 2)
        self.assertEqual(r["first_pass"], 1)
        self.assertEqual(r["cost_per_edit"], 1.0)
        self.assertEqual(r["tokens_per_edit"], 200)

    def test_empty_file_returns_none(self):
        self.assertIsNone(self._run([]))


class TestLoadOutcomes(unittest.TestCase):
    def _run(self, lines):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write("\n".join(lines) + "\n")
            path = f.name
        try:
            with mock.patch.object(token_stats, "OUTCOMES_FILE", path):
                return token_stats.load_outcomes()
        finally:
            os.unlink(path)

    def test_per_model_counts(self):
        r = self._run([
            json.dumps({"model": "gpt-5.6", "accepted": True}),
            json.dumps({"model": "gpt-5.6", "accepted": False}),
            json.dumps({"model": "deepseek-v4-flash", "accepted": True}),
            "bad json\n",
        ])
        self.assertEqual(r["outcomes"], 3)
        self.assertEqual(r["accepted"], 2)
        self.assertEqual(r["per_model"], {"gpt-5.6": [1, 2], "deepseek-v4-flash": [1, 1]})


class TestAggregate(unittest.TestCase):
    def test_tracker_path_merges_models_and_adds_legacy_cost(self):
        tr = {
            "total_tokens": 1000, "cost": 50.0, "conversations": 10,
            "by_agent": {"opencode": 700, "codex": 300},
            "by_model": {"minimax-m2.7": 400, "MiniMax-M2.7": 600, "gpt-5.6": 0},
            "by_model_cost": {}, "period_start": "2026-08-01T01:00",
            "peak_day": "2026-08-01", "peak_day_tokens": 400,
            "input": 800, "output": 150, "cached": 50, "cc": 0,
            "by_day": {"2026-08-01": 700, "2026-08-02": 300},
        }
        with mock.patch.object(token_stats, "load_tracker", return_value=tr), \
             mock.patch.object(token_stats, "load_sessions", return_value=None), \
             mock.patch.object(token_stats, "load_outcomes", return_value=None):
            r = token_stats.aggregate()
        self.assertEqual(r["total_tokens"], 1000)
        self.assertEqual(r["total_cost"], 50.0 + 1348.07)
        self.assertEqual(r["conversations"], 10)
        self.assertEqual(r["by_agent"], {"OpenCode": 700, "Codex": 300})
        self.assertEqual(r["models"], [("MiniMax M2.7", 1000), ("GPT-5.6", 0)])
        self.assertEqual(r["top_model"], "MiniMax M2.7")
        self.assertEqual(r["daily"], [("2026-08-01", 700), ("2026-08-02", 300)])
        self.assertEqual(r["period"], f"2026-08-01 ~ {datetime.date.today().isoformat()}")
        self.assertEqual(r["stats"], {"input": 800, "output": 150, "cached": 50, "cc": 0})

    def test_qpd_rows_sorted_by_cost_per(self):
        tr = {"total_tokens": 100, "cost": 0.0, "conversations": 0, "by_agent": {},
              "by_model": {}, "by_model_cost": {"gpt-5.6": 10.0, "deepseek-v4-flash": 5.0},
              "period_start": None, "peak_day": None, "peak_day_tokens": 0,
              "input": 0, "output": 0, "cached": 0, "cc": 0, "by_day": {}}
        qpd = {"outcomes": 2, "accepted": 2,
               "per_model": {"deepseek-v4-flash": [2, 2], "gpt-5.6": [1, 2]}}
        with mock.patch.object(token_stats, "load_tracker", return_value=tr), \
             mock.patch.object(token_stats, "load_sessions", return_value=None), \
             mock.patch.object(token_stats, "load_outcomes", return_value=qpd):
            r = token_stats.aggregate()
        rows = r["qpd"]["rows"]
        self.assertEqual([x["model"] for x in rows], ["DeepSeek V4 Flash", "GPT-5.6"])
        self.assertEqual(rows[0]["rate"], 1.0)
        self.assertEqual(rows[0]["cost_per"], 5.0 / 2)


class TestSvg(unittest.TestCase):
    MIN_R = {
        "total_tokens": 123456, "total_cost": 1398.07, "conversations": 100,
        "by_agent": {"opencode": 100000, "codex": 23456},
        "by_model": {"gpt-5.6": 100000},
        "models": [("GPT-5.6", 100000)],
        "period_start": "2026-03", "peak_day": "2026-08-01", "peak_day_tokens": 50000,
        "daily": [("2026-08-01", 50000), ("2026-08-02", 40000)],
        "stats": {"input": 80000, "output": 15000, "cached": 20000, "cc": 5000},
        "top_model": "GPT-5.6",
    }

    def _today_window(self):
        today = datetime.date.today()
        r = dict(self.MIN_R)
        r["daily"] = [(today.isoformat(), 50000), ((today - datetime.timedelta(days=1)).isoformat(), 40000)]
        return r

    def test_svg_card_well_formed_and_localized(self):
        for dark, zh, needle in ((True, False, "AI token usage"),
                                 (False, False, "AI token usage"),
                                 (True, True, "AI Token 用量"),
                                 (False, True, "AI Token 用量")):
            svg = token_stats.svg_card(self._today_window(), dark=dark, zh=zh)
            root = ET.fromstring(svg)
            self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
            self.assertIn(needle, svg)
            self.assertIn("123K", svg)
            self.assertIn("$1.4K", svg)

    def test_dark_light_palettes_differ(self):
        dark = token_stats.svg_card(self._today_window(), dark=True)
        light = token_stats.svg_card(self._today_window(), dark=False)
        self.assertNotEqual(dark, light)
        self.assertIn("#0d1117", dark)
        self.assertIn("#ffffff", light)

    def test_trend_section_contains_bars_avg_line_and_peak(self):
        r = self._today_window()
        out = token_stats.trend_section(r, {"track": "#000", "faint": "#000", "acc": "#000",
                                            "acc_hi": "#000", "bg": "#000", "split": ["#a"] * 4,
                                            "dark": True},
                                        {"trend": "T", "lg_bar": "b", "lg_avg": "a", "lg_peak": "p",
                                         "c_in": "i", "c_cached": "c", "c_out": "o", "c_cc": "w"})
        joined = "\n".join(out)
        self.assertIn("<polyline", joined)
        self.assertIn("<rect", joined)
        self.assertIn("50K", joined)   # 峰值日数值
        self.assertIn("· ", joined)      # 拆分明细占比


if __name__ == "__main__":
    unittest.main()
