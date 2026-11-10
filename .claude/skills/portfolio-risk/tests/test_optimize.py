"""ทดสอบ optimize.py — รันด้วย:
  cd __FRIDAY_ROOT__/.claude/skills/portfolio-risk && \
  __FRIDAY_ROOT__/.venv/bin/python -m unittest discover -s tests -v
ใช้ unittest (built-in) เพราะ .venv ไม่มี pytest และ §8 ห้ามเติมไลบรารี
"""
import json
import math
import sys
import unittest
from decimal import Decimal
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import optimize as op  # noqa: E402


class TextbookFormulas(unittest.TestCase):
    def test_8_8_expected_return(self):
        # ตำรา 8.8: E(rA)=12% E(rB)=16% w=0.5/0.5 → 14% [ตามแหล่ง]
        self.assertAlmostEqual(op.portfolio_expected([0.5, 0.5], [0.12, 0.16]), 0.14, places=12)

    def test_8_9_portfolio_sigma(self):
        # ตำรา 8.9: σA=10% σB=20% wA=0.75 wB=0.25 ρ=+0.5 → 10.90% (คิดทวน 0.10897)
        sa, sb, rho = 0.10, 0.20, 0.5
        cov = np.array([[sa * sa, rho * sa * sb], [rho * sa * sb, sb * sb]])
        s = op.portfolio_sigma([0.75, 0.25], cov)
        self.assertAlmostEqual(s, math.sqrt(0.011875), places=12)
        self.assertEqual(op.pct(s), "10.90%")

    def test_capm(self):
        self.assertAlmostEqual(op.capm(0.04, 1.5, 0.10), 0.13, places=12)


class Solver(unittest.TestCase):
    def test_two_uncorrelated_no_binding_target(self):
        # residual ไม่สัมพันธ์กัน เป้าไม่บังคับ → w₁ = σ²ε₂/(σ²ε₁+σ²ε₂)
        v1, v2 = 0.04, 0.09
        w = op.min_unsys([1.0, 1.0], np.diag([v1, v2]), beta_target=0.5)
        self.assertAlmostEqual(w[0], v2 / (v1 + v2), places=6)

    def test_binding_target_hits_beta_exactly(self):
        beta = np.array([0.6, 0.9, 1.4])
        cov_e = np.diag([0.01, 0.02, 0.08])
        rf, rm, target = 0.04, 0.10, 0.11          # β เป้า = 7/6 ≈ 1.1667
        res = op.plan_portfolio(beta, cov_e, rf, rm, target)
        w = res["weights"]
        self.assertTrue(res["feasible"])
        self.assertAlmostEqual(w.sum(), 1.0, places=9)
        self.assertTrue((w >= 0).all())
        self.assertAlmostEqual(float(w @ beta), (target - rf) / (rm - rf), places=6)
        self.assertGreaterEqual(res["e_p"], target - 1e-7)

    def test_target_above_beta_max_is_infeasible(self):
        beta = np.array([0.8, 1.2])
        res = op.plan_portfolio(beta, np.diag([0.02, 0.03]), 0.04, 0.10, 0.40)
        self.assertFalse(res["feasible"])
        self.assertAlmostEqual(res["e_max"], 0.04 + 1.2 * 0.06, places=12)
        self.assertAlmostEqual(res["shortfall"], 0.40 - res["e_max"], places=12)
        self.assertAlmostEqual(res["weights"][1], 1.0, places=6)   # พอร์ต E สูงสุด = หุ้น β สูงสุดล้วน

    def test_market_not_above_rf_stops(self):
        with self.assertRaises(op.StopRun):
            op.plan_portfolio(np.array([1.0, 1.1]), np.eye(2) * 0.01, 0.05, 0.05, 0.08)
        with self.assertRaises(op.StopRun):
            op.check_market(0.05, 0.03)


