#!/usr/bin/env python3
"""portfolio-risk — จัดน้ำหนักหุ้นให้ความเสี่ยงไม่เป็นระบบต่ำสุด ภายใต้เป้าผลตอบแทน (CAPM) + เขียน HTML.

รันด้วย root venv เท่านั้น (numpy + scipy):
  __FRIDAY_ROOT__/.venv/bin/python optimize.py --in <run>.json --target 10 \
      --out __FRIDAY_ROOT__/outputs/portfolio-risk/<slug>-YYYY-MM-DD.html [--rm 9.5]

ตัวเลขทุกตัวที่ผู้ใช้เห็นมาจากไฟล์นี้. สูตรอ้างบทที่ 8 (FN_08):
  8.8  E(rp) = Σ wᵢ E(rᵢ)
  8.9  σ²p  = w'Σw
  (12) E(rᵢ) = r_RF + βᵢ (r_M − r_RF)
  single-index: Σ = ββ'σ²_M + Σ_ε  → สิ่งที่ลดคือ w'Σ_ε w (ความเสี่ยงไม่เป็นระบบ)
โหมดตรวจพอร์ตที่ถือ: แทน --target ด้วย --weights AAPL=40 MSFT=60 หรือ --shares AAPL=10 MSFT=5
  (--target ใส่ได้ถ้าอยากให้สัดส่วนเป้าใช้เป้าอื่นแทน E(rp) ปัจจุบัน)
HTML สร้างที่ render.py · มิติความเสี่ยง/เกณฑ์สีอยู่ที่ risk.py
อุตสาหกรรม / ค่าเงินบาท / ดอกเบี้ย (add_macro) ขาดข้อมูล → [ข้อมูลไม่พอ] + ธง ไม่หยุดงาน
exit 0 = เขียน HTML แล้ว (รวมกรณีถึงเป้าไม่ได้) · exit 2 = หยุด ไม่เขียน HTML
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

import risk as rk
from render import build_html  # noqa: F401 — ให้ test เรียก op.build_html ได้
from risk import num, pct, round_weights

TRADING_DAYS = 252
COVERAGE_MIN = 0.95
SHORT_MIN_DAYS = 252      # หุ้นประวัติสั้น (--short-history) ต้องมีอย่างน้อย 1 ปีทำการ


class StopRun(Exception):
    """เงื่อนไขที่ต้องหยุดแล้วบอกผู้ใช้ (ไม่เขียน HTML)."""


# ================================================================ สูตรพื้นฐาน
def portfolio_expected(w, er) -> float:
    """สูตร 8.8: E(rp) = Σ wᵢ E(rᵢ)."""
    return float(np.dot(np.asarray(w, float), np.asarray(er, float)))


def portfolio_sigma(w, cov) -> float:
    """สูตร 8.9 (รูปเมทริกซ์): σp = √(w'Σw)."""
    w = np.asarray(w, float)
    return math.sqrt(float(w @ np.asarray(cov, float) @ w))


def capm(rf: float, beta, rm: float):
    """สูตรที่ 12: r = r_RF + β (r_M − r_RF)."""
    return rf + np.asarray(beta, float) * (rm - rf) if np.ndim(beta) else rf + beta * (rm - rf)


def check_market(rf: float, rm: float) -> None:
    if rm <= rf:
        raise StopRun(f"r_M ({rm:.4%}) ไม่สูงกว่า r_RF ({rf:.4%}) — CAPM กลับทิศ "
                      "(หุ้น β สูงจะถูกคาดว่าได้ผลตอบแทนต่ำกว่า) จึงไม่คำนวณต่อ "
                      "ลองกำหนด r_M เองด้วย --rm")


def cagr(p0: float, p1: float, days: int) -> float:
    return (p1 / p0) ** (365.25 / days) - 1


# ================================================================ ข้อมูล
def to_map(rows) -> dict[str, float]:
    return {d: float(p) for d, p in (rows or []) if p is not None}


def history_gaps(stock_maps: dict, index_dates: list[str]) -> dict[str, str]:
    """เกณฑ์ครบ: วันแรกของราคา ≤ วันแรกของดัชนีในหน้าต่าง และมีข้อมูล ≥ 95% ของวันทำการดัชนี."""
    gaps = {}
    if not index_dates:
        return {t: "ไม่มีข้อมูลดัชนีในหน้าต่าง" for t in stock_maps}
    first, idx = index_dates[0], set(index_dates)
    for t, m in stock_maps.items():
        if not m:
            gaps[t] = "ไม่มีข้อมูลราคา"
            continue
        d0 = min(m)
        cov = len(idx & set(m)) / len(idx)
        if d0 > first:
            gaps[t] = f"ราคาวันแรก {d0} หลังวันเริ่มหน้าต่าง {first}"
        elif cov < COVERAGE_MIN:
            gaps[t] = f"มีข้อมูลเพียง {cov:.1%} ของวันทำการดัชนี (ต้อง ≥ {COVERAGE_MIN:.0%})"
    return gaps


def align(stock_maps: dict, index_map: dict, tickers: list[str]):
    """inner-join วันที่ของทุกหุ้นกับดัชนี → (dates, P[T×n], pm[T])."""
    common = set(index_map)
    for t in tickers:
        common &= set(stock_maps[t])
    dates = sorted(common)
    P = np.array([[stock_maps[t][d] for t in tickers] for d in dates], float).reshape(len(dates), len(tickers))
    pm = np.array([index_map[d] for d in dates], float)
    return dates, P, pm


def simple_returns(P):
    P = np.asarray(P, float)
    return P[1:] / P[:-1] - 1


def estimate(R, rm) -> dict:
    """OLS รายตัว rᵢ = αᵢ + βᵢ r_M + εᵢ · ทุกค่า annualize ด้วย 252."""
    R = np.asarray(R, float)
    rm = np.asarray(rm, float)
    X = np.column_stack([np.ones(len(rm)), rm])
    coef, *_ = np.linalg.lstsq(X, R, rcond=None)
    resid = R - X @ coef
    cov = np.atleast_2d(np.cov(R, rowvar=False, ddof=1)) * TRADING_DAYS
    cov_e = np.atleast_2d(np.cov(resid, rowvar=False, ddof=1)) * TRADING_DAYS
    cov_e = (cov_e + cov_e.T) / 2
    return {"alpha": coef[0], "beta": coef[1], "cov": cov, "cov_e": cov_e,
            "var_m": float(np.var(rm, ddof=1)) * TRADING_DAYS, "resid": resid}


def short_history_problem(m: dict, index_dates: list[str]) -> str | None:
    """หุ้นที่ผู้ใช้ยอมให้ประวัติสั้น: นับจากวันแรกของตัวนั้น ต้องมี ≥ 252 วันทำการ และครอบ ≥ 95% ของวันดัชนี."""
    if not m:
        return "ไม่มีข้อมูลราคา"
    idx = [d for d in index_dates if d >= min(m)]
    if len(idx) < SHORT_MIN_DAYS:
        return f"มีแค่ {len(idx)} วันทำการ (ต้อง ≥ {SHORT_MIN_DAYS})"
    cov = len(set(idx) & set(m)) / len(idx)
    if cov < COVERAGE_MIN:
        return f"มีข้อมูลเพียง {cov:.1%} ของวันทำการดัชนีนับจากวันแรก (ต้อง ≥ {COVERAGE_MIN:.0%})"
    return None


def nearest_psd(c):
    """ตัดค่า eigen ติดลบทิ้ง (เมทริกซ์ที่คิดทีละคู่คนละช่วงอาจไม่ positive semi-definite) · คืน (เมทริกซ์, แก้ไหม)."""
    c = (np.asarray(c, float) + np.asarray(c, float).T) / 2
    vals, vecs = np.linalg.eigh(c)
    if vals.min() >= -1e-12:
        return c, False
    c = (vecs * np.clip(vals, 0, None)) @ vecs.T
    return (c + c.T) / 2, True


def estimate_pairwise(stock_maps: dict, index_map: dict, tickers: list[str]) -> dict:
    """เหมือน estimate แต่ยอมให้บางตัวประวัติสั้น: β/ε รายตัวคิดจากช่วงที่ตัวนั้นมีข้อมูล
    · Σ และ Σ_ε คิดทีละคู่จากวันที่ทั้งคู่มีข้อมูล (คู่ที่ครบใช้เต็มหน้าต่าง) · annualize ด้วย 252."""
    dates = sorted(index_map)
    P = np.array([[stock_maps[t].get(d, np.nan) for t in tickers] for d in dates], float)
    pm = np.array([index_map[d] for d in dates], float)
    R, rm = P[1:] / P[:-1] - 1, pm[1:] / pm[:-1] - 1       # วันไหนราคาหาย → NaN
    n = len(tickers)
    alpha, beta = np.empty(n), np.empty(n)
    resid = np.full_like(R, np.nan)
    for i in range(n):
        ok = ~np.isnan(R[:, i])
        X = np.column_stack([np.ones(ok.sum()), rm[ok]])
        coef, *_ = np.linalg.lstsq(X, R[ok, i], rcond=None)
        alpha[i], beta[i] = coef
        resid[ok, i] = R[ok, i] - X @ coef

    def pair_cov(M):
        C = np.empty((n, n))
        for i in range(n):
            for j in range(i, n):
                ok = ~np.isnan(M[:, i]) & ~np.isnan(M[:, j])
                C[i, j] = C[j, i] = np.cov(M[ok, i], M[ok, j], ddof=1)[0, 1] * TRADING_DAYS
        return C

    cov, fix1 = nearest_psd(pair_cov(R))
    cov_e, fix2 = nearest_psd(pair_cov(resid))
    return {"alpha": alpha, "beta": beta, "cov": cov, "cov_e": cov_e,
            "var_m": float(np.var(rm, ddof=1)) * TRADING_DAYS, "resid": resid, "psd_fixed": fix1 or fix2}


def corr_from_cov(c):
    d = np.sqrt(np.clip(np.diag(c), 1e-18, None))
    return c / np.outer(d, d)


# ================================================================ ตัวหาน้ำหนัก
def min_unsys(beta, cov_e, beta_target: float | None = None):
    """min w'Σ_ε w  s.t. Σw=1, w≥0, (β'w ≥ β เป้า)."""
    beta = np.asarray(beta, float)
    cov_e = np.asarray(cov_e, float)
    n = len(beta)
    if n == 1:
        return np.array([1.0])
    scale = n / max(float(np.trace(cov_e)), 1e-18)   # ทำให้ objective อยู่ราว ๆ 1 → SLSQP ลู่เข้าแม่น
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(n)}]
    if beta_target is not None:
        cons.append({"type": "ineq", "fun": lambda w: w @ beta - beta_target, "jac": lambda w: beta})
    starts = [np.full(n, 1 / n)]
    if beta_target is not None:
        starts.append(np.eye(n)[int(np.argmax(beta))])
    for x0 in starts:
        r = minimize(lambda w: scale * (w @ cov_e @ w), x0, jac=lambda w: 2 * scale * (cov_e @ w),
                     bounds=[(0, 1)] * n, constraints=cons, method="SLSQP",
                     options={"ftol": 1e-15, "maxiter": 1000})
        w = np.clip(r.x, 0, None)
        w = w / w.sum()
        ok = abs(w.sum() - 1) < 1e-9 and (beta_target is None or w @ beta >= beta_target - 1e-6)
        if ok:
            return w
    raise StopRun(f"ตัวหาน้ำหนัก (SLSQP) หาคำตอบไม่สำเร็จ: {r.message}")


