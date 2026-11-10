#!/usr/bin/env python3
"""portfolio-risk — ดึงข้อมูลดิบทั้งหมดที่ optimize.py ต้องใช้ แล้วเขียนเป็น JSON ไฟล์เดียว.

รันด้วย marketdata venv เท่านั้น (ต้องใช้ yfinance/fredapi):
  __FRIDAY_ROOT__/tools/marketdata/.venv/bin/python fetch.py \
      --tickers AAPL MSFT --out __FRIDAY_ROOT__/scratch/portfolio-risk/<run>.json

ไม่คำนวณอะไรเลย — แค่ดึงแล้วบันทึก as-of/tier ของทุกชุด.
ชุดเสริม (ค่าเงิน DEXTHUS · ดอกเบี้ย DGS10 · อุตสาหกรรม Nasdaq) ดึงไม่ได้ → เก็บ error ไว้ ไม่หยุดงาน ตัดสินว่าข้อมูลพอไหมเป็นงานของ optimize.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

FRIDAY = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(FRIDAY / "tools" / "marketdata"))
import core  # noqa: E402

INDEX_TICKER = "^GSPC"      # ใช้หา β / correlation (ดัชนีราคา)
INDEX_FALLBACK = "SPY"      # ถ้า ^GSPC ได้ NO_DATA
LIQ_DAYS = 63               # ราว 3 เดือนทำการ — ใช้คิดมูลค่าซื้อขายเฉลี่ยต่อวัน
MARKET_TICKER = "SPY"       # ใช้ทำ r_M (adj_close รวมปันผล)
RF_SERIES = "DTB3"          # ตั๋วเงินคลัง 3 เดือน (% ต่อปี)
FX_SERIES = "DEXTHUS"       # บาทต่อ 1 ดอลลาร์ (รายวัน)
RATE_SERIES = "DGS10"       # ดอกเบี้ยพันธบัตรรัฐบาลสหรัฐ 10 ปี (% ต่อปี รายวัน)
STRESS_WINDOWS = {          # end เป็นแบบไม่รวมวันสุดท้าย (yfinance) จึงเลื่อนไป 1 วัน
    "covid_2020": ("2020-02-01", "2020-05-01", "โควิด ก.พ.–เม.ย. 2020"),
    "y2022": ("2022-01-01", "2023-01-01", "ดอกเบี้ยขึ้น ปี 2022"),
}


def years_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29 ก.พ.
        return d.replace(year=d.year - years, day=28)


def get_prices(ticker: str, start: str, end: str, liq_days: int = 0) -> dict:
    """คืน {"prices": [[date, adj_close], ...], meta} หรือ {"error": code, "message": ...}.

    liq_days > 0 → แนบ "liq": [[date, close, volume], ...] ของ liq_days วันทำการท้ายสุด
    (ราคาปิดจริง ไม่ปรับปันผล × จำนวนหุ้น = มูลค่าซื้อขาย · ใช้คิดสภาพคล่องและมูลค่าตามจำนวนหุ้น)
    """
    try:
        r = core.fetch_price(ticker, start=start, end=end, market="US")
    except core.MarketDataError as e:
        return {"error": e.code, "message": e.message}
    except Exception as e:  # noqa: BLE001 — network/parse error ของ yfinance
        return {"error": type(e).__name__, "message": str(e)}
    rows = [[row["date"], row["adj_close"]] for row in r["data"] if row.get("adj_close") is not None]
    if not rows:
        return {"error": "NO_DATA", "message": f"{ticker}: ไม่มี adj_close"}
    m = r["metadata"]
    out = {"ticker_used": r["ticker_used"], "prices": rows,
           "source": m["source"], "source_tier": m["source_tier"], "as_of": m["as_of"]}
    if liq_days:
        out["liq"] = [[row["date"], row["close"], row["volume"]] for row in r["data"]
                      if row.get("close") is not None and row.get("volume") not in (None, "None")][-liq_days:]
    return out


def get_series(series_id: str, start: str, end: str) -> dict:
    """FRED ช่วง start–end → {"rows": [[date, value], ...], meta} หรือ {"error": ...}."""
    try:
        m = core.fetch_macro(series_id, start=start, end=end)
    except core.MarketDataError as e:
        return {"error": e.code, "message": e.message}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__, "message": str(e)}
    return {"series_id": series_id, "rows": [[r["date"], r["value"]] for r in m["data"]],
            "source": m["metadata"]["source"], "source_tier": m["metadata"]["source_tier"],
            "as_of": m["metadata"]["as_of"]}


def get_sectors(tickers: list[str]) -> dict:
    """อุตสาหกรรมจาก Nasdaq screener (tier 3) · us_only=False กันหุ้นต่างชาติที่จดในสหรัฐหาย ·
    ETF ไม่อยู่ใน screener → ไม่มีใน map (optimize.py จัดเป็นกลุ่ม "ETF / ไม่ทราบ")."""
    try:
        u = core.fetch_universe(us_only=False)
    except core.MarketDataError as e:
        return {"error": e.code, "message": e.message}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__, "message": str(e)}
    by_sym = {r["symbol"]: r for r in u["universe"]}          # screener แปลงคลาสรองเป็น BRK-B แล้ว
    found = {}
    for t in tickers:
        r = by_sym.get(core.us_class_ticker(t))
        if r:
            found[t] = {"sector": r["sector"], "industry": r.get("industry")}
    m = u["metadata"]
    return {"map": found, "source": m["source"], "source_tier": m["source_tier"], "as_of": m["as_of"],
            "warnings": m.get("exchange_warnings")}


def main() -> int:
    ap = argparse.ArgumentParser(description="ดึงข้อมูลให้ portfolio-risk")
    ap.add_argument("--tickers", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    tickers = []
    for t in a.tickers:
        t = t.strip().upper()
        if t and t not in tickers:
            tickers.append(t)
    non_us = [t for t in tickers if core.is_non_us(t)]
    if non_us:
        print(f"STOP: สกิลนี้รับเฉพาะหุ้นสหรัฐ — ตัวที่ไม่ใช่: {', '.join(non_us)}", file=sys.stderr)
        return 2

    today = date.today()
    w_start = years_back(today, 3).isoformat()
    w_end = (today + timedelta(days=1)).isoformat()

    index = get_prices(INDEX_TICKER, w_start, w_end)
    index_ticker, index_fallback = INDEX_TICKER, False
    if "error" in index:
        index = get_prices(INDEX_FALLBACK, w_start, w_end)
        index_ticker, index_fallback = INDEX_FALLBACK, True
    if "error" in index:
        print(f"STOP: ดึงดัชนีไม่ได้ทั้ง {INDEX_TICKER} และ {INDEX_FALLBACK}: {index['message']}",
              file=sys.stderr)
        return 2

    stocks = {t: get_prices(t, w_start, w_end, liq_days=LIQ_DAYS) for t in tickers}

    stress = {}
    for key, (s, e, label) in STRESS_WINDOWS.items():
        stress[key] = {"label": label, "start": s, "end_exclusive": e,
                       "index": get_prices(index_ticker, s, e),
                       "stocks": {t: get_prices(t, s, e) for t in tickers}}

    market = get_prices(MARKET_TICKER, years_back(today, 20).isoformat(), w_end)
    if "error" not in market:
        p = market.pop("prices")
        market["first"], market["last"], market["rows"] = p[0], p[-1], len(p)

    try:
        m = core.fetch_macro(RF_SERIES, limit=5)
        last = m["data"][-1]
        rf = {"series_id": RF_SERIES, "date": last["date"], "value_pct": last["value"],
              "source": m["metadata"]["source"], "source_tier": m["metadata"]["source_tier"],
              "as_of": m["metadata"]["as_of"]}
    except core.MarketDataError as e:
        rf = {"error": e.code, "message": e.message}

    fx_start = min([w_start] + [s for s, _, _ in STRESS_WINDOWS.values()])
    fx = get_series(FX_SERIES, fx_start, w_end)
    rates = get_series(RATE_SERIES, w_start, w_end)
    sectors = get_sectors(tickers)

    out = {
        "run": {"as_of": today.isoformat(), "window_start": w_start, "window_end_exclusive": w_end,
                "tickers": tickers},
        "index": {"ticker": index_ticker, "fallback": index_fallback, **index},
        "stocks": stocks,
        "stress": stress,
        "market": {"ticker": MARKET_TICKER, "years": 20, **market},
        "rf": rf,
        "fx": fx,
        "rates": rates,
        "sectors": sectors,
    }
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    errs = [t for t, s in stocks.items() if "error" in s]
    print(json.dumps({"out": str(path), "tickers": tickers, "index": index_ticker,
                      "index_fallback": index_fallback, "stock_errors": errs,
                      "market_error": market.get("error"), "rf_error": rf.get("error"),
                      "fx_error": fx.get("error"), "rates_error": rates.get("error"),
                      "sectors_error": sectors.get("error"),
                      "sectors_missing": [t for t in tickers if t not in sectors.get("map", {})]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