class Estimation(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        T = 756
        self.rm = rng.normal(0.0004, 0.01, T)
        self.beta_true = np.array([0.7, 1.0, 1.5])
        eps = rng.normal(0, 0.012, (T, 3))
        eps[:, 1] += 0.6 * eps[:, 0]          # หุ้นอุตสาหกรรมเดียวกัน → residual สัมพันธ์กัน
        self.R = self.rm[:, None] * self.beta_true + eps
        self.est = op.estimate(self.R, self.rm)

    def test_decomposition(self):
        e = self.est
        np.testing.assert_allclose(e["cov"], np.outer(e["beta"], e["beta"]) * e["var_m"] + e["cov_e"], atol=1e-12)

    def test_residual_symmetric_and_full(self):
        ce = self.est["cov_e"]
        np.testing.assert_allclose(ce, ce.T)
        self.assertGreater(op.corr_from_cov(ce)[0, 1], 0.3)   # เก็บ off-diagonal ไว้จริง

    def test_beta_recovered(self):
        np.testing.assert_allclose(self.est["beta"], self.beta_true, atol=0.1)


class Helpers(unittest.TestCase):
    def test_largest_remainder_sums_to_100(self):
        for w in ([1 / 3] * 3, [0.123456, 0.3, 0.576544], [1.0], [1 / 7] * 7):
            r = op.round_weights(w)
            self.assertEqual(sum(r), Decimal("100.00"))

    def test_history_gaps(self):
        idx = [f"2023-01-{d:02d}" for d in range(2, 32)]
        maps = {"OLD": {d: 1.0 for d in idx},
                "IPO": {d: 1.0 for d in idx[10:]},
                "HOLE": {d: 1.0 for d in idx[::2]}}
        g = op.history_gaps(maps, idx)
        self.assertNotIn("OLD", g)
        self.assertIn("IPO", g)
        self.assertIn("HOLE", g)

    def test_drawdown(self):
        self.assertAlmostEqual(float(op.drawdown([1, 2, 1, 3]).min()), -0.5)


def _series(dates, rets, p0=100.0):
    p, out = p0, [[dates[0], p0]]
    for d, r in zip(dates[1:], rets):
        p *= 1 + r
        out.append([d, p])
    return out


def _bdays(start: str, n: int) -> list[str]:
    from datetime import date, timedelta
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def synthetic_run(tickers=("AAA", "BBB", "CCC"), missing_stress=()):
    """JSON หน้าตาเดียวกับที่ fetch.py เขียน — ไม่แตะเน็ต."""
    rng = np.random.default_rng(11)
    betas = {"AAA": 0.7, "BBB": 1.0, "CCC": 1.4}

    def block(dates, skip=()):
        rm = rng.normal(0.0004, 0.01, len(dates) - 1)
        stocks = {t: ({"error": "NO_DATA", "message": "x"} if t in skip else
                      {"prices": _series(dates, betas[t] * rm + rng.normal(0, 0.012, len(rm)))})
                  for t in tickers}
        return {"prices": _series(dates, rm)}, stocks

    d3 = _bdays("2023-09-25", 756)
    idx, stocks = block(d3)
    stress = {}
    for key, s, n in (("covid_2020", "2020-02-03", 63), ("y2022", "2022-01-03", 251)):
        si, ss = block(_bdays(s, n), missing_stress)
        stress[key] = {"label": key, "start": s, "end_exclusive": s, "index": si, "stocks": ss}
    return {"run": {"as_of": d3[-1], "tickers": list(tickers)},
            "index": {"ticker": "^GSPC", "fallback": False, **idx, "as_of": d3[-1]},
            "stocks": stocks, "stress": stress,
            "market": {"ticker": "SPY", "years": 20, "first": ["2006-09-25", 100.0],
                       "last": ["2026-09-21", 800.0], "rows": 5000},
            "rf": {"series_id": "DTB3", "date": "2026-09-18", "value_pct": "4.0"}}


class EndToEnd(unittest.TestCase):
    def test_run_and_html(self):
        c = op.run(synthetic_run(), 0.10, None)
        self.assertEqual(sum(c["w_disp"]), Decimal("100.00"))
        self.assertGreaterEqual(c["res"]["e_p"], 0.10 - 1e-7)
        h = op.build_html(c)
        self.assertIn("in-sample", h)
        self.assertIn("คนละช่วงเวลา", h)

    def test_stress_ignores_weight_shown_as_zero(self):
        data = synthetic_run(missing_stress=("CCC",))
        w = np.array([0.6, 0.4, 1e-9])                 # CCC แสดงเป็น 0.00% → ไม่นับว่าถืออยู่
        s = op.stress_block(data["stress"]["covid_2020"], data["run"]["tickers"], w)
        self.assertIsNotNone(s["portfolio"])
        w[2] = 0.2                                     # CCC ถืออยู่จริงแต่ขาดข้อมูล → ไม่คำนวณพอร์ต
        s = op.stress_block(data["stress"]["covid_2020"], data["run"]["tickers"], w / w.sum())
        self.assertIsNone(s["portfolio"])

    def test_bad_target_exits_2(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in.json"
            inp.write_text(json.dumps(synthetic_run()))
            r = subprocess.run([sys.executable, str(Path(op.__file__)), "--in", str(inp),
                                "--target", "10%", "--out", str(Path(tmp) / "o.html")],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.startswith("STOP:"))


if __name__ == "__main__":
    unittest.main()


def _truncate(data, ticker, keep_from):
    """ตัดราคาของ ticker ให้เริ่ม keep_from (จำลองหุ้นเพิ่งเข้าตลาด) ทั้งหน้าต่างหลักและ stress."""
    p = data["stocks"][ticker]["prices"]
    data["stocks"][ticker]["prices"] = [r for r in p if r[0] >= keep_from]
    for sb in data["stress"].values():
        sb["stocks"][ticker] = {"error": "NO_DATA", "message": "x"}
    return data


class ShortHistory(unittest.TestCase):
    def test_short_without_flag_stops(self):
        d = _truncate(synthetic_run(), "CCC", _bdays("2023-09-25", 756)[300])
        with self.assertRaises(op.StopRun) as e:
            op.run(d, 0.10, None)
        self.assertIn("--short-history", str(e.exception))

    def test_short_with_flag_runs(self):
        d3 = _bdays("2023-09-25", 756)
        d = _truncate(synthetic_run(), "CCC", d3[300])
        c = op.run(d, 0.10, None, short_ok=["CCC"])
        self.assertEqual(c["short_history"], {"CCC": d3[300]})
        self.assertEqual(c["dates"][0], d3[300])                      # ช่วงร่วมเริ่มตามตัวที่สั้นสุด
        self.assertAlmostEqual(float(np.sum(c["res"]["weights"])), 1.0, places=9)
        self.assertGreaterEqual(float(np.linalg.eigvalsh(c["cov_e"]).min()), -1e-12)
        self.assertTrue(any("ประวัติไม่ครบ 3 ปี" in f for f in c["flags"]))
        self.assertIsNone(c["stress"]["covid_2020"]["portfolio"])     # CCC ไม่มีราคาช่วงนั้น
        op.build_html(c)

    def test_pairwise_matches_full_when_no_gap(self):
        d = synthetic_run()
        maps = {t: op.to_map(d["stocks"][t]["prices"]) for t in d["run"]["tickers"]}
        idx = op.to_map(d["index"]["prices"])
        dates, P, pm = op.align(maps, idx, d["run"]["tickers"])
        full = op.estimate(op.simple_returns(P), op.simple_returns(pm))
        pw = op.estimate_pairwise(maps, idx, d["run"]["tickers"])
        np.testing.assert_allclose(pw["beta"], full["beta"], atol=1e-12)
        np.testing.assert_allclose(pw["cov_e"], full["cov_e"], atol=1e-12)

    def test_too_short_stops(self):
        d = _truncate(synthetic_run(), "CCC", _bdays("2023-09-25", 756)[600])   # เหลือ ~156 วัน
        with self.assertRaises(op.StopRun):
            op.run(d, 0.10, None, short_ok=["CCC"])

    def test_unknown_short_ticker_stops(self):
        with self.assertRaises(op.StopRun):
            op.run(synthetic_run(), 0.10, None, short_ok=["ZZZ"])