def plan_portfolio(beta, cov_e, rf: float, rm: float, target: float) -> dict:
    """ตัดสิน feasible แบบ closed-form ก่อน: E สูงสุด = r_RF + β_max (r_M − r_RF)."""
    check_market(rf, rm)
    beta = np.asarray(beta, float)
    beta_t = (target - rf) / (rm - rf)
    b_max = float(beta.max())
    e_max = float(capm(rf, b_max, rm))
    feasible = beta_t <= b_max + 1e-12
    w = min_unsys(beta, cov_e, beta_t if feasible else b_max)
    b_p = float(w @ beta)
    return {"feasible": feasible, "weights": w, "beta_target": beta_t, "beta_max": b_max,
            "e_max": e_max, "shortfall": 0.0 if feasible else target - e_max,
            "beta_p": b_p, "e_p": float(capm(rf, b_p, rm)),
            "unsys_var": float(w @ np.asarray(cov_e) @ w)}


def frontier(beta, cov_e, rf, rm, points: int = 21) -> list[tuple[float, float]]:
    """เป้า E(rp) เทียบ σ_ε ต่ำสุดที่ทำได้ (ช่วงตั้งแต่พอร์ต σ_ε ต่ำสุดไม่มีเป้า ถึง E สูงสุด)."""
    beta = np.asarray(beta, float)
    w0 = min_unsys(beta, cov_e)
    e0 = float(capm(rf, w0 @ beta, rm))
    e_max = float(capm(rf, beta.max(), rm))
    out = [(e0, math.sqrt(max(float(w0 @ cov_e @ w0), 0)))]
    if e_max - e0 < 1e-9:
        return out
    for e in np.linspace(e0, e_max, points)[1:]:
        w = min_unsys(beta, cov_e, (e - rf) / (rm - rf))
        out.append((float(e), math.sqrt(max(float(w @ cov_e @ w), 0))))
    return out


