"""ทดสอบ risk.py + โหมดตรวจพอร์ต — รันด้วย:
  cd __FRIDAY_ROOT__/.claude/skills/portfolio-risk && \
  __FRIDAY_ROOT__/.venv/bin/python -m unittest discover -s tests -v
ข้อมูลสังเคราะห์ทั้งหมด ไม่แตะเน็ต
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import optimize as op  # noqa: E402
import risk as rk  # noqa: E402
from test_optimize import _bdays, synthetic_run  # noqa: E402

FORBIDDEN = ("ซื้อ", "ขาย")          # แนวทางลดความเสี่ยงใช้ได้แค่ เพิ่มน้ำหนัก/ลดน้ำหนัก/คง/เฝ้าระวัง


def with_liq(data, adv=None):
    """เติม liq ให้ทุกหุ้น · adv = {ticker: มูลค่าซื้อขายต่อวัน} (ราคาปิด 100 ทุกวัน)."""
    days = _bdays("2026-06-01", 63)
    for t in data["run"]["tickers"]:
        a = (adv or {}).get(t, 5_000_000_000)
        data["stocks"][t]["liq"] = [[d, "100.0", str(int(a / 100))] for d in days]
    return data


class HeatThresholds(unittest.TestCase):
    """ทุกเส้นแบ่งในตารางเกณฑ์: ค่าที่อยู่บนเส้นพอดีต้องตกไปฝั่งแย่กว่า (ตาม ≥ ในตาราง)."""

    def check(self, metric, cases):
        for v, want in cases:
            self.assertEqual(rk.heat_score(metric, v), want, f"{metric} {v}")

    def test_weight(self):
        self.check("weight", [("4.99", 1), ("5", 2), ("9.99", 2), ("10", 3), ("19.99", 3), ("20", 4),
                              ("29.99", 4), ("30", 5), ("100", 5)])

    def test_vol(self):
        self.check("vol", [("14.99", 1), ("15", 2), ("20", 3), ("25", 4), ("34.99", 4), ("35", 5)])

    def test_beta(self):
        self.check("beta", [("0.79", 1), ("0.8", 2), ("1.0", 3), ("1.2", 4), ("1.49", 4), ("1.5", 5), ("-0.3", 1)])

    def test_drawdown_negative(self):
        self.check("dd", [("-9.99", 1), ("-10", 2), ("-15", 3), ("-25", 4), ("-34.99", 4), ("-35", 5), ("0", 1)])

    def test_corr(self):
        self.check("corr", [("0.29", 1), ("0.30", 2), ("0.45", 3), ("0.60", 4), ("0.75", 5), ("-0.9", 1)])

    def test_rate_uses_magnitude(self):
        self.check("rate", [("1.99", 1), ("2", 2), ("-2", 2), ("-8", 5), ("7.99", 4)])

    def test_liquidity_low_is_worse(self):
        self.check("liq", [(1_000_000_000, 1), (999_999_999, 2), (100_000_000, 2), (99_999_999, 3),
                           (20_000_000, 3), (19_999_999, 4), (5_000_000, 4), (4_999_999, 5)])

    def test_missing_is_grey_not_green(self):
        self.assertIsNone(rk.heat_score("vol", None))
        self.assertEqual(rk.heat_color(None), rk.GREY)
        self.assertEqual(rk.cell("vol", None)["text"], "[ข้อมูลไม่พอ]")

    def test_colors_and_overall(self):
        self.assertEqual([rk.heat_color(s) for s in range(1, 6)], list(rk.HEAT_COLORS))
        cells = {"a": rk.cell("vol", "12"), "b": rk.cell("beta", "1.6"), "c": rk.cell("liq", None)}
        self.assertEqual(rk.overall(cells), 5)            # รวม = แย่สุด ไม่ใช่เฉลี่ย
        self.assertIsNone(rk.overall({"c": rk.cell("liq", None)}))

    def test_every_metric_has_five_ranges(self):
        for m, spec in rk.HEAT.items():
            self.assertEqual(len(spec["cuts"]), 4, m)
            self.assertEqual(len(spec["ranges"]), 5, m)


class Pieces(unittest.TestCase):
    def test_liquidity(self):
        rows = [["d", "10.0", "1000"]] * 25
        lq = rk.liquidity(rows)
        self.assertEqual(lq["adv"], Decimal("10000.0"))
        self.assertEqual(lq["last_close"], Decimal("10.0"))
        self.assertIsNone(rk.liquidity(rows[:5])["adv"])          # ไม่ถึง 20 วัน
        self.assertIsNone(rk.liquidity(None)["adv"])

    def test_anchor_tie_uses_index(self):
        self.assertEqual(rk.anchor_index([Decimal("60"), Decimal("40")]), 0)
        self.assertIsNone(rk.anchor_index([Decimal("50"), Decimal("50")]))

    def test_avg_pair_corr(self):
        C = np.array([[1, 0.5, 0.1], [0.5, 1, 0.3], [0.1, 0.3, 1]])
        self.assertAlmostEqual(rk.avg_pair_corr([1 / 3] * 3, C), 0.3, places=12)
        self.assertIsNone(rk.avg_pair_corr([1, 0, 0], C))       # ถือตัวเดียว ไม่มีคู่

    def test_concentration(self):
        c = rk.concentration(["A", "B", "C"], [Decimal("50.00"), Decimal("25.00"), Decimal("25.00")])
        self.assertEqual(c["top_ticker"], "A")
        self.assertEqual(c["effective_n"], Decimal("2.7"))      # 1/(0.25+0.0625+0.0625)
        self.assertEqual([(w["ticker"], w["level"]) for w in c["warnings"]], [("A", "hard"), ("B", "soft"), ("C", "soft")])

    def test_rebalance_band(self):
        rows = rk.rebalance_table(["A", "B", "C", "D"],
                                  [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("70")],
                                  [Decimal("12.01"), Decimal("12"), Decimal("7.99"), Decimal("68")])
        self.assertEqual([r["action"] for r in rows], ["เพิ่มน้ำหนัก", "คง", "ลดน้ำหนัก", "คง"])

    def test_money_format(self):
        self.assertEqual(rk.usd(Decimal("1234567.891")), "$1,234,567.89")
        self.assertEqual(rk.usd_compact(Decimal("2500000000")), "$2.50B")
        self.assertEqual(rk.usd_compact(Decimal("45000000")), "$45.00M")


class EvaluateMode(unittest.TestCase):
    def test_weights_mode_sums_and_rebalances(self):
        data = with_liq(synthetic_run())
        c = op.run(data, None, None, ("weights", op.parse_holdings(["AAA=20", "BBB=30", "CCC=50"], "weights")))
        self.assertEqual(c["mode"], "evaluate")
        self.assertEqual(c["w_disp"], [Decimal("20.00"), Decimal("30.00"), Decimal("50.00")])
        self.assertEqual(sum(c["w_disp"]), Decimal("100.00"))
        # สัดส่วนเป้าใช้ E(rp) ของพอร์ตปัจจุบัน → β เท่ากัน
        self.assertAlmostEqual(c["rebal_res"]["beta_p"], c["res"]["beta_p"], places=5)
        self.assertLessEqual(c["rebal_res"]["unsys_var"], c["res"]["unsys_var"] + 1e-12)
        self.assertEqual(c["corr_anchor"], "CCC")
        self.assertEqual(c["heat_rows"][2]["cells"]["corr"]["text"], "หุ้นหลัก")
        self.assertIn({"ticker": "CCC", "weight": Decimal("50.00"), "cap": rk.HARD_CAP, "level": "hard"},
                      c["conc"]["warnings"])
        h = op.build_html(c)
        self.assertIn("ปรับพอร์ต", h)
        self.assertNotIn("เฟสถัดไป", h)
        # JSON รุ่นเก่า (ไม่มีค่าเงิน/ดอกเบี้ย/อุตสาหกรรม) → ธงบอก ไม่หยุดงาน ไม่ระบายเขียว
        self.assertIsNone(c["fx"])
        self.assertIsNone(c["sectors"])
        self.assertIsNone(c["heat_port"]["rate"]["score"])
        self.assertTrue(any("DEXTHUS" in f for f in c["flags"]))

    def test_shares_equals_weights_when_prices_equal(self):
        # ราคาปิดทุกตัว = 100 → จำนวนหุ้น 2:3:5 ต้องได้น้ำหนักเดียวกับ 20/30/50%
        data = with_liq(synthetic_run())
        a = op.run(data, None, None, ("weights", op.parse_holdings(["AAA=20", "BBB=30", "CCC=50"], "weights")))
        b = op.run(data, None, None, ("shares", op.parse_holdings(["AAA=2", "BBB=3", "CCC=5"], "shares")))
        self.assertEqual(a["w_disp"], b["w_disp"])
        self.assertEqual(b["total_value"], Decimal("1000.0"))
        self.assertIsNone(a["total_value"])

    def test_weights_must_match_tickers_and_sum(self):
        data = with_liq(synthetic_run())
        with self.assertRaises(op.StopRun):
            op.run(data, None, None, ("weights", op.parse_holdings(["AAA=50", "BBB=50"], "weights")))
        with self.assertRaises(op.StopRun):
            op.run(data, None, None, ("weights", op.parse_holdings(["AAA=20", "BBB=30", "CCC=40"], "weights")))
        with self.assertRaises(op.StopRun):
            op.parse_holdings(["AAA=-5"], "weights")
        with self.assertRaises(op.StopRun):
            op.parse_holdings(["AAA"], "weights")

    def test_optimize_mode_still_needs_target(self):
        with self.assertRaises(op.StopRun):
            op.run(synthetic_run(), None, None)

    def test_liquidity_heat_and_hedge(self):
        data = with_liq(synthetic_run(), adv={"AAA": 3_000_000})
        c = op.run(data, None, None, ("weights", op.parse_holdings(["AAA=34", "BBB=33", "CCC=33"], "weights")))
        self.assertEqual(c["heat_rows"][0]["cells"]["liq"]["score"], 5)
        self.assertEqual(c["heat_port"]["liq"]["score"], 5)
        self.assertEqual(c["heat_port_overall"], 5)
        self.assertTrue(any(h["metric"] == "liq" for h in c["hedges"]))

    def test_hedge_text_has_no_trade_words(self):
        data = with_liq(synthetic_run(), adv={"AAA": 3_000_000})
        for hold in (["AAA=70", "BBB=20", "CCC=10"], ["AAA=10", "BBB=10", "CCC=80"]):
            c = op.run(data, None, None, ("weights", op.parse_holdings(hold, "weights")))
            self.assertTrue(c["hedges"])
            for h in c["hedges"]:
                for w in FORBIDDEN:
                    self.assertNotIn(w, h["text"])

    def test_html_self_contained_and_colors_match(self):
        data = with_liq(synthetic_run())
        for c in (op.run(data, 0.10, None),
                  op.run(data, None, None, ("weights", op.parse_holdings(["AAA=20", "BBB=30", "CCC=50"], "weights")))):
            h = op.build_html(c)
            self.assertNotIn("<script", h.lower())
            self.assertNotIn("http://", h)
            self.assertNotIn("https://", h)
            self.assertIn("อภิธานศัพท์", h)
            self.assertIn("ความจริงที่ต้องบอกตรง ๆ", h)
            for r in c["heat_rows"]:
                for cl in r["cells"].values():
                    if cl["score"] is not None:
                        self.assertIn(f"background:{rk.heat_color(cl['score'])}'>{cl['text']}<", h)

    def test_cli_weights_and_shares_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.json"
            inp.write_text(json.dumps(with_liq(synthetic_run())))
            base = [sys.executable, str(Path(op.__file__)), "--in", str(inp), "--out", str(Path(tmp) / "o.html")]
            both = subprocess.run(base + ["--weights", "AAA=50", "BBB=30", "CCC=20", "--shares", "AAA=1"],
                                  capture_output=True, text=True)
            self.assertEqual(both.returncode, 2)                      # argparse ปฏิเสธใช้คู่กัน
            ok = subprocess.run(base + ["--shares", "AAA=2", "BBB=3", "CCC=5"], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            s = json.loads(ok.stdout)
            self.assertEqual(s["mode"], "evaluate")
            self.assertEqual(s["total_value_usd"], "$1,000.00")
            self.assertTrue(re.match(r"^\d · ", s["risk_level"]))


def with_macro(data, sectors=None, fx=Decimal("35.00")):
    """เติมค่าเงิน (คงที่ = fx) · ดอกเบี้ย (random walk) · อุตสาหกรรม ให้ JSON สังเคราะห์."""
    rng = np.random.default_rng(3)
    days = _bdays("2020-01-01", 1800)
    data["fx"] = {"series_id": "DEXTHUS", "rows": [[d, str(fx)] for d in days], "as_of": days[-1]}
    d3 = sorted(data["stocks"][data["run"]["tickers"][0]]["prices"])
    y = 4 + np.cumsum(rng.normal(0, 0.05, len(d3)))
    data["rates"] = {"series_id": "DGS10", "rows": [[r[0], f"{v:.2f}"] for r, v in zip(d3, y)], "as_of": d3[-1][0]}
    data["sectors"] = {"map": sectors if sectors is not None else
                       {"AAA": {"sector": "Technology", "industry": "Software"},
                        "BBB": {"sector": "Technology", "industry": "Semis"},
                        "CCC": {"sector": "Health Care", "industry": "Pharma"}},
                       "source": "nasdaq-screener", "source_tier": 3, "as_of": d3[-1][0]}
    return data


class Phase2Pieces(unittest.TestCase):
    def test_sector_weights_and_caps(self):
        g = rk.sector_weights(["A", "B", "C", "D"],
                              [Decimal("30.00"), Decimal("15.00"), Decimal("35.00"), Decimal("20.00")],
                              {"A": {"sector": "Tech"}, "B": {"sector": "Tech"}, "C": {"sector": "Energy"}})
        rows = {r["sector"]: r for r in g["rows"]}
        self.assertEqual(rows["Tech"]["weight"], Decimal("45.00"))
        self.assertEqual(rows["Tech"]["level"], "hard")                     # 45 พอดี = เตือนแรง
        self.assertEqual(rows["Energy"]["level"], "soft")                   # 35 พอดี = เตือน
        self.assertEqual(rows[rk.UNKNOWN_SECTOR]["tickers"], ["D"])        # ETF/หาไม่เจอ
        self.assertIsNone(rows[rk.UNKNOWN_SECTOR]["level"])                 # ไม่ใช้เพดาน
        self.assertEqual(g["rows"][-1]["sector"], rk.UNKNOWN_SECTOR)
        self.assertEqual(sum(r["weight"] for r in g["rows"]), Decimal("100.00"))

    def test_value_at_forward_fill_limit(self):
        pts = rk.series_points([["2024-01-02", "35.10"], ["2024-01-03", "."], ["2024-01-05", "35.30"]])
        self.assertEqual(len(pts), 2)                                       # "." ของ FRED ถูกข้าม
        self.assertEqual(rk.value_at(pts, "2024-01-04"), Decimal("35.10"))
        self.assertEqual(rk.value_at(pts, "2024-01-12"), Decimal("35.30"))  # ห่าง 7 วันพอดี ยังใช้ได้
        self.assertIsNone(rk.value_at(pts, "2024-01-13"))                   # เกิน 7 วัน
        self.assertIsNone(rk.value_at(pts, "2023-12-31"))                   # ก่อนมีข้อมูล

    def test_fx_scenarios(self):
        sc = rk.fx_scenarios(Decimal("36.00"), Decimal("1000"))
        self.assertEqual([x["shock"] for x in sc], [-10, -5, 0, 5, 10])
        self.assertEqual(sc[0]["rate"], Decimal("32.40"))
        self.assertEqual(sc[2]["value_thb"], Decimal("36000.00"))
        self.assertEqual(sc[4]["value_thb"], Decimal("39600.00"))
        self.assertIsNone(rk.fx_scenarios(Decimal("36"), None)[0]["value_thb"])   # โหมด % ไม่มีมูลค่า

    def test_fx_path_converts_with_actual_rate(self):
        dates = _bdays("2022-01-03", 3)
        pts = rk.series_points([[dates[0], "33.00"], [dates[2], "36.30"]])
        r = rk.fx_path(dates, [1.0, 0.9, 1.0], pts)
        self.assertAlmostEqual(r["ret_usd"], 0.0)
        self.assertAlmostEqual(r["ret_thb"], 0.10)                          # บาทอ่อน 10% → เป็นบาทได้ +10%
        self.assertAlmostEqual(r["max_dd_thb"], -0.10)                      # วันกลางใช้ค่าเงิน 33 (forward-fill)

    def test_rate_regression_recovers_coefficient(self):
        rng = np.random.default_rng(5)
        dates = _bdays("2023-01-02", 756)
        dy = rng.normal(0, 0.05, len(dates) - 1)
        y = np.concatenate([[4.0], 4.0 + np.cumsum(dy)])
        b = np.array([-0.05, 0.02])
        P = 100 * np.cumprod(np.vstack([np.ones(2), 1 + np.outer(dy, b)]), axis=0)
        rows = [[d, f"{v:.6f}"] for d, v in zip(dates, y)]
        rs = rk.rate_sensitivity(dates, P, rows, [0.5, 0.5])
        self.assertGreaterEqual(rs["weeks"], rk.RATE_MIN_WEEKS)
        self.assertAlmostEqual(rs["stocks"][0]["b"], -0.05, delta=0.002)
        self.assertAlmostEqual(rs["stocks"][1]["b"], 0.02, delta=0.002)
        self.assertGreater(rs["stocks"][0]["r2"], 0.99)
        self.assertAlmostEqual(rs["portfolio"]["b"], 0.5 * rs["stocks"][0]["b"] + 0.5 * rs["stocks"][1]["b"], places=10)
        self.assertEqual(rk.signed_pct(rk.pct_value(rs["stocks"][1]["b"], 0)), "+2%")

    def test_rate_needs_enough_weeks(self):
        dates = _bdays("2023-01-02", 100)                                   # ~20 สัปดาห์
        P = np.ones((100, 1)) * 100
        rs = rk.rate_sensitivity(dates, P, [[d, "4.0"] for d in dates], [1.0])
        self.assertIsNone(rs["portfolio"])
        self.assertEqual(rs["stocks"], [None])


class Phase2EndToEnd(unittest.TestCase):
    def run_eval(self, hold, kind="weights", **kw):
        data = with_macro(with_liq(synthetic_run()), **kw)
        return op.run(data, None, None, (kind, op.parse_holdings(hold, kind)))

    def test_sections_filled_and_sector_hedge(self):
        c = self.run_eval(["AAA=30", "BBB=30", "CCC=40"])                  # Tech 60% → เตือนแรง
        self.assertEqual(c["sectors"]["warnings"][0]["sector"], "Technology")
        self.assertEqual(c["sectors"]["warnings"][0]["level"], "hard")
        self.assertTrue(any(h["metric"] == "sector" for h in c["hedges"]))
        self.assertIsNotNone(c["heat_port"]["rate"]["score"])
        self.assertEqual(c["fx"]["rate"], Decimal("35.00"))
        # ค่าเงินคงที่ → ผลตอบแทนเป็นบาท = เป็นดอลลาร์ ทุกช่วง
        for w in c["fx"]["windows"]:
            self.assertAlmostEqual(w["ret_thb"], w["ret_usd"], places=12)
        h = op.build_html(c)
        for txt in ("Technology", "Health Care", "DGS10", "DEXTHUS", "บาทแข็ง (ดอลลาร์อ่อน) 10%"):
            self.assertIn(txt, h)
        self.assertNotIn("เฟสถัดไป", h)
        for hd in c["hedges"]:
            for w in FORBIDDEN:
                self.assertNotIn(w, hd["text"])

    def test_shares_mode_shows_baht_value(self):
        c = self.run_eval(["AAA=2", "BBB=3", "CCC=5"], kind="shares")
        self.assertEqual(c["fx"]["scenarios"][2]["value_thb"], Decimal("35000.00"))   # $1,000 × 35
        s = op.summary(c, Path("x.html"))
        self.assertEqual(s["total_value_thb"], "฿35,000.00")
        self.assertIn("มูลค่าพอร์ต (บาท)", op.build_html(c))

    def test_unknown_sector_not_capped(self):
        c = self.run_eval(["AAA=10", "BBB=10", "CCC=80"], sectors={})      # หาไม่เจอทุกตัว (เช่น ETF ล้วน)
        self.assertEqual([g["sector"] for g in c["sectors"]["rows"]], [rk.UNKNOWN_SECTOR])
        self.assertEqual(c["sectors"]["warnings"], [])

    def test_rate_cells_colored_in_html(self):
        c = self.run_eval(["AAA=20", "BBB=30", "CCC=50"])
        h = op.build_html(c)
        for r in c["heat_rows"]:
            cl = r["cells"]["rate"]
            self.assertIsNotNone(cl["score"])
            self.assertIn(f"background:{rk.heat_color(cl['score'])}'>{cl['text']}<", h)


if __name__ == "__main__":
    unittest.main()
