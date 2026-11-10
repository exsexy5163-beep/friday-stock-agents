#!/usr/bin/env python3
"""portfolio-risk — มิติความเสี่ยงแบบสมหมาย (เลขล้วน ไม่มี HTML).

ลอกแนวคิดมาเขียนใหม่.
ทุกเลขที่ผู้ใช้เห็น (%, เงิน, คะแนนสี) ผ่าน Decimal · numpy ใช้เฉพาะชั้นเมทริกซ์
เกณฑ์สีเก็บไว้ที่ HEAT ชุดเดียว — HTML พิมพ์ตารางเกณฑ์จากค่าคงที่ชุดนี้
"""
from __future__ import annotations

import bisect
import math
from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

import numpy as np

# ================================================================ การปัดตัวเลขที่แสดง
def D(x) -> Decimal:
    """ตัวเลขใด ๆ → Decimal โดยไม่พาเศษทศนิยมเพี้ยนของ float มาด้วย."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, (int, str)):
        return Decimal(x)
    return Decimal(repr(float(x)))


def is_missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def round_weights(w, units: int = 10000) -> list[Decimal]:
    """largest-remainder → % ทศนิยม 2 ตำแหน่ง รวมได้ 100.00 พอดี."""
    raw = [D(x) * units for x in w]
    fl = [r.to_integral_value(rounding=ROUND_FLOOR) for r in raw]
    rem = max(0, min(len(w), units - int(sum(fl))))
    for i in sorted(range(len(w)), key=lambda i: raw[i] - fl[i], reverse=True)[:rem]:
        fl[i] += 1
    return [(f * 100 / units).quantize(Decimal("0.01")) for f in fl]


def pct_value(x, dp: int = 2) -> Decimal | None:
    """สัดส่วน (0.1234) → % ที่ปัดแล้ว (12.34) เป็น Decimal — ใช้ทั้งแสดงและตัดสินสี ให้สองอย่างตรงกัน."""
    if is_missing(x):
        return None
    return (D(x) * 100).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)


def pct(x, dp: int = 2) -> str:
    v = pct_value(x, dp)
    return "[ข้อมูลไม่พอ]" if v is None else f"{v}%"


def num(x, dp: int = 2) -> str:
    if is_missing(x):
        return "[ข้อมูลไม่พอ]"
    return str(D(x).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP))


def usd(x) -> str:
    if x is None:
        return "[ข้อมูลไม่พอ]"
    return f"${D(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"


def thb(x) -> str:
    if x is None:
        return "[ข้อมูลไม่พอ]"
    return f"฿{D(x).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"


def usd_compact(x) -> str:
    """1,234,000,000 → $1.23B · ใช้กับมูลค่าซื้อขายต่อวัน."""
    if x is None:
        return "[ข้อมูลไม่พอ]"
    v = D(x)
    for size, unit in ((Decimal(10) ** 9, "B"), (Decimal(10) ** 6, "M"), (Decimal(10) ** 3, "K")):
        if abs(v) >= size:
            return f"${(v / size).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}{unit}"
    return usd(v)


# ================================================================ เกณฑ์สี heat map
# cuts = เส้นแบ่งระดับ 1|2|3|4|5 ในหน่วยที่แสดง · worse = ทิศที่ถือว่าแย่
#   high → ยิ่งสูงยิ่งแย่ · deep → ค่าติดลบ ยิ่งลึกยิ่งแย่ · abs → ดูขนาดไม่ดูทิศ · low → ยิ่งต่ำยิ่งแย่
HEAT = {
    "weight": {"label": "น้ำหนักในพอร์ต", "worse": "high", "cuts": ("5", "10", "20", "30"),
               "ranges": ("<5%", "5–10%", "10–20%", "20–30%", "≥30%")},
    "vol": {"label": "ความผันผวนต่อปี", "worse": "high", "cuts": ("15", "20", "25", "35"),
            "ranges": ("<15%", "15–20%", "20–25%", "25–35%", "≥35%")},
    "beta": {"label": "β", "worse": "high", "cuts": ("0.8", "1.0", "1.2", "1.5"),
             "ranges": ("<0.8", "0.8–1.0", "1.0–1.2", "1.2–1.5", "≥1.5")},
    "dd": {"label": "ร่วงสูงสุดช่วงวิกฤต", "worse": "deep", "cuts": ("10", "15", "25", "35"),
           "ranges": (">−10%", "−10% ถึง −15%", "−15% ถึง −25%", "−25% ถึง −35%", "≤−35%")},
    "corr": {"label": "correlation กับหุ้นหลัก", "worse": "high", "cuts": ("0.30", "0.45", "0.60", "0.75"),
             "ranges": ("<0.30", "0.30–0.45", "0.45–0.60", "0.60–0.75", "≥0.75")},
    "rate": {"label": "ดอกเบี้ย +1% หุ้นขยับ", "worse": "abs", "cuts": ("2", "4", "6", "8"),
             "ranges": ("<2%", "2–4%", "4–6%", "6–8%", "≥8%")},
    "liq": {"label": "มูลค่าซื้อขายเฉลี่ยต่อวัน", "worse": "low",
            "cuts": ("1000000000", "100000000", "20000000", "5000000"),
            "ranges": ("≥$1B", "$100M–1B", "$20–100M", "$5–20M", "<$5M")},
}
HEAT_ORDER = ("weight", "vol", "beta", "dd", "corr", "rate", "liq")
HEAT_COLORS = ("#1C6B52", "#3E8E5E", "#C9A23F", "#C97A3A", "#A8392F")
GREY = "#3A4450"
LEVEL = {1: "ต่ำ", 2: "ค่อนข้างต่ำ", 3: "ปานกลาง", 4: "สูง", 5: "สูงมาก"}

SOFT_CAP, HARD_CAP = Decimal(20), Decimal(30)   # เพดานเตือนหุ้นตัวเดียว (% ของพอร์ต)
SECTOR_SOFT, SECTOR_HARD = Decimal(35), Decimal(45)   # เพดานเตือนรายอุตสาหกรรม
SECTOR_SCORE = {"soft": 4, "hard": 5}           # เทียบระดับเดียวกับเพดานหุ้นตัวเดียว (20–30% = 4 · ≥30% = 5)
UNKNOWN_SECTOR = "ETF / ไม่ทราบ"
FX_SHOCKS = (Decimal(-10), Decimal(-5), Decimal(5), Decimal(10))   # % เปลี่ยนของอัตราบาทต่อดอลลาร์
RATE_WEAK_R2 = Decimal("0.10")                  # r² ต่ำกว่านี้ → บอกว่าความสัมพันธ์อ่อน
RATE_MIN_WEEKS = 52                             # ถดถอยดอกเบี้ยต้องมีอย่างน้อย 1 ปีของสัปดาห์
FFILL_MAX_DAYS = 7                              # ค่าเงิน/ดอกเบี้ยวันหยุด ใช้ค่าล่าสุดได้ไม่เกิน 7 วัน
REBAL_BAND = Decimal(2)                          # ห่างเป้าเกินกี่จุด% ถึงเรียกว่าต้องปรับ


def heat_score(metric: str, value) -> int | None:
    """ค่าที่แสดง (หน่วยเดียวกับตาราง) → ระดับ 1–5 · ไม่มีข้อมูล → None (ห้ามเดาเป็นเขียว)."""
    if is_missing(value):
        return None
    spec = HEAT[metric]
    v = D(value)
    cuts = [Decimal(c) for c in spec["cuts"]]
    if spec["worse"] == "deep":
        v = -v
    elif spec["worse"] == "abs":
        v = abs(v)
    if spec["worse"] == "low":
        return 1 + sum(v < c for c in cuts)
    return 1 + sum(v >= c for c in cuts)


def heat_color(score: int | None) -> str:
    return GREY if score is None else HEAT_COLORS[score - 1]


def cell(metric: str, value, text: str | None = None) -> dict:
    """ช่องหนึ่งช่องของ heat map: ข้อความที่แสดง + ระดับ (สีคิดจากระดับเท่านั้น)."""
    score = heat_score(metric, value)
    if score is None:
        return {"text": "[ข้อมูลไม่พอ]", "score": None, "pending": False}
    return {"text": text if text is not None else str(value), "score": score, "pending": False}


def overall(cells: dict) -> int | None:
    """ช่อง "รวม" = ระดับแย่สุดในแถว (ไม่เฉลี่ย เพราะจุดอ่อนจุดเดียวก็พอให้เจ็บ)."""
    s = [c["score"] for c in cells.values() if c["score"] is not None]
    return max(s) if s else None


# ================================================================ มิติรายตัว
def liquidity(rows, min_days: int = 20) -> dict:
    """rows = [[date, close, volume], ...] ช่วงราว 3 เดือนล่าสุด → มูลค่าซื้อขายเฉลี่ยต่อวัน (USD)."""
    vals, last_close = [], None
    for r in rows or []:
        if len(r) < 3 or is_missing(r[1]) or r[2] in (None, "", "None"):
            continue
        close, vol = D(r[1]), D(r[2])
        vals.append(close * vol)
        last_close = close
    adv = (sum(vals) / len(vals)) if len(vals) >= min_days else None
    return {"adv": adv, "last_close": last_close, "days": len(vals)}


def worst_crisis_dd(stress: dict, i_ticker: str):
    """ร่วงสูงสุด (max drawdown) ที่แย่สุดของทุกช่วงวิกฤตที่มีข้อมูล · คืน (ค่า, ชื่อช่วง) หรือ (None, None)."""
    best = (None, None)
    for sb in stress.values():
        r = sb["rows"].get(i_ticker)
        if r and (best[0] is None or r["max_dd"] < best[0]):
            best = (r["max_dd"], sb["label"])
    return best


def anchor_index(w_disp: list[Decimal]) -> int | None:
    """หุ้นหลัก = น้ำหนักที่แสดงมากสุด · ถ้าเสมอกันหลายตัว → None (ใช้ดัชนีตลาดเป็นแกนแทน)."""
    top = max(w_disp)
    idx = [i for i, x in enumerate(w_disp) if x == top]
    return idx[0] if len(idx) == 1 else None


def corr_with(R, Rm, corr, anchor: int | None) -> list:
    """correlation ของหุ้นแต่ละตัวกับหุ้นหลัก (ตัวหลักเองคืน None) หรือกับดัชนีถ้าไม่มีหุ้นหลัก."""
    n = corr.shape[0]
    if anchor is not None:
        return [None if i == anchor else float(corr[i, anchor]) for i in range(n)]
    R, Rm = np.asarray(R, float), np.asarray(Rm, float)
    return [float(np.corrcoef(R[:, i], Rm)[0, 1]) for i in range(n)]


def avg_pair_corr(w, corr) -> float | None:
    """correlation เฉลี่ยถ่วงน้ำหนักของทุกคู่หุ้นที่ถือ (ไม่นับคู่ตัวเองกับตัวเอง)."""
    w = np.asarray(w, float)
    C = np.asarray(corr, float)
    W = np.outer(w, w)
    np.fill_diagonal(W, 0)
    tot = W.sum()
    return None if tot <= 1e-12 else float((W * C).sum() / tot)


def concentration(tickers, w_disp: list[Decimal]) -> dict:
    """ตัวใหญ่สุด · จำนวนหุ้นเทียบเท่า (1/Σw²) · รายการที่เกินเพดานเตือน."""
    top = max(range(len(tickers)), key=lambda i: w_disp[i])
    s2 = sum((x / 100) ** 2 for x in w_disp)
    eff = (1 / s2).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if s2 > 0 else None
    warns = []
    for t, x in zip(tickers, w_disp):
        if x >= HARD_CAP:
            warns.append({"ticker": t, "weight": x, "cap": HARD_CAP, "level": "hard"})
        elif x >= SOFT_CAP:
            warns.append({"ticker": t, "weight": x, "cap": SOFT_CAP, "level": "soft"})
    return {"top_ticker": tickers[top], "top_weight": w_disp[top], "effective_n": eff, "warnings": warns}


# ================================================================ อุตสาหกรรม
def sector_weights(tickers, w_disp: list[Decimal], sector_map: dict | None) -> dict:
    """รวมน้ำหนักตามกลุ่มอุตสาหกรรม (Nasdaq) · หาไม่เจอ/ETF → กลุ่ม UNKNOWN_SECTOR (ไม่ใช้เพดานเตือน)."""
    groups: dict[str, dict] = {}
    for t, x in zip(tickers, w_disp):
        info = (sector_map or {}).get(t) or {}
        name = info.get("sector") if info.get("sector") not in (None, "", "?") else UNKNOWN_SECTOR
        g = groups.setdefault(name, {"sector": name, "weight": Decimal("0.00"), "tickers": [], "level": None})
        g["weight"] += x
        g["tickers"].append(t)
    rows = sorted(groups.values(), key=lambda g: (g["sector"] == UNKNOWN_SECTOR, -g["weight"], g["sector"]))
    warns = []
    for g in rows:
        if g["sector"] == UNKNOWN_SECTOR:
            continue
        g["level"] = "hard" if g["weight"] >= SECTOR_HARD else "soft" if g["weight"] >= SECTOR_SOFT else None
        if g["level"]:
            warns.append({"sector": g["sector"], "weight": g["weight"], "tickers": g["tickers"],
                          "cap": SECTOR_HARD if g["level"] == "hard" else SECTOR_SOFT, "level": g["level"]})
    return {"rows": rows, "warnings": warns}


# ================================================================ ค่าเงิน / ดอกเบี้ย (อนุกรมรายวันจาก FRED)
def series_points(rows) -> list[tuple[str, Decimal]]:
    """[[date, "36.12"], ...] → เรียงตามวัน · ข้ามค่าว่าง/ไม่ใช่ตัวเลข."""
    out = []
    for r in rows or []:
        try:
            v = Decimal(str(r[1]))
        except Exception:  # noqa: BLE001 — "." หรือค่าว่างของ FRED
            continue
        if v.is_finite():
            out.append((str(r[0]), v))
    return sorted(out)


def value_at(points: list[tuple[str, Decimal]], d: str, max_days: int = FFILL_MAX_DAYS) -> Decimal | None:
    """ค่าล่าสุดที่วันไม่เกิน d (forward-fill) · ห่างเกิน max_days → None (ไม่ลากค่าข้ามช่วงที่ขาด)."""
    i = bisect.bisect_right([p[0] for p in points], d) - 1
    if i < 0:
        return None
    pd, v = points[i]
    return v if (date.fromisoformat(d) - date.fromisoformat(pd)).days <= max_days else None


def fx_scenarios(rate_now: Decimal, total_usd: Decimal | None) -> list[dict]:
    """สมมติอัตราบาทต่อดอลลาร์เปลี่ยน ±5% ±10% · มูลค่าเป็นบาทเปลี่ยน % เท่ากันแม้หุ้นไม่ขยับ."""
    out = []
    for shock in (FX_SHOCKS[0], FX_SHOCKS[1], Decimal(0), FX_SHOCKS[2], FX_SHOCKS[3]):
        r = (rate_now * (1 + shock / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        label = ("ค่าเงินวันนี้" if shock == 0 else
                 f"บาทแข็ง (ดอลลาร์อ่อน) {abs(shock)}%" if shock < 0 else f"บาทอ่อน (ดอลลาร์แข็ง) {shock}%")
        out.append({"shock": shock, "label": label, "rate": r,
                    "value_thb": None if total_usd is None else (total_usd * rate_now * (1 + shock / 100))
                    .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)})
    return out


def fx_path(dates: list[str], values, points) -> dict | None:
    """มูลค่าพอร์ต USD ตามวัน × ค่าเงินวันเดียวกัน (forward-fill) → ผลตอบแทน/ร่วงสูงสุดเมื่อคิดเป็นบาท.

    วันที่ไม่มีค่าเงินใช้ได้ถูกข้าม · เหลือไม่ถึง 2 วัน → None
    """
    usd, thb, keep = [], [], []
    for d, v in zip(dates, values):
        fx = value_at(points, d)
        if fx is None:
            continue
        usd.append(float(v))
        thb.append(float(v) * float(fx))
        keep.append((d, fx))
    if len(keep) < 2:
        return None
    thb_a = np.asarray(thb)
    dd = thb_a / np.maximum.accumulate(thb_a) - 1
    return {"start": keep[0][0], "end": keep[-1][0], "fx_start": keep[0][1], "fx_end": keep[-1][1],
            "fx_change": float(keep[-1][1] / keep[0][1] - 1),
            "ret_usd": usd[-1] / usd[0] - 1, "ret_thb": thb[-1] / thb[0] - 1, "max_dd_thb": float(dd.min())}


def week_ends(dates: list[str]) -> list[int]:
    """index ของวันทำการสุดท้ายในแต่ละสัปดาห์ (ISO week)."""
    out = []
    for i, d in enumerate(dates):
        wk = date.fromisoformat(d).isocalendar()[:2]
        if out and date.fromisoformat(dates[out[-1]]).isocalendar()[:2] == wk:
            out[-1] = i
        else:
            out.append(i)
    return out


def rate_sensitivity(dates: list[str], P, rate_rows, w, min_weeks: int = RATE_MIN_WEEKS) -> dict:
    """ถดถอยผลตอบแทนรายสัปดาห์ของหุ้นกับการเปลี่ยนของ DGS10 (จุด%) → "ดอกเบี้ย +1% หุ้นขยับ b%".

    เป็นความสัมพันธ์ในอดีตแบบตัวแปรเดียว (รวมผลที่ตลาดทั้งก้อนขยับตามดอกเบี้ยด้วย) ไม่ใช่ duration ของหุ้น
    พอร์ตถ่วงน้ำหนักคงที่ → b พอร์ต = Σ wᵢ bᵢ (OLS เป็นเชิงเส้นในตัวแปรตาม)
    """
    pts = series_points(rate_rows)
    n = np.asarray(P).shape[1]
    empty = {"stocks": [None] * n, "portfolio": None, "weeks": 0, "start": None, "end": None,
             "y_start": None, "y_end": None}
    if not pts:
        return empty
    keep, ys = [], []
    for i in week_ends(dates):
        y = value_at(pts, dates[i])
        if y is not None:
            keep.append(i)
            ys.append(float(y))
    if len(keep) - 1 < min_weeks:
        return {**empty, "weeks": max(len(keep) - 1, 0)}
    Pw = np.asarray(P, float)[keep]
    R = Pw[1:] / Pw[:-1] - 1
    dy = np.diff(np.asarray(ys))
    var = float(np.var(dy, ddof=1))
    if var <= 1e-12:
        return {**empty, "weeks": len(dy)}

    def fit(r):
        b = float(np.cov(r, dy, ddof=1)[0, 1] / var)
        rho = float(np.corrcoef(r, dy)[0, 1])
        return {"b": b, "r2": rho * rho}

    w = np.asarray(w, float)
    return {"stocks": [fit(R[:, j]) for j in range(n)], "portfolio": fit(R @ w), "weeks": len(dy),
            "start": dates[keep[0]], "end": dates[keep[-1]],
            "y_start": Decimal(str(ys[0])), "y_end": Decimal(str(ys[-1]))}


def signed_pct(x: Decimal | None) -> str:
    return "[ข้อมูลไม่พอ]" if x is None else f"{x:+}%"


# ================================================================ ตารางปรับพอร์ต
def rebalance_table(tickers, cur: list[Decimal], tgt: list[Decimal], band: Decimal = REBAL_BAND) -> list[dict]:
    """ห่างเกิน ±band จุด% → เพิ่มน้ำหนัก / ลดน้ำหนัก · ไม่เกิน → คง."""
    out = []
    for t, a, b in zip(tickers, cur, tgt):
        diff = b - a
        action = "เพิ่มน้ำหนัก" if diff > band else "ลดน้ำหนัก" if diff < -band else "คง"
        out.append({"ticker": t, "current": a, "target": b, "diff": diff, "action": action})
    return out


# ================================================================ แนวทางลดความเสี่ยง (แม่แบบประโยค)
def metric_label(m: str) -> str:
    return "กระจุกตัวในอุตสาหกรรม" if m == "sector" else HEAT[m]["label"]


def sector_hedge(warn: dict) -> dict:
    """แม่แบบของเพดานรายอุตสาหกรรม · ระดับตาม SECTOR_SCORE."""
    names = ", ".join(warn["tickers"])
    text = (f"กลุ่ม {warn['sector']} รวม {warn['weight']}% ของพอร์ต ({names}) ถ้าอุตสาหกรรมนี้เจอข่าวร้าย "
            f"หลายตัวมักลงพร้อมกัน — แนวทาง: ลดน้ำหนักบางตัวในกลุ่มนี้ หรือเพิ่มน้ำหนักหุ้นกลุ่มอื่น "
            f"ให้กลุ่มนี้ต่ำกว่าเพดานเตือน {SECTOR_SOFT}%")
    return {"metric": "sector", "score": SECTOR_SCORE[warn["level"]], "text": text}


def top_hedges(port_cells: dict, ctx: dict, k: int = 3, extras: list[dict] | None = None) -> list[dict]:
    """เลือก k มิติที่ระดับพอร์ตแย่สุด (ระดับ ≥ 3) แล้วเติมแม่แบบ · ใช้คำ เพิ่มน้ำหนัก/ลดน้ำหนัก/คง/เฝ้าระวัง เท่านั้น.

    ctx ต้องมี: tickers, w_disp, vol (list %), beta (list), dd (list %|None), dd_label, corr (list|None),
    liq (list Decimal|None), rate (list % ต่อดอกเบี้ย +1%|None)
    extras = แนวทางที่สร้างไว้แล้ว (เช่น sector_hedge) ลงแข่งจัดอันดับด้วยระดับเดียวกัน
    """
    extra_map = {e["metric"]: e for e in (extras or []) if e["score"] >= 3}
    cand = [(m, c["score"]) for m, c in port_cells.items() if c["score"] is not None and c["score"] >= 3]
    cand += [(m, e["score"]) for m, e in extra_map.items()]
    order = lambda m: HEAT_ORDER.index(m) if m in HEAT_ORDER else len(HEAT_ORDER)
    ranked = sorted(cand, key=lambda x: (-x[1], order(x[0])))[:k]
    if not ranked:
        return [{"metric": None, "score": None,
                 "text": "ทุกมิติของพอร์ตอยู่ระดับ 1–2 — แนวทาง: คงสัดส่วนเดิม และเฝ้าระวังด้วยการทบทวนเป็นระยะ"}]
    t, wd = ctx["tickers"], ctx["w_disp"]
    held = [i for i, x in enumerate(wd) if x > 0]

    def pick(values, worst_high=True):
        cand = [i for i in held if values[i] is not None]
        if not cand:
            return None
        return (max if worst_high else min)(cand, key=lambda i: values[i])

    out = []
    for m, s in ranked:
        if m in extra_map:
            out.append(extra_map[m])
            continue
        pc = port_cells[m]["text"]
        if m == "weight":
            i = pick(wd)
            text = (f"{t[i]} มีน้ำหนัก {wd[i]}% ของพอร์ต ถ้าตัวนี้ร่วงแรง ทั้งพอร์ตจะเจ็บตามมาก — "
                    f"แนวทาง: ลดน้ำหนัก {t[i]} ให้ต่ำกว่าเพดานเตือน {SOFT_CAP}% หรือเฝ้าระวังข่าวของตัวนี้ใกล้ชิด")
        elif m == "vol":
            i = pick(ctx["vol"])
            text = (f"พอร์ตแกว่งขึ้นลงราว {pc} ต่อปี ตัวที่แกว่งแรงสุดคือ {t[i]} ({ctx['vol'][i]}%) — "
                    f"แนวทาง: ลดน้ำหนัก {t[i]} หรือเพิ่มน้ำหนักตัวที่แกว่งน้อยกว่า")
        elif m == "beta":
            hi = [t[i] for i in held if ctx["beta"][i] >= Decimal("1.2")]
            names = ", ".join(hi) if hi else t[pick(ctx["beta"])]
            text = (f"β พอร์ต {pc} = ตลาดลง 10% พอร์ตมักลงราว {(D(pc) * 10).quantize(Decimal('0.1'))}% — "
                    f"แนวทาง: ลดน้ำหนักตัว β สูง ({names}) ถ้ารับการขยับแรงกว่าตลาดไม่ไหว")
        elif m == "dd":
            i = pick([None if x is None else -x for x in ctx["dd"]])
            text = (f"ถ้าถือชุดนี้ไว้ในช่วง{ctx['dd_label']} พอร์ตเคยลงจากยอดถึง {pc} "
                    f"ตัวที่ลงหนักสุดคือ {t[i]} ({ctx['dd'][i]}%) — "
                    f"แนวทาง: เฝ้าระวัง {t[i]} และเตรียมใจว่าวิกฤตแบบนี้เกิดซ้ำได้")
        elif m == "corr":
            low = pick(ctx["corr"], worst_high=False) if ctx["corr"] else None
            extra = f" เช่น {t[low]} (correlation {num(ctx['corr'][low])})" if low is not None else ""
            text = (f"หุ้นในพอร์ตขยับไปทางเดียวกันเฉลี่ย {pc} การกระจายจึงช่วยได้น้อย — "
                    f"แนวทาง: เพิ่มน้ำหนักตัวที่ขยับไม่ค่อยตามหุ้นหลัก{extra}")
        elif m == "rate":
            i = pick([None if x is None else abs(x) for x in ctx["rate"]])
            text = (f"ช่วง 3 ปีที่ผ่านมา เมื่อดอกเบี้ยพันธบัตรสหรัฐ 10 ปีขึ้น 1% พอร์ตนี้เคยขยับราว {pc} "
                    f"ตัวที่ไวต่อดอกเบี้ยสุดคือ {t[i]} ({signed_pct(ctx['rate'][i])}) — "
                    f"แนวทาง: เฝ้าระวังช่วงดอกเบี้ยเปลี่ยนเร็ว หรือลดน้ำหนัก {t[i]} ถ้ารับการแกว่งตามดอกเบี้ยไม่ไหว")
        elif m == "liq":
            i = pick([None if x is None else -x for x in ctx["liq"]])
            text = (f"{t[i]} มีเงินหมุนเวียนในตลาดเฉลี่ยแค่ {usd_compact(ctx['liq'][i])} ต่อวัน ถ้าต้องใช้เงินด่วน "
                    f"อาจต้องยอมรับราคาที่แย่ลง — แนวทาง: เฝ้าระวังขนาดที่ถือเทียบกับสภาพคล่อง")
        else:
            continue
        out.append({"metric": m, "score": s, "text": text})
    return out


# ================================================================ ประโยคแปลความใต้ตัวเลข
def explain_beta(b: str) -> str:
    return f"β {b} = ตลาดขึ้นหรือลง 1% พอร์ตมักขยับตามราว {b}%"


def explain_vol(v: str) -> str:
    return f"ปีปกติ ผลตอบแทนของพอร์ตมักเหวี่ยงห่างค่าเฉลี่ยราว ±{v} (ราว 2 ใน 3 ของปีอยู่ในกรอบนี้)"


def explain_dd(dd, label: str | None) -> str:
    if dd is None:
        return "ไม่มีข้อมูลช่วงวิกฤตครบทุกตัว จึงคำนวณไม่ได้"
    left = (Decimal(100) + dd).quantize(Decimal("0.01"))
    return f"ช่วง{label} ถ้าถือชุดนี้ เงิน 100 บาทที่จุดสูงสุดเคยเหลือ {left} บาทก่อนฟื้น"


def explain_unsys(share: str) -> str:
    return (f"ความเสี่ยง {share} มาจากตัวบริษัทเอง (กระจายหุ้นช่วยลดได้) "
            f"ส่วนที่เหลือมาจากตลาดทั้งก้อน (กระจายเท่าไรก็ไม่หาย)")


def explain_er(e: str) -> str:
    return f"ตามทฤษฎี CAPM พอร์ตนี้ควรให้ผลตอบแทนราว {e} ต่อปี — เป็นค่าตามทฤษฎี ไม่ใช่คำสัญญา"


def explain_corr(c: str) -> str:
    return (f"correlation เฉลี่ย {c}: ใกล้ 1 = หุ้นขึ้นลงพร้อมกันเกือบทุกวัน (กระจายไม่ช่วย) · "
            f"ใกล้ 0 = ต่างคนต่างไป (กระจายช่วยมาก)")


def explain_rate(b: Decimal | None, r2: float | None = None) -> str:
    if b is None:
        return "ข้อมูลดอกเบี้ยไม่พอ จึงคำนวณไม่ได้"
    way = "ลง" if b < 0 else "ขึ้น"
    text = (f"ช่วง 3 ปีที่ผ่านมา สัปดาห์ที่ดอกเบี้ยพันธบัตร 10 ปีขึ้น 1% พอร์ตมัก{way}ราว {abs(b)}% "
            f"(ดอกเบี้ยลง 1% ก็มักขยับกลับทิศเท่ากัน)")
    if r2 is not None and r2 < RATE_WEAK_R2:
        text += (f" — แต่ r² แค่ {num(r2)} (ต่ำกว่า {RATE_WEAK_R2}) แปลว่าดอกเบี้ยอธิบายการขยับของพอร์ตได้น้อยมาก "
                 f"ตัวเลขนี้จึงเป็นแนวโน้มอ่อน ๆ ไม่ใช่กฎ")
    return text


def explain_fx(rate: Decimal) -> str:
    return (f"วันนี้ 1 ดอลลาร์ = {rate} บาท · ถ้าบาทแข็งขึ้น 10% มูลค่าพอร์ตเป็นบาทจะลดราว 10% "
            f"แม้ราคาหุ้นไม่ขยับเลย (และกลับกันถ้าบาทอ่อน)")


def explain_eff(n) -> str:
    return f"เทียบเท่ากับถือหุ้นน้ำหนักเท่ากันราว {n} ตัว — ยิ่งน้อยยิ่งกระจุก"