# ================================================================ ความเสี่ยงย้อนหลัง
def risk_split(w, beta, cov, cov_e, var_m) -> dict:
    w = np.asarray(w, float)
    sys_v = float((w @ beta) ** 2 * var_m)
    uns_v = float(w @ cov_e @ w)
    tot = float(w @ cov @ w)
    return {"sys_var": sys_v, "unsys_var": uns_v, "total_var": tot,
            "sys_share": sys_v / (sys_v + uns_v), "unsys_share": uns_v / (sys_v + uns_v)}


def buy_hold_path(P, w):
    """มูลค่าพอร์ตถือเฉย ๆ ตั้งแต่วันแรก (เริ่ม = 1)."""
    P = np.asarray(P, float)
    return (P / P[0]) @ np.asarray(w, float)


def drawdown(v):
    v = np.asarray(v, float)
    return v / np.maximum.accumulate(v) - 1


def path_stats(v) -> dict:
    v = np.asarray(v, float)
    r = v[1:] / v[:-1] - 1
    return {"total_return": float(v[-1] / v[0] - 1), "max_dd": float(drawdown(v).min()),
            "vol": float(np.std(r, ddof=1) * math.sqrt(TRADING_DAYS)) if len(r) > 1 else float("nan")}


def stress_block(block: dict, tickers: list[str], w) -> dict:
    idx = to_map(block["index"].get("prices"))
    idx_dates = sorted(idx)
    maps = {t: to_map(block["stocks"].get(t, {}).get("prices")) for t in tickers}
    gaps = history_gaps(maps, idx_dates)
    rows = {}
    for t in tickers:
        if t in gaps:
            rows[t] = None
        else:
            d, P, _ = align({t: maps[t]}, idx, [t])
            rows[t] = path_stats(P[:, 0])
    shown = round_weights(w)                       # นับเฉพาะตัวที่แสดง > 0.00% ในตาราง
    held = [t for t, d in zip(tickers, shown) if d > 0]
    port = path = None
    if idx_dates and not any(t in gaps for t in held):
        wh = np.array([x for x, d in zip(w, shown) if d > 0])
        d, P, pm = align(maps, idx, held)
        v = buy_hold_path(P, wh / wh.sum())
        port = path_stats(v)
        path = {"dates": d, "values": [float(x) for x in v]}     # ใช้คิดเป็นบาทด้วยค่าเงินจริงช่วงนั้น
    index = path_stats(np.array([idx[d] for d in idx_dates])) if len(idx_dates) > 1 else None
    return {"label": block["label"], "start": block["start"], "rows": rows, "gaps": gaps,
            "portfolio": port, "index": index, "path": path}


# ================================================================ พอร์ตที่ถืออยู่
def evaluate_weights(w, beta, cov_e, rf: float, rm: float) -> dict:
    """พอร์ตที่ผู้ใช้ถืออยู่ → คีย์ชุดเดียวกับ plan_portfolio (ไม่หาน้ำหนักใหม่)."""
    check_market(rf, rm)
    w = np.asarray(w, float)
    beta = np.asarray(beta, float)
    b_p = float(w @ beta)
    b_max = float(beta.max())
    return {"feasible": True, "weights": w, "beta_target": b_p, "beta_max": b_max,
            "e_max": float(capm(rf, b_max, rm)), "shortfall": 0.0,
            "beta_p": b_p, "e_p": float(capm(rf, b_p, rm)),
            "unsys_var": float(w @ np.asarray(cov_e) @ w)}


def parse_holdings(pairs: list[str], kind: str) -> dict[str, Decimal]:
    """["AAPL=40", "MSFT=60%"] → {"AAPL": Decimal("40"), ...} · ผิดรูป/ซ้ำ/ติดลบ → StopRun."""
    out = {}
    for raw in pairs:
        if "=" not in raw:
            raise StopRun(f"--{kind} ต้องเป็นรูป TICKER=ค่า (ได้ {raw!r})")
        t, v = raw.split("=", 1)
        t = t.strip().upper()
        try:
            d = Decimal(v.strip().rstrip("%").replace(",", ""))
        except InvalidOperation:
            raise StopRun(f"--{kind} ค่าของ {t} ไม่ใช่ตัวเลข (ได้ {v!r})") from None
        if not d.is_finite() or d < 0:
            raise StopRun(f"--{kind} ค่าของ {t} ต้องเป็นตัวเลขไม่ติดลบ (ได้ {v!r})")
        if t in out:
            raise StopRun(f"--{kind} มี {t} ซ้ำ")
        out[t] = d
    if not out or sum(out.values()) <= 0:
        raise StopRun(f"--{kind} รวมกันต้องมากกว่า 0")
    return out


def holdings_to_weights(hold: dict, kind: str, tickers: list[str], liq: list[dict]):
    """คืน (w เรียงตาม tickers, ข้อมูลมูลค่ารายตัวหรือ None, มูลค่ารวมหรือ None)."""
    if set(hold) != set(tickers):
        extra, lack = sorted(set(hold) - set(tickers)), sorted(set(tickers) - set(hold))
        raise StopRun(f"รายชื่อใน --{kind} ไม่ตรงกับ --tickers ของ fetch"
                      + (f" · เกิน: {', '.join(extra)}" if extra else "")
                      + (f" · ขาด: {', '.join(lack)}" if lack else ""))
    if kind == "weights":
        tot = sum(hold.values())
        if abs(tot - 100) > 1:
            raise StopRun(f"--weights รวมได้ {tot}% ต้องอยู่ระหว่าง 99–101% (ปัดเศษจากภาพหน้าจอได้ ±1)")
        return np.array([float(hold[t] / tot) for t in tickers]), None, None
    values = {}
    for t, lq in zip(tickers, liq):
        if lq["last_close"] is None:
            raise StopRun(f"ไม่มีราคาปิดล่าสุดของ {t} จึงคิดมูลค่าจากจำนวนหุ้นไม่ได้ — ใช้ --weights แทน")
        values[t] = {"shares": hold[t], "price": lq["last_close"], "value": hold[t] * lq["last_close"]}
    total = sum(v["value"] for v in values.values())
    return np.array([float(values[t]["value"] / total) for t in tickers]), values, total


# ================================================================ มิติความเสี่ยง (heat map)
def heat_map(c: dict, R, Rm) -> None:
    """เติม heat_rows / heat_port / hedges / conc ลงใน c (ใช้ค่าที่แสดงแล้วเท่านั้น สีจึงตรงกับตัวเลข)."""
    t, wd = c["tickers"], c["w_disp"]
    n = len(t)
    held = [i for i in range(n) if wd[i] > 0]
    anchor = rk.anchor_index(wd)
    cw = rk.corr_with(R, Rm, c["corr"], anchor)
    vol = [rk.pct_value(math.sqrt(c["cov"][i, i])) for i in range(n)]
    beta = [rk.D(num(b, 3)) for b in c["beta"]]
    dd, dd_lab = zip(*(rk.worst_crisis_dd(c["stress"], tk) for tk in t))
    dd = [rk.pct_value(x) for x in dd]
    adv = [lq["adv"] for lq in c["liq"]]
    rs = c["rate_sens"]
    rate = [None if x is None else rk.pct_value(x["b"]) for x in rs["stocks"]]
    rows = []
    for i, tk in enumerate(t):
        cells = {
            "weight": rk.cell("weight", wd[i], f"{wd[i]}%"),
            "vol": rk.cell("vol", vol[i], f"{vol[i]}%"),
            "beta": rk.cell("beta", beta[i], num(beta[i], 3)),
            "dd": rk.cell("dd", dd[i], f"{dd[i]}%"),
            "corr": ({"text": "หุ้นหลัก", "score": None, "pending": False, "anchor": True} if i == anchor
                     else rk.cell("corr", None if cw[i] is None else num(cw[i]), num(cw[i]) if cw[i] is not None else None)),
            "rate": rk.cell("rate", rate[i], rk.signed_pct(rate[i])),
            "liq": rk.cell("liq", adv[i], rk.usd_compact(adv[i])),
        }
        rows.append({"ticker": tk, "cells": cells, "overall": rk.overall(cells)})

    # ระดับพอร์ต
    port_dd, port_lab = None, None
    for sb in c["stress"].values():
        if sb["portfolio"] and (port_dd is None or sb["portfolio"]["max_dd"] < port_dd):
            port_dd, port_lab = sb["portfolio"]["max_dd"], sb["label"]
    w = np.asarray(c["res"]["weights"], float)
    avg = rk.avg_pair_corr(w, c["corr"])
    held_adv = [adv[i] for i in held]
    min_adv = None if (not held_adv or any(a is None for a in held_adv)) else min(held_adv)
    pvol = rk.pct_value(math.sqrt(c["split"]["total_var"]))
    pbeta = rk.D(num(c["res"]["beta_p"], 3))
    pdd = rk.pct_value(port_dd)
    prate = None if rs["portfolio"] is None else rk.pct_value(rs["portfolio"]["b"])
    port = {
        "weight": rk.cell("weight", max(wd), f"{max(wd)}%"),
        "vol": rk.cell("vol", pvol, f"{pvol}%"),
        "beta": rk.cell("beta", pbeta, num(pbeta, 3)),
        "dd": rk.cell("dd", pdd, f"{pdd}%"),
        "corr": rk.cell("corr", None if avg is None else num(avg), None if avg is None else num(avg)),
        "rate": rk.cell("rate", prate, rk.signed_pct(prate)),
        "liq": rk.cell("liq", min_adv, rk.usd_compact(min_adv)),
    }
    c.update({
        "heat_rows": rows, "heat_port": port, "heat_port_overall": rk.overall(port),
        "corr_anchor": t[anchor] if anchor is not None else None, "avg_corr": avg,
        "port_dd": {"value": pdd, "label": port_lab}, "conc": rk.concentration(t, wd),
        "rate_disp": rate, "rate_port": prate,
    })
    sw = c["sectors"]["warnings"] if c["sectors"] else []
    extras = [rk.sector_hedge(max(sw, key=lambda x: x["weight"]))] if sw else []
    c["hedges"] = rk.top_hedges(port, {"tickers": t, "w_disp": wd, "vol": vol, "beta": beta, "dd": dd,
                                        "dd_label": port_lab, "corr": cw, "liq": adv, "rate": rate},
                                extras=extras)


# ================================================================ อุตสาหกรรม · ค่าเงิน · ดอกเบี้ย
def add_macro(c: dict, data: dict, P, v_p) -> None:
    """เติม sectors / fx / rate_sens ลงใน c · ชุดไหนดึงไม่ได้ → None + ธง (ไม่หยุดทั้งงาน)."""
    t, flags = c["tickers"], c["flags"]

    sec = data.get("sectors") or {"error": "MISSING", "message": "JSON ไม่มีข้อมูลอุตสาหกรรม (fetch รุ่นเก่า)"}
    if "error" in sec:
        c["sectors"], c["sector_src"] = None, None
        flags.append(f"ดึงอุตสาหกรรมไม่ได้ ({sec['error']}) — หัวข้ออุตสาหกรรมเป็น [ข้อมูลไม่พอ]")
    else:
        c["sectors"] = rk.sector_weights(t, c["w_disp"], sec["map"])
        c["sector_map"] = sec["map"]
        c["sector_src"] = {"as_of": sec.get("as_of"), "tier": sec.get("source_tier")}

    fx = data.get("fx") or {"error": "MISSING", "message": "JSON ไม่มีค่าเงิน (fetch รุ่นเก่า)"}
    pts = [] if "error" in fx else rk.series_points(fx.get("rows"))
    if not pts:
        c["fx"] = None
        flags.append(f"ดึงค่าเงินบาท (DEXTHUS) ไม่ได้ ({fx.get('error', 'NO_DATA')}) — หัวข้อค่าเงินเป็น [ข้อมูลไม่พอ]")
    else:
        d_now, r_now = pts[-1]
        windows = [{"label": c["win_label"], **(rk.fx_path(c["dates"], v_p, pts) or {})}]
        for sb in c["stress"].values():
            pth = sb.get("path")
            windows.append({"label": sb["label"], **((rk.fx_path(pth["dates"], pth["values"], pts) or {}) if pth else {})})
        c["fx"] = {"date": d_now, "rate": r_now, "as_of": fx.get("as_of"),
                   "scenarios": rk.fx_scenarios(r_now, c["total_value"]), "windows": windows}

    rt = data.get("rates") or {"error": "MISSING", "message": "JSON ไม่มีดอกเบี้ย (fetch รุ่นเก่า)"}
    rows = None if "error" in rt else rt.get("rows")
    c["rate_sens"] = rk.rate_sensitivity(c["dates"], P, rows, c["res"]["weights"])
    c["rate_src"] = None if "error" in rt else {"as_of": rt.get("as_of")}
    if c["rate_sens"]["portfolio"] is None:
        why = rt.get("error") or f"มีแค่ {c['rate_sens']['weeks']} สัปดาห์ (ต้อง ≥ {rk.RATE_MIN_WEEKS})"
        flags.append(f"คิดความไวต่อดอกเบี้ย (DGS10) ไม่ได้ ({why}) — มิติดอกเบี้ยเป็น [ข้อมูลไม่พอ]")


# ================================================================ main
def run(data: dict, target: float | None, rm_override: float | None, holdings: tuple | None = None,
        short_ok: list[str] | None = None) -> dict:
    """holdings = None (โหมดหาน้ำหนัก) หรือ (kind, {ticker: Decimal}) โดย kind = "weights" | "shares".
    short_ok = หุ้นที่ผู้ใช้ยอมให้ประวัติไม่ครบ 3 ปี (ใช้ข้อมูลเท่าที่มี ≥ 1 ปี)."""
    tickers = data["run"]["tickers"]
    mode = "evaluate" if holdings else "optimize"
    if mode == "optimize" and target is None:
        raise StopRun("โหมดหาน้ำหนักต้องมี --target (หรือให้ --weights/--shares เพื่อตรวจพอร์ตที่ถืออยู่)")
    flags = []
    rf_raw = data["rf"]
    if "error" in rf_raw:
        raise StopRun(f"ดึง r_RF (DTB3) ไม่ได้: {rf_raw['message']}")
    rf = float(Decimal(rf_raw["value_pct"]) / 100)
    mk = data["market"]
    if rm_override is not None:
        rm = rm_override
        rm_src, rm_detail = "ผู้ใช้กำหนด", f"ผู้ใช้กำหนดเอง {pct(rm)}"
    else:
        if "error" in mk:
            raise StopRun(f"ดึง SPY 20 ปีไม่ได้: {mk['message']} — กำหนด r_M เองด้วย --rm")
        (d0, p0), (d1, p1) = mk["first"], mk["last"]
        days = (date.fromisoformat(d1) - date.fromisoformat(d0)).days
        rm = cagr(float(p0), float(p1), days)
        rm_src = "SPY CAGR 20 ปี"
        rm_detail = f"CAGR ของ SPY adj_close (รวมปันผล) {d0} → {d1} = {pct(rm)} (yfinance tier 3)"
    check_market(rf, rm)

    liq = [rk.liquidity(data["stocks"][t].get("liq")) for t in tickers]
    hold_values = total_value = None
    if holdings:
        w_hold, hold_values, total_value = holdings_to_weights(holdings[1], holdings[0], tickers, liq)

    index_map = to_map(data["index"].get("prices"))
    if data["index"].get("fallback"):
        flags.append("ดึง ^GSPC ไม่ได้ จึงใช้ SPY เป็นดัชนีตลาดสำหรับหา β แทน")
    stock_maps = {t: to_map(data["stocks"][t].get("prices")) for t in tickers}
    short = {x.upper() for x in (short_ok or [])}
    if short - set(tickers):
        raise StopRun(f"--short-history มีหุ้นที่ไม่อยู่ใน --tickers: {', '.join(sorted(short - set(tickers)))}")
    gaps = history_gaps(stock_maps, sorted(index_map))
    hard = {k: v for k, v in gaps.items() if k not in short}
    if hard:
        raise StopRun("ประวัติราคาไม่ครบ 3 ปี: " + "; ".join(f"{k} ({v})" for k, v in hard.items())
                      + " — ถ้าจะใช้ข้อมูลเท่าที่มี ใส่ --short-history ตามด้วยชื่อหุ้น")
    short_used = {}
    for t in gaps:
        why = short_history_problem(stock_maps[t], sorted(index_map))
        if why:
            raise StopRun(f"{t} ประวัติสั้นเกินกว่าจะใช้: {why}")
        short_used[t] = min(stock_maps[t])
    if any(lq["adv"] is None for lq in liq):
        flags.append("บางตัวไม่มีข้อมูล volume พอ (ต้อง ≥ 20 วัน) — มิติสภาพคล่องของตัวนั้นเป็น [ข้อมูลไม่พอ]")

    dates, P, pm = align(stock_maps, index_map, tickers)      # ประวัติสั้น → ช่วงร่วมเริ่มตามตัวที่สั้นสุด
    R, Rm = simple_returns(P), simple_returns(pm)
    est = estimate_pairwise(stock_maps, index_map, tickers) if short_used else estimate(R, Rm)
    if short_used:
        idx_dates = sorted(index_map)
        flags.append("ใช้ข้อมูลเท่าที่มีของหุ้นประวัติไม่ครบ 3 ปี: "
                     + ", ".join(f"{k} (เริ่ม {v})" for k, v in short_used.items())
                     + " — β และความเสี่ยงไม่เป็นระบบของตัวนั้น และคู่ที่มีตัวนั้น คิดจากช่วงที่มีข้อมูลเท่านั้น "
                     f"ส่วนคู่อื่นใช้เต็มหน้าต่าง {idx_dates[0]} → {idx_dates[-1]} (คนละช่วงเวลา ความแม่นยำลดลง) · "
                     f"ผลตอบแทนย้อนหลัง/กราฟ/ค่าเงิน/ดอกเบี้ย ใช้ช่วงร่วม {dates[0]} → {dates[-1]} · "
                     "stress test ช่วงที่หุ้นตัวนั้นยังไม่มีราคา คิดทั้งพอร์ตไม่ได้")
        if est["psd_fixed"]:
            flags.append("covariance ที่คิดทีละคู่คนละช่วงไม่สอดคล้องกันเล็กน้อย จึงปรับค่า eigen ติดลบเป็น 0 ก่อนหาน้ำหนัก")
    beta, cov, cov_e, var_m = est["beta"], est["cov"], est["cov_e"], est["var_m"]
    if mode == "evaluate":
        res = evaluate_weights(w_hold, beta, cov_e, rf, rm)
    else:
        res = plan_portfolio(beta, cov_e, rf, rm, target)
    w = res["weights"]
    w_eq = np.full(len(tickers), 1 / len(tickers))
    days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days
    v_p, v_eq = buy_hold_path(P, w), buy_hold_path(P, w_eq)
    c = {
        "mode": mode, "tickers": tickers, "target": target, "target_given": target is not None,
        "rf": rf, "rm": rm, "res": res, "beta": beta, "cov": cov,
        "cov_e": cov_e, "er": capm(rf, beta, rm), "hist": [cagr(P[0, i], P[-1, i], days) for i in range(len(tickers))],
        "w_disp": round_weights(w), "split": risk_split(w, beta, cov, cov_e, var_m),
        "split_eq": risk_split(w_eq, beta, cov, cov_e, var_m), "b_eq": float(w_eq @ beta),
        "e_eq": float(capm(rf, w_eq @ beta, rm)), "corr": corr_from_cov(cov), "corr_e": corr_from_cov(cov_e),
        "dates": dates, "short_history": short_used,
        "win_txt": f"ช่วงร่วม {dates[0]} → {dates[-1]}" if short_used else "3 ปี",
        "win_label": (f"ช่วงร่วม {dates[0]} → {dates[-1]}" if short_used else "3 ปีล่าสุด (หน้าต่างประมาณค่า)"),
        "hist_p": path_stats(v_p), "hist_eq": path_stats(v_eq),
        "dd_p": drawdown(v_p), "dd_eq": drawdown(v_eq), "dd_idx": drawdown(pm),
        "stress": {k: stress_block(b, tickers, w) for k, b in data["stress"].items()},
        "liq": liq, "holding_values": hold_values, "total_value": total_value,
        "index_ticker": data["index"]["ticker"], "as_of": data["run"]["as_of"], "flags": flags,
        "sources": {"rf": rf_raw["series_id"], "rf_date": rf_raw["date"], "rm": rm_src, "rm_detail": rm_detail,
                    "price_as_of": data["index"].get("as_of", data["run"]["as_of"])},
    }
    if mode == "optimize":
        c["frontier"] = frontier(beta, cov_e, rf, rm)
    else:
        # สัดส่วนเป้า: หุ้นชุดเดิม ที่ E(rp) = เป้าผู้ใช้ หรือ = ของพอร์ตปัจจุบัน
        rb = plan_portfolio(beta, cov_e, rf, rm, target if target is not None else res["e_p"])
        c["rebal_res"] = rb
        c["split_rebal"] = risk_split(rb["weights"], beta, cov, cov_e, var_m)
        c["rebalance"] = rk.rebalance_table(tickers, c["w_disp"], round_weights(rb["weights"]))
    add_macro(c, data, P, v_p)
    heat_map(c, R, Rm)
    # ตรวจตัวเอง: Σ = ββ'σ²M + Σ_ε (in-sample ต้องตรง) · Σ_ε สมมาตร
    if not short_used:    # คิดทีละคู่คนละช่วง → สมการนี้ไม่ต้องตรงเป๊ะ
        assert np.allclose(cov, np.outer(beta, beta) * var_m + cov_e, atol=1e-10), "Σ ≠ ββ'σ²M + Σ_ε"
    assert np.allclose(cov_e, cov_e.T), "Σ_ε ไม่สมมาตร"
    return c


def summary(c: dict, out: Path) -> dict:
    res = c["res"]
    s = {
        "html": str(out), "mode": c["mode"],
        "risk_level": (f"{c['heat_port_overall']} · {rk.LEVEL[c['heat_port_overall']]}"
                       if c["heat_port_overall"] else "[ข้อมูลไม่พอ]"),
        "e_p": pct(res["e_p"]), "beta_p": num(res["beta_p"], 3),
        "vol_p": pct(math.sqrt(c["split"]["total_var"])),
        "worst_crisis_dd": (f"{c['port_dd']['value']}% ({c['port_dd']['label']})"
                            if c["port_dd"]["value"] is not None else "[ข้อมูลไม่พอ]"),
        "avg_corr": num(c["avg_corr"]) if c["avg_corr"] is not None else "[ข้อมูลไม่พอ]",
        "effective_n": str(c["conc"]["effective_n"]),
        "cap_warnings": [f"{w['ticker']} {w['weight']}% ≥ {w['cap']}%" for w in c["conc"]["warnings"]],
        "rf": pct(c["rf"]), "rm": pct(c["rm"]), "rm_source": c["sources"]["rm_detail"],
        "sys_share": pct(c["split"]["sys_share"], 1), "unsys_share": pct(c["split"]["unsys_share"], 1),
        "unsys_sigma": pct(math.sqrt(c["split"]["unsys_var"])),
        "weights": {t: f"{wd}%" for t, wd in zip(c["tickers"], c["w_disp"])},
        "heat": {r["ticker"]: r["overall"] for r in c["heat_rows"]},
        "hedges": [h["text"] for h in c["hedges"]],
        "window": [c["dates"][0], c["dates"][-1]], "flags": c["flags"],
        "short_history": c["short_history"],
        "stress_portfolio": {k: (pct(v["portfolio"]["total_return"]) if v["portfolio"] else "[ข้อมูลไม่พอ]")
                             for k, v in c["stress"].items()},
        "sectors": ({g["sector"]: f"{g['weight']}%" for g in c["sectors"]["rows"]} if c["sectors"] else "[ข้อมูลไม่พอ]"),
        "sector_warnings": ([f"{w['sector']} {w['weight']}% ≥ {w['cap']}%" for w in c["sectors"]["warnings"]]
                            if c["sectors"] else []),
        "rate_plus1_port": rk.signed_pct(c["rate_port"]),
        "rate_r2_port": (num(c["rate_sens"]["portfolio"]["r2"]) if c["rate_sens"]["portfolio"] else "[ข้อมูลไม่พอ]"),
        "rate_plus1": {tk: rk.signed_pct(x) for tk, x in zip(c["tickers"], c["rate_disp"])},
        "fx_usdthb": (f"{c['fx']['rate']} ({c['fx']['date']})" if c["fx"] else "[ข้อมูลไม่พอ]"),
        "fx_windows": ({w["label"]: (f"USD {pct(w['ret_usd'])} → THB {pct(w['ret_thb'])}" if "ret_usd" in w
                                     else "[ข้อมูลไม่พอ]") for w in c["fx"]["windows"]} if c["fx"] else "[ข้อมูลไม่พอ]"),
    }
    if c["mode"] == "optimize":
        s.update({"feasible": res["feasible"], "target": pct(c["target"]), "e_max": pct(res["e_max"]),
                  "shortfall": pct(res["shortfall"]), "beta_target": num(res["beta_target"], 3),
                  "unsys_sigma_equal_weight": pct(math.sqrt(c["split_eq"]["unsys_var"]))})
    else:
        rb = c["rebal_res"]
        s.update({"rebalance_basis": pct(c["target"]) if c["target_given"] else f"E(rp) ≥ ปัจจุบัน {pct(res['e_p'])}",
                  "rebalance_feasible": rb["feasible"],
                  "rebalance": {r["ticker"]: f"{r['current']}% → {r['target']}% ({r['action']})" for r in c["rebalance"]},
                  "unsys_sigma_rebalanced": pct(math.sqrt(c["split_rebal"]["unsys_var"]))})
        if c["total_value"] is not None:
            s["total_value_usd"] = rk.usd(c["total_value"])
            if c["fx"]:
                s["total_value_thb"] = rk.thb(c["fx"]["scenarios"][2]["value_thb"])
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="portfolio-risk optimizer / evaluator")
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--target", default=None,
                    help="เป้า E(rp) หน่วย %% ต่อปี เช่น 10 (โหมดหาน้ำหนักต้องมี · โหมดตรวจพอร์ตใส่หรือไม่ก็ได้)")
    ap.add_argument("--rm", default=None, help="r_M หน่วย %% ต่อปี (ไม่ใส่ = SPY CAGR 20 ปี)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--weights", nargs="+", metavar="T=%", help="ตรวจพอร์ตที่ถือ: สัดส่วน %% เช่น AAPL=40 MSFT=60")
    g.add_argument("--shares", nargs="+", metavar="T=n", help="ตรวจพอร์ตที่ถือ: จำนวนหุ้น เช่น AAPL=10 MSFT=5")
    ap.add_argument("--short-history", nargs="+", default=None, metavar="T",
                    help="หุ้นที่ยอมให้ประวัติไม่ครบ 3 ปี (ใช้ข้อมูลเท่าที่มี ต้อง ≥ 1 ปี) เช่น GEV")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        target = float(Decimal(a.target) / 100) if a.target is not None else None
        rm = float(Decimal(a.rm) / 100) if a.rm is not None else None
    except InvalidOperation:
        print(f"STOP: --target/--rm ต้องเป็นตัวเลขหน่วย % ไม่มีเครื่องหมาย % (ได้ {a.target!r}, {a.rm!r})",
              file=sys.stderr)
        return 2
    data = json.loads(Path(a.inp).read_text(encoding="utf-8"))
    try:
        holdings = None
        if a.weights:
            holdings = ("weights", parse_holdings(a.weights, "weights"))
        elif a.shares:
            holdings = ("shares", parse_holdings(a.shares, "shares"))
        c = run(data, target, rm, holdings, a.short_history)
    except StopRun as e:
        print(f"STOP: {e}", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(c), encoding="utf-8")
    print(json.dumps(summary(c, out), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
