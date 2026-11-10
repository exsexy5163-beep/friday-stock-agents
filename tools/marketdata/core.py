#!/usr/bin/env python3
"""marketdata core — แกนกลางดึงข้อมูลการเงิน ใช้ร่วมกันโดย cli.py และ mcp_server.py.

หลักการ (CLAUDE.md §7 — ความถูกต้อง + ความเป็นทางการ):
  ชั้น 1 ทางการ = SEC EDGAR (งบ/insider/ownership US) · FRED (มหภาค)
  ชั้น 2 aggregator (ธง) = FMP stable/ (ratio)
  ชั้น 3 รอง (ธง) = yfinance (ราคา) · alpha-vantage (สำรอง) · FMP estimates (คาดการณ์)

สัญญาของไฟล์นี้ (สำคัญ):
  • ฟังก์ชัน fetch_* คืน dict ที่ JSON-serializable เสมอ (data + metadata) — **ไม่ print อะไรทั้งสิ้น**
    (mcp_server ใช้ stdio: print หลงเข้า stdout = พัง JSON-RPC).
  • error ที่คาดได้ → raise MarketDataError (โครงสร้างชัด); error ไม่คาด → ปล่อย exception ขึ้นไป
    ให้ผู้เรียก (mcp_server/cli) จัดการ.
  • ตัวเลขการเงิน serialize เป็น string เสมอ (กัน float precision หาย — CLAUDE.md §8);
    การคำนวณที่ต้องแม่น (เช่น value = shares×price) ใช้ decimal.Decimal.
  • CLI = ดึงข้อมูลดิบ; การวิเคราะห์/คำนวณ ratio ทำในเอเจนต์บน main .venv.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

_IDENTITY_FILE = Path(__file__).with_name(".edgar-identity")


def _load_edgar_identity() -> str:
    """SEC บังคับใส่อีเมลเป็นป้ายชื่อ (ไม่ลับ) · setup.sh เก็บค่าที่ผู้ติดตั้งกรอกไว้ในไฟล์นี้."""
    value = os.environ.get("EDGAR_IDENTITY", "").strip()
    if value:
        return value
    try:
        return _IDENTITY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


EDGAR_IDENTITY = _load_edgar_identity()
KEYCHAIN_ACCOUNT = "friday"

VALID_MARKETS = ("US", "TH", "AUTO")

# suffix ของตลาดนอกสหรัฐ (yahoo-style) — ใช้ตัดสินว่า ticker "ไม่ใช่ US" แทนการดูว่า "มีจุด"
# หุ้นสหรัฐคลาสรอง (BRK.B, BF.B) ก็มีจุดเหมือนกัน การเหมารวมทำให้ tier-1 ใช้ไม่ได้ทั้งที่ EDGAR มีข้อมูล
NON_US_SUFFIXES = (".BK", ".HK", ".T", ".TO", ".V", ".L", ".SS", ".SZ", ".AX", ".NS", ".BO",
                   ".SI", ".KS", ".KQ", ".TW", ".TWO", ".DE", ".F", ".PA", ".MI", ".MC", ".AS",
                   ".BR", ".LS", ".SW", ".ST", ".HE", ".OL", ".CO", ".VI", ".IS", ".SA", ".MX",
                   ".JO", ".NZ", ".JK", ".KL", ".TA")


def is_non_us(ticker: str) -> bool:
    """ticker เป็นของตลาดนอกสหรัฐหรือไม่ — ดูจาก suffix จริง ไม่ใช่ 'มีจุด'."""
    t = (ticker or "").strip().upper()
    return any(t.endswith(sfx) for sfx in NON_US_SUFFIXES)


def us_class_ticker(ticker: str) -> str:
    """หุ้นสหรัฐคลาสรอง → รูปขีดกลาง ซึ่งเป็นรูปที่ผู้ให้บริการรับตรงกันทุกเจ้า.

    วัดจริง 2026-08-26: EDGAR รับทั้ง 'BRK.B' และ 'BRK-B'; **yfinance รับเฉพาะ 'BRK-B'**
    ('BRK.B' คืน 0 แถว); Nasdaq screener คืนมาเป็น 'BRK/B' ซึ่งไม่มีเจ้าไหนรับ → รวมเป็นขีดกลาง.
    """
    t = (ticker or "").strip()
    return t.replace(".", "-").replace("/", "-") if not is_non_us(t) else t


# ---------------------------------------------------------------- error type
class MarketDataError(Exception):
    """error ที่คาดการณ์ได้ — พกพา metadata พอให้ผู้เรียกสร้าง structured error/CLI message."""

    def __init__(self, code: str, message: str, *, recoverable: bool = True,
                 provider: str | None = None, source: str | None = None,
                 source_tier: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.provider = provider
        self.source = source
        self.source_tier = source_tier


# ---------------------------------------------------------------- secrets / time
def keychain(service: str) -> str | None:
    """อ่าน secret จาก macOS Keychain (แพตเทิร์นเดียวกับ smoke_test.py).

    subprocess ใช้ list args + shell=False เสมอ; ไม่ log/return ค่า key ที่ไหนนอกจากผู้เรียกโดยตรง.
    """
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def keychain_present(service: str) -> bool:
    """เช็คว่ามี secret ใน Keychain ไหมโดยอ่านเฉพาะ metadata ไม่อ่านค่า secret."""
    try:
        subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", KEYCHAIN_ACCOUNT],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def today_iso() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def require_us(ticker: str, subcommand: str) -> None:
    """subcommand นอกจาก price รองรับ US เท่านั้น — ticker ไทย (.BK ฯลฯ) ต้อง error ชัด.

    ตัดสินจาก suffix ตลาด (NON_US_SUFFIXES) ไม่ใช่ 'มีจุด' — ไม่งั้น BRK.B/BF.B ซึ่งเป็นหุ้นสหรัฐแท้
    จะถูกปฏิเสธ แล้วเอเจนต์เข้าใจผิดว่า tier 1 ใช้ไม่ได้ → ข้ามไปหาเว็บโดยไม่จำเป็น."""
    if is_non_us(ticker):
        raise MarketDataError(
            "UNSUPPORTED_MARKET",
            f"'{subcommand}' รองรับหุ้น US เท่านั้น (ticker '{ticker}' ไม่ใช่ US). "
            f"งบ/ข้อมูลไทย: ดึงมือจากเว็บ SET / 56-1 / IR — ดู waterfall ชั้นไทย (manual).",
            recoverable=False, provider="edgar",
        )


def _set_edgar_identity(set_identity) -> None:
    """set_identity + แก้ลิงก์หน้าสารบัญ filing ของ edgartools 5.36.0.
    SEC ตอบ 403 กับรูปสั้น /data/<cik>/<accession>-index.html (พบ 2026-10-08) → f.html()/f.text()
    ล้มด้วย 'NoneType' ... 'download' · ใช้รูปในโฟลเดอร์แทน เหมือน upstream GH #1421 (edgartools 5.61.0)
    อัปเกรด edgartools ถึง 5.61.0 แล้วลบส่วน override นี้ได้."""
    if not EDGAR_IDENTITY:
        raise MarketDataError(
            "MISSING_SECRET",
            "ยังไม่ได้ตั้งอีเมลสำหรับ SEC — รัน ./setup.sh แล้วกรอกอีเมลของคุณ",
            recoverable=False, provider="edgar",
        )
    set_identity(EDGAR_IDENTITY)
    try:
        from edgar._filings import Filing
    except ImportError:   # edgar ปลอมในชุดทดสอบ offline
        return
    if getattr(Filing, "_friday_index_url_fix", False):
        return
    Filing.homepage_url = property(
        lambda self: f"https://www.sec.gov/Archives/edgar/data/{self.cik}/"
                     f"{self.accession_no.replace('-', '')}/{self.accession_no}-index.html"
    )
    Filing._friday_index_url_fix = True


# ---------------------------------------------------------------- numeric helpers
def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float_or_none(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # กรอง NaN


def _price_num(v) -> str | None:
    """ราคาตลาด → string ปัด 4 ตำแหน่ง (กัน float artifact เช่น 308.739990234375); NaN/None → None."""
    f = _float_or_none(v)
    return _plain_num(round(f, 4)) if f is not None else None


def _plain_num(v) -> str | None:
    """ตัวเลข → plain decimal string (ไม่มีคอมมา ไม่มี sci-notation) เก็บ precision; NaN/None → None.

    ใช้กับ JSON (financials/price) — คอมมาจะทำ JSON พัง, sci-notation ทำลอกเลขผิด.
    """
    import pandas as pd
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        if v is None:
            return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return str(v)
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


# คอลัมน์ภายในของ edgartools ที่เป็น noise สำหรับการวิเคราะห์ — ตัดทิ้งก่อนแสดง
_META_COLS = {"depth", "is_abstract", "is_total", "section", "confidence",
              "level", "dimension", "decimals", "units", "unit", "concept"}


def _fmt_num(v) -> str:
    """แปลงตัวเลขดิบเป็นข้อความอ่านง่ายสำหรับ **display** (CLI) — ไม่มี scientific notation."""
    import pandas as pd
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:  # NaN
        return ""
    if abs(f) >= 1000:                      # ยอดใหญ่ (revenue/asset): จำนวนเต็มคั่นหลักพัน
        return f"{f:,.0f}"
    return f"{f:.4f}".rstrip("0").rstrip(".")  # เลขเล็ก (EPS/ratio): ทศนิยมเท่าที่จำเป็น


def _clean_financial_frame(df, keep_concept: bool = False):
    """ทำความสะอาด financial statement DataFrame ของ edgartools:
    ตัดแถว abstract (หัวข้อเปล่า) + คอลัมน์ภายใน, ใช้ label เป็นชื่อแถว. คืน DataFrame (ค่าตัวเลขดิบ).

    keep_concept=True → คง XBRL concept ไว้เป็นคอลัมน์ (ใช้ฝั่ง JSON/MCP) เพราะ label ของ edgartools
    ซ้ำกันได้ — เช่น EarningsPerShareBasic กับ EarningsPerShareDiluted ใช้ label
    'Earnings Per Share (Derived)' เหมือนกัน; concept ไม่ซ้ำจึงเป็นตัวแยกที่เชื่อถือได้."""
    df = df.copy()
    if df.index.name and "concept" in str(df.index.name).lower():
        df = df.reset_index()
    if "is_abstract" in df.columns:
        df = df[~df["is_abstract"].fillna(False).astype(bool)]
    label_col = next((c for c in ("label", "concept") if c in df.columns), None)
    drop = _META_COLS - {"concept"} if (keep_concept and label_col == "label") else _META_COLS
    df = df.drop(columns=[c for c in df.columns if c.lower() in drop], errors="ignore")
    if label_col and label_col in df.columns:
        df = df.set_index(label_col)
        df.index.name = "line_item"
    return df


def _clean_financial_df(df) -> str:
    """display version (CLI) — เลขมีคอมมาคั่นหลักพัน, คืน to_string()."""
    df = _clean_financial_frame(df)
    for c in df.columns:
        df[c] = df[c].map(_fmt_num)
    return df.to_string()


def _clean_financial_records(df) -> list[dict]:
    """JSON version (MCP) — records [{line_item, concept, "FY 2025": "416161000000", ...}]
    เลขเป็น plain string. concept = XBRL tag ไว้แยกแถวที่ label ซ้ำกัน (มีเมื่อต้นทางให้มา)."""
    df = _clean_financial_frame(df, keep_concept=True)
    has_concept = "concept" in df.columns
    value_cols = [c for c in df.columns if c != "concept"]
    records = []
    for line_item, row in df.iterrows():
        rec = {"line_item": str(line_item)}
        if has_concept:
            rec["concept"] = str(row["concept"]) if row["concept"] is not None else None
        for c in value_cols:
            rec[c] = _plain_num(row[c])
        records.append(rec)
    return records


def _render(stmt) -> str:
    """render statement object → ตารางข้อความ (ใช้โดย CLI financials เพื่อคงรูปแบบเดิม)."""
    for m in ("to_dataframe", "to_pandas"):
        fn = getattr(stmt, m, None)
        if callable(fn):
            try:
                df = fn()
            except Exception:  # noqa: BLE001
                continue
            try:
                return _clean_financial_df(df)
            except Exception:  # noqa: BLE001 — ถ้า schema ไม่ตรง คืน raw กันงานล้ม
                return df.to_string()
    return str(stmt)


# ---------------------------------------------------------------- ticker resolve
def _resolve_ticker(ticker: str, market: str) -> str:
    """US → ตามเดิม; TH → เติม .BK ถ้ายังไม่มี; AUTO → ถือเป็น TH เฉพาะเมื่อมี .BK อยู่แล้ว (ไม่เดา)."""
    t = (ticker or "").strip()
    m = (market or "AUTO").upper()
    if m not in VALID_MARKETS:
        raise MarketDataError("INVALID_INPUT", f"market ต้องเป็นหนึ่งใน {VALID_MARKETS} (ได้ '{market}')",
                              recoverable=False)
    if m == "TH":
        return t if t.upper().endswith(".BK") else t + ".BK"
    # US หรือ AUTO: ไม่เติม .BK เอง แต่แปลงคลาสรองเป็นรูปขีดกลางที่ yfinance รับได้ (BRK.B → BRK-B)
    return us_class_ticker(t)


# ---------------------------------------------------------------- price (yfinance)
def fetch_price(ticker: str, start: str | None = None, end: str | None = None,
                period: str | None = None, interval: str | None = "1d",
                market: str = "AUTO") -> dict:
    """ราคาย้อนหลัง OHLCV (US + ไทย .BK) ผ่าน yfinance. auto_adjust=False → มีทั้ง close และ adj_close."""
    import yfinance as yf
    if not ticker or not ticker.strip():
        raise MarketDataError("INVALID_INPUT", "ต้องระบุ ticker", recoverable=False)
    used = _resolve_ticker(ticker, market)
    iv = interval or "1d"
    kwargs = {"interval": iv, "auto_adjust": False}
    if start or end:
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end
    else:
        kwargs["period"] = period or "1y"

    df = yf.Ticker(used).history(**kwargs)
    if df is None or not len(df):
        raise MarketDataError("NO_DATA", f"No price data returned for ticker {used}",
                              provider="yfinance", source="yfinance", source_tier=3)

    intraday = bool(iv) and iv[-1] in ("m", "h")
    data = []
    for idx, row in df.iterrows():
        d = idx.isoformat() if intraday else idx.date().isoformat()
        data.append({
            "date": d,
            "open": _price_num(row.get("Open")),
            "high": _price_num(row.get("High")),
            "low": _price_num(row.get("Low")),
            "close": _price_num(row.get("Close")),
            "adj_close": _price_num(row.get("Adj Close")),
            "volume": (str(_int_or_none(row.get("Volume")))
                       if _int_or_none(row.get("Volume")) is not None else None),
        })

    notes = []
    if used != ticker:
        notes.append(f"ticker '{ticker}' → '{used}' (market={market})")
    currency = "THB" if used.upper().endswith(".BK") else None  # US/อื่น = None (ไม่เดา)
    return {
        "ticker": ticker,
        "ticker_used": used,
        "data": data,
        "metadata": {"source": "yfinance", "source_tier": 3, "as_of": today_iso(),
                     "interval": iv, "currency": currency, "notes": notes},
    }


# ---------------------------------------------------------------- financials (EDGAR)
_STATEMENT_METHODS = {"income": "income_statement", "balance": "balance_sheet", "cashflow": "cash_flow"}

# ชื่อเมธอดฝั่ง "XBRL ของ filing ฉบับนั้น" (คนละชุดกับฝั่ง company-facts ด้านบน)
_FILING_STMT_METHODS = {"income": ("income_statement",), "balance": ("balance_sheet",),
                        "cashflow": ("cashflow_statement", "cash_flow_statement", "cash_flow")}

# สกุลเงินที่โผล่ใน filing ของ SEC ได้จริง — ใช้เดา presentation currency จากชื่อ unit ของ XBRL
_ISO_CCY = {"USD", "TWD", "EUR", "JPY", "KRW", "GBP", "CAD", "CHF", "CNY", "HKD", "SEK", "NOK",
            "DKK", "AUD", "NZD", "SGD", "BRL", "MXN", "INR", "ILS", "ZAR", "THB", "IDR", "MYR",
            "PHP", "VND", "RUB", "TRY", "PLN", "ARS", "CLP", "COP", "AED", "SAR", "NGN", "EGP"}


def _pick_currency(unit_names) -> str | None:
    """เดาสกุลเงินที่ใช้แสดงงบ จากรายชื่อ unit เรียงตามความถี่ (มากไปน้อย).

    ข้าม unit ที่เป็นอัตราส่วน/ต่อหุ้น ('Unit_Divide_USD_EUR', 'usdPerShare') เพราะไม่ใช่สกุลของงบ.
    ชื่อ unit ไม่มีมาตรฐานเดียว — 'twd' (TSM) กับ 'Unit_Standard_EUR_Dznin...' (SAP) จึงจับด้วยการ
    แยกคำแล้วเทียบกับรายชื่อ ISO."""
    import re as _re
    for name in unit_names:
        s = str(name)
        low = s.lower()
        if "divide" in low or "per" in low or "/" in s:
            continue
        for tok in _re.split(r"[^A-Za-z]+", s):
            if tok.upper() in _ISO_CCY:
                return tok.upper()
    return None


def _records_from_filing_frame(df, years: int) -> list[dict]:
    """แปลงตารางงบที่มาจาก XBRL ของ filing ฉบับเดียว → records แบบเดียวกับฝั่ง company-facts.

    ต่างจากฝั่ง company-facts ตรงที่ตารางนี้มีแถว breakdown ตาม dimension (เช่นแยกตามภูมิภาค)
    ปนมาด้วย ซึ่งใช้ชื่อบรรทัดซ้ำกับแถวรวม → ตัดทิ้ง เหลือเฉพาะแถวยอดรวม."""
    import re as _re
    d = df
    for col, keep_false in (("abstract", True), ("dimension", True), ("is_breakdown", True)):
        if col in d.columns:
            d = d[~d[col].fillna(False).astype(bool)] if keep_false else d
    per_cols = [c for c in d.columns if _re.match(r"^\d{4}-\d{2}-\d{2}", str(c))]
    per_cols = per_cols[:years] if years and years > 0 else per_cols

    # '2025-12-31 (FY)' → 'FY 2025' ให้เข้ารูปเดียวกับฝั่ง company-facts. ถ้าปีชนกัน (บริษัทเปลี่ยน
    # รอบปีบัญชี → มีสองคอลัมน์ในปีเดียว) ต้องไม่ปล่อยให้คอลัมน์หลังทับคอลัมน์แรกเงียบ ๆ → ติดวันที่เต็ม
    col_keys: dict = {}
    used: set[str] = set()
    for c in per_cols:
        key = f"FY {str(c)[:4]}"
        if key in used:
            key = f"FY {str(c)[:4]} ({str(c)[:10]})"
        used.add(key)
        col_keys[c] = key

    records = []
    seen_rows: set = set()
    for _, row in d.iterrows():
        label = str(row.get("label") or row.get("concept") or "").strip()
        if not label:
            continue
        rec = {"line_item": label, "concept": str(row.get("concept") or "") or None}
        empty = True
        for c in per_cols:
            v = _plain_num(row[c])
            rec[col_keys[c]] = v
            if v is not None:
                empty = False
        if empty:
            continue
        # ตาราง XBRL ของ filing เอาแถวยอดรวมมาแสดงซ้ำได้ (TSM: NET INCOME โผล่ 2 รอบค่าเท่ากันเป๊ะ)
        # ผู้เรียกที่บวกรวมแถวจะนับซ้ำ → ตัดแถวที่ซ้ำทั้ง concept/label/ค่าทุกงวดออก
        fingerprint = (rec["concept"], rec["line_item"], tuple(rec[col_keys[c]] for c in per_cols))
        if fingerprint in seen_rows:
            continue
        seen_rows.add(fingerprint)
        records.append(rec)
    return records


def fetch_financials(ticker: str, period: str = "annual",
                     statements: list[str] | None = None, years: int | None = 5) -> dict:
    """งบ US ดิบจาก SEC EDGAR (edgartools). v1 EDGAR-only (ไม่มี FMP fallback)."""
    require_us(ticker, "financials")
    from edgar import set_identity, Company
    _set_edgar_identity(set_identity)

    period = (period or "annual").lower()
    if period not in ("annual", "quarterly"):
        raise MarketDataError("INVALID_INPUT", f"period ต้องเป็น annual หรือ quarterly (ได้ '{period}')",
                              recoverable=False)
    wanted = [s.lower() for s in (statements or ["income", "balance", "cashflow"])]
    bad = [s for s in wanted if s not in _STATEMENT_METHODS]
    if bad:
        raise MarketDataError("INVALID_INPUT",
                              f"statements ไม่รู้จัก: {bad} (รองรับ {list(_STATEMENT_METHODS)})",
                              recoverable=False)
    periods = years if isinstance(years, int) and years > 0 else 5

    c = Company(ticker)
    out_statements: dict[str, list] = {}
    for s in wanted:
        method = getattr(c, _STATEMENT_METHODS[s], None)
        if method is None:
            out_statements[s] = []
            continue
        df = method(periods=periods, period=period, as_dataframe=True)
        out_statements[s] = _clean_financial_records(df) if df is not None and len(df) else []

    if not any(out_statements.values()):
        raise MarketDataError("NO_DATA", f"EDGAR ไม่คืนงบของ {ticker} (period={period})",
                              provider="edgar", source="SEC EDGAR", source_tier=1)

    # filing reference — เลือก "ฉบับที่ยื่นล่าสุด" จากชุดฟอร์มที่ป้อนข้อมูลงวดนี้ได้จริง
    #   annual   : 10-K + 20-F/40-F (FPI ไม่ยื่น 10-K → เดิมได้ null)
    #   quarterly: 10-Q + 10-K ด้วย เพราะคอลัมน์ไตรมาสสุดท้ายของปีบัญชี edgartools derive จากงบปี
    #              (FY − 9 เดือน) → ยึด 10-Q ตายตัวจะแปะที่มาผิดฉบับ
    forms = ("10-K", "20-F", "40-F") if period == "annual" else ("10-Q", "10-K", "20-F", "40-F", "6-K")
    filing_date = accession = filing_form = ref_filing = None
    for f in forms:
        try:
            latest = c.get_filings(form=f).latest()
        except Exception:  # noqa: BLE001 — ฟอร์มที่บริษัทนี้ไม่เคยยื่น
            continue
        if latest is None:
            continue
        d = str(getattr(latest, "filing_date", None) or "") or None
        if d and (filing_date is None or d > filing_date):
            filing_date, accession, filing_form = d, getattr(latest, "accession_no", None), f
            ref_filing = latest

    latest_period = _latest_period(out_statements)

    # ---- ทาง B: อ่านจาก XBRL ของ filing ฉบับนั้นตรง ๆ แทน company-facts ------------------
    # company-facts (data.sec.gov/api/xbrl/companyfacts) เป็น "คลังรวม" ที่ SEC ประมวลเอง และ
    # **ไม่ครบสำหรับผู้ยื่นแบบ IFRS**: TSM ยื่น 20-F ปี FY2025 (มี inline XBRL 10.7MB) แล้ว แต่ใน
    # companyfacts มีแค่ข้อมูลหน้าปก (dei) ตัวเลขงบยังหยุดที่ FY2024 — และตัว fact เดียวกันมีทั้ง
    # หน่วย TWD และ USD (convenience translation) ปนกันโดยชั้นบนไม่เห็นหน่วย → ตารางหน่วยผสม.
    # XBRL ของ filing เองไม่มีปัญหาทั้งสองข้อ (สกุลเดียว + ปีล่าสุด + label ที่บริษัทตั้งเอง).
    data_path, currency, notes = "companyfacts", None, []
    stale = _is_stale(latest_period, ref_filing)
    if period == "annual" and (filing_form in ("20-F", "40-F") or stale):
        try:
            rebuilt, currency = _financials_from_filing(ref_filing, wanted, periods)
        except Exception as e:  # noqa: BLE001 — ล้มแล้วยังมีของเดิมให้ใช้ ดีกว่าไม่คืนอะไร
            notes.append(f"อ่าน XBRL จาก filing ไม่สำเร็จ ({type(e).__name__}) — คืนข้อมูลจาก company-facts แทน "
                         f"ซึ่งอาจเก่ากว่าฉบับที่ยื่นและหน่วยเงินอาจปนกัน")
        else:
            if any(rebuilt.values()):
                out_statements, data_path = rebuilt, "filing-xbrl"
                latest_period = _latest_period(out_statements)
                if stale:
                    notes.append("company-facts ของ SEC ยังไม่มีตัวเลขงวดล่าสุด — อ่านจาก XBRL ของ filing แทน")

    if data_path == "companyfacts":
        currency = _facts_currency(c)
        if filing_form in ("20-F", "40-F"):
            notes.append("ผู้ยื่นต่างชาติ (FPI/IFRS): ตัวเลขจาก company-facts อาจปนหลายสกุลในตารางเดียว "
                         "— ตรวจกับตัวเอกสารด้วย get_filing_text ก่อนอ้าง")

    return {
        "ticker": ticker,
        "period": period,
        "statements": out_statements,
        "note": " | ".join(notes) or None,
        "metadata": {"source": "SEC EDGAR (edgartools)", "source_tier": 1, "as_of": today_iso(),
                     "filing_date": filing_date, "accession": accession, "filing_form": filing_form,
                     "latest_period": latest_period, "currency": currency, "data_path": data_path,
                     "fallback_used": False},
    }


def _latest_period(out_statements: dict) -> str | None:
    """งวดล่าสุดที่ 'มีข้อมูลจริง' ในตาราง — ใช้จับกรณีข้อมูลค้างหลังฉบับที่ยื่นไปแล้ว."""
    for recs in out_statements.values():
        if recs:
            cols = [k for k in recs[0] if k not in ("line_item", "concept")]
            if cols:
                return cols[0]
    return None


def _is_stale(latest_period: str | None, filing) -> bool:
    """ข้อมูลเก่ากว่างวดของ filing ล่าสุดหรือไม่ (เทียบระดับปี)."""
    if not latest_period or filing is None:
        return False
    import re as _re
    m = _re.search(r"(\d{4})", str(latest_period))
    end = str(getattr(filing, "period_of_report", None) or "")
    if not m or len(end) < 4:
        return False
    try:
        return int(end[:4]) > int(m.group(1))
    except ValueError:
        return False


def _facts_currency(company) -> str | None:
    """สกุลเงินหลักของตัวเลขใน company-facts (ตัด unit ที่เป็นต่อหุ้น/อัตราส่วนออก)."""
    try:
        df = company.get_facts().to_dataframe()
        counts = df["unit"].value_counts()
    except Exception:  # noqa: BLE001 — currency เป็น nice-to-have
        return None
    return _pick_currency(list(counts.index))


def _financials_from_filing(filing, wanted: list[str], years: int) -> tuple[dict, str | None]:
    """สร้างงบจาก XBRL ของ filing ฉบับเดียว. คืน (statements, currency)."""
    x = filing.xbrl()
    out: dict[str, list] = {}
    for s in wanted:
        recs = []
        for name in _FILING_STMT_METHODS[s]:
            fn = getattr(x.statements, name, None)
            if fn is None:
                continue
            try:
                df = fn().to_dataframe()
            except Exception:  # noqa: BLE001 — งบบางชนิดไม่มีในฟอร์มนั้น
                continue
            if df is not None and len(df):
                recs = _records_from_filing_frame(df, years)
                break
        out[s] = recs
    currency = None
    try:
        currency = _pick_currency(list(x.query().to_dataframe()["unit_ref"].value_counts().index))
    except Exception:  # noqa: BLE001
        pass
    return out, currency


# ---------------------------------------------------------------- FMP helper (ratios + estimates ใช้ร่วม)
# ข้อความอธิบาย HTTP ที่ FMP ตอบกลับ — ต้อง "บอกความจริง" ไม่ใช่เหมารวมว่าเน็ตพัง
_FMP_STATUS_HINT = {
    401: "API key ไม่ถูกต้องหรือถูกเพิกถอน",
    402: "แพ็กเกจ FMP ปัจจุบันไม่ครอบคลุม ticker นี้ (คำขอไปถึงแล้ว ไม่ใช่เน็ตพัง) "
         "→ ใช้ tier 1 แทน: get_financials/financials จาก SEC EDGAR แล้วคำนวณ ratio เองด้วย Decimal",
    403: "แพ็กเกจปัจจุบันไม่มีสิทธิ์เข้าถึง endpoint นี้",
    429: "ยิงถี่เกินหรือโควตาวันหมด — รอแล้วลองใหม่",
}


def _fmp_get(url: str, endpoint: str) -> tuple[object | None, str | None, str | None]:
    """ยิง FMP แล้วคืน (json, error_code, ข้อความ). สำเร็จ → (json, None, None).

    ทำไมต้องมีตัวกลางนี้: `requests.exceptions.JSONDecodeError` เป็น **คลาสลูกของ
    `requests.RequestException`** (ตั้งแต่ requests 2.27) — เดิม `requests.get()` กับ `r.json()`
    อยู่ใน try เดียวกันที่ดัก `RequestException` ผลคือคำตอบที่ไม่ใช่ JSON ถูกรายงานเป็น
    "เรียก FMP ไม่ได้" (เน็ตพัง) ทั้งที่คำขอไปถึงและ FMP ตอบกลับมาแล้ว และไม่เคยแสดง status code
    วัดจริง 2026-09-03: FMP ตอบ **HTTP 402 พร้อม body ที่ไม่ใช่ JSON** เมื่อ ticker อยู่นอกชุดที่
    แพ็กเกจครอบคลุม (AAPL/MSFT/META/JNJ/XOM/V ผ่าน · TER/COHU/KEYS/ATEYY/BRK.B ได้ 402 ทุก endpoint)
    → ข้อความเดิมชี้ผิดทางทั้งหมด ทำให้เอเจนต์เข้าใจว่าเน็ตล่มแทนที่จะรู้ว่าต้องขึ้นไป tier 1

    ห้ามใส่ `str(e)` ลงข้อความเด็ดขาด — ข้อความ exception ของ requests พก URL เต็ม (มี apikey) มาด้วย
    """
    import requests
    try:
        r = requests.get(url, timeout=25)
    except requests.RequestException as e:
        return None, "NETWORK_ERROR", f"เรียก FMP ไม่ได้: {type(e).__name__}"
    if r.status_code != 200:
        code = {401: "MISSING_SECRET", 402: "PLAN_LIMITED", 403: "PLAN_LIMITED",
                429: "RATE_LIMITED"}.get(r.status_code, "UPSTREAM_ERROR")
        hint = _FMP_STATUS_HINT.get(r.status_code, "FMP ปฏิเสธคำขอ")
        return None, code, f"{endpoint} ตอบ HTTP {r.status_code} — {hint}"
    try:
        return r.json(), None, None
    except ValueError:
        return None, "UPSTREAM_ERROR", f"{endpoint} ตอบ HTTP 200 แต่เนื้อคำตอบไม่ใช่ JSON"


# ---------------------------------------------------------------- ratios (FMP stable/)
def fetch_ratios(ticker: str, period: str = "annual", limit: int = 5) -> dict:
    """ratio สำเร็จรูป จาก FMP stable/ratios (ห้าม v3). aggregator ชั้น 2 — ควร verify กับงบ EDGAR."""
    require_us(ticker, "ratios")
    key = keychain("fmp-api")
    if not key:
        raise MarketDataError("MISSING_SECRET",
                              "ไม่มี fmp-api ใน Keychain — ทางเลือก: คำนวณ ratio จากงบ EDGAR ด้วย Decimal",
                              recoverable=False, provider="fmp", source="FMP stable", source_tier=2)
    limit = limit if isinstance(limit, int) and limit > 0 else 5
    # ส่ง period ไปจริง — เดิมรับพารามิเตอร์นี้แล้ว "ทิ้ง" ผู้เรียกที่ขอ quarter จึงได้ annual เงียบ ๆ
    # (วัดจริง 2026-09-03: ไม่ใส่ period = annual · period=quarter ได้ 402 พรีเมียมบนแพ็กเกจฟรี)
    url = (f"https://financialmodelingprep.com/stable/ratios?symbol={ticker}"
           f"&period={period}&limit={limit}&apikey={key}")
    j, code, err = _fmp_get(url, "stable/ratios")
    if code:
        raise MarketDataError(code, f"ratio ของ '{ticker}': {err}",
                              recoverable=code in ("NETWORK_ERROR", "RATE_LIMITED", "UPSTREAM_ERROR"),
                              provider="fmp", source="FMP stable", source_tier=2)
    if not (isinstance(j, list) and j):
        raise MarketDataError("NO_DATA",
                              f"FMP ตอบ HTTP 200 แต่ไม่มี ratio ของ '{ticker}' "
                              f"— ใช้ tier 1 (SEC EDGAR) แล้วคำนวณเองด้วย Decimal",
                              provider="fmp", source="FMP stable", source_tier=2)
    return {
        "ticker": ticker,
        "data": j[:limit],
        "metadata": {"source": "FMP stable", "source_tier": 2, "as_of": today_iso(),
                     "endpoint_family": "stable", "fallback_used": False},
    }


# ---------------------------------------------------------------- insider (EDGAR Form 4)
def fetch_insider(ticker: str, limit: int = 20, start: str | None = None,
                  end: str | None = None) -> dict:
    """insider transactions (Form 4) จาก SEC EDGAR. value = shares×price ใช้ Decimal ถ้าต้องคำนวณเอง."""
    require_us(ticker, "insider")
    from edgar import set_identity, Company
    _set_edgar_identity(set_identity)
    limit = limit if isinstance(limit, int) and limit > 0 else 20

    c = Company(ticker)
    recs = []
    for f in list(c.get_filings(form="4")):
        filed = str(getattr(f, "filing_date", "") or "")
        if start and filed and filed < start:
            continue
        if end and filed and filed > end:
            continue
        rec = {"filed": filed or None, "accession": getattr(f, "accession_no", None),
               "url": getattr(f, "url", None)}
        try:
            s = f.obj().get_ownership_summary()
            rec["insider"] = getattr(s, "insider_name", None)
            rec["position"] = getattr(s, "position", None)
            rec["remaining_shares"] = _int_or_none(getattr(s, "remaining_shares", None))
            rec["transactions"] = [_insider_txn(t) for t in (getattr(s, "transactions", []) or [])]
        except Exception:  # noqa: BLE001 — fallback: คืน accession ให้ drill เอง
            rec["enrich_error"] = "เปิด accession เองเพื่อดูรายละเอียด (parse Form 4 ไม่สำเร็จ)"
        recs.append(rec)
        if len(recs) >= limit:
            break

    return {
        "ticker": ticker,
        "data": recs,
        "metadata": {"source": "EDGAR", "source_tier": 1, "as_of": today_iso(), "form_type": "Form 4"},
    }


def _insider_txn(t) -> dict:
    shares = _int_or_none(getattr(t, "shares", None))
    price = _float_or_none(getattr(t, "price_per_share", None))
    value = getattr(t, "value", None)
    value_str = _plain_num(value) if value is not None else None
    calc_note = None
    if value_str is None and shares is not None and price is not None:
        # คำนวณเองด้วย Decimal (กัน float เพี้ยน) — ติดธงว่า derived
        value_str = _plain_num(Decimal(str(shares)) * Decimal(str(price)))
        calc_note = "value = shares × price (คำนวณด้วย Decimal — filing ไม่ได้ระบุตรง)"
    txn = {
        "type": getattr(t, "transaction_type", None),
        "code": getattr(t, "code", None),
        "shares": shares,
        "price_per_share": (_plain_num(price) if price is not None else None),
        "value": value_str,
        "security": getattr(t, "security_title", None),
    }
    if calc_note:
        txn["calculation_note"] = calc_note
    return txn


# ---------------------------------------------------------------- ownership (EDGAR 13D/G)
_OWNERSHIP_FORM_MAP = {"13D": ["SC 13D", "SC 13D/A"], "13G": ["SC 13G", "SC 13G/A"]}


def fetch_ownership(ticker: str, form_types: list[str] | None = None, limit: int = 20) -> dict:
    """ผู้ถือใหญ่/activist (SC 13D/G) จาก SEC EDGAR.

    ⚠️ parser ดึง "ชื่อ" ได้ดี แต่ "%/หุ้น" มักไม่ได้กับ filing ฟอร์แมตเก่า/HTML → คืน null + note
    (ห้ามรายงาน 0% ปลอม). ทุก record มี filing URL ให้เปิดดูค่าจริงเอง.
    """
    require_us(ticker, "ownership")
    from edgar import set_identity, Company
    _set_edgar_identity(set_identity)
    limit = limit if isinstance(limit, int) and limit > 0 else 20

    forms: list[str] = []
    for ft in (form_types or ["13D", "13G"]):
        forms.extend(_OWNERSHIP_FORM_MAP.get(ft.upper().replace("SC ", "").strip(), [ft]))

    c = Company(ticker)
    recs = []
    for f in list(c.get_filings(form=forms)):
        base = {"form": getattr(f, "form", None),
                "filed": str(getattr(f, "filing_date", "") or "") or None,
                "accession": getattr(f, "accession_no", None),
                "url": getattr(f, "url", None)}
        try:
            o = f.obj()
            persons = list(getattr(o, "reporting_persons", []) or [])
        except Exception:  # noqa: BLE001
            persons = None
        if not persons:
            recs.append({**base, "owner": None, "shares": None, "percent_of_class": None,
                         "calculation_note": "parse ไม่สำเร็จ — เปิด filing เพื่อดูผู้ถือ/สัดส่วน"})
        else:
            for rp in persons:
                pct = _float_or_none(getattr(rp, "percent_of_class", None))
                shares = _int_or_none(getattr(rp, "aggregate_amount", None))
                # 0/None = ดึงไม่ได้ (ไม่ใช่ศูนย์จริง) → null + note (ห้ามเดา %)
                pct_out = _plain_num(pct) if pct else None
                shares_out = shares if shares else None
                rec = {**base, "owner": getattr(rp, "name", None),
                       "shares": shares_out, "percent_of_class": pct_out}
                if pct_out is None or shares_out is None:
                    rec["calculation_note"] = ("ตัวเลขไม่ machine-readable ในฟอร์แมต filing นี้ "
                                               "— เปิด filing (url) เพื่อดูค่าจริง")
                recs.append(rec)
        if len(recs) >= limit:
            break

    return {
        "ticker": ticker,
        "data": recs[:limit],
        "metadata": {"source": "EDGAR", "source_tier": 1, "as_of": today_iso()},
    }


# ---------------------------------------------------------------- filings (EDGAR ทุกฟอร์ม)
# ฟอร์มที่ใช้บ่อยในงานวิเคราะห์ — ไม่ใช่ allowlist (ส่งฟอร์มอื่นได้) แค่ใช้เตือนตอนพิมพ์ผิด
KNOWN_FORMS = ("10-K", "10-Q", "8-K", "DEF 14A", "20-F", "40-F", "6-K", "S-1", "424B4", "11-K")

# เพดานความยาวข้อความต่อการเรียก 1 ครั้ง — DEF 14A ยาว ~357k ตัวอักษร, 10-K ~261k
# ถ้าปล่อยไหลเข้ามาทั้งก้อน context ของผู้เรียกจะเต็มทันที → บังคับแบ่งหน้าด้วย offset
FILING_TEXT_MAX_CHARS = 100_000
FILING_TEXT_DEFAULT_CHARS = 20_000


def _filing_date_str(f) -> str:
    return str(getattr(f, "filing_date", "") or "")


def _exhibit_rows(f) -> list[dict]:
    """รายการไฟล์แนบที่เป็นสาระ (EX-*) — ตัด XBRL (EX-101.*) ที่เป็น machine artifact ทิ้ง."""
    rows = []
    for a in getattr(f, "attachments", []) or []:
        dt = str(getattr(a, "document_type", "") or "")
        if not dt.upper().startswith("EX-") or dt.upper().startswith("EX-101"):
            continue
        rows.append({"exhibit": dt,
                     "document": getattr(a, "document", None),
                     "description": getattr(a, "description", None)})
    return rows


def fetch_filings(ticker: str, form: str | None = None, limit: int = 20,
                  start: str | None = None, end: str | None = None,
                  detail: bool = False) -> dict:
    """ลิสต์ filing ของบริษัท US จาก SEC EDGAR (tier 1) — metadata เท่านั้น ไม่ดึงเนื้อ.

    detail=False (default) คืนแค่ form/filed/accession/url — มาจาก index ที่โหลดครั้งเดียว จึง**เร็วมาก**
    detail=True  เติม item code ของ 8-K ('Item 2.02' = ประกาศผลประกอบการ) + รายการ exhibit

    ต้นทุนเวลามี 2 ก้อน แยกกัน (วัดจริง แคชเปล่า):
      1) โหลดสารบัญ filing ของบริษัท — **ครั้งเดียวต่อบริษัทต่อโปรเซส** ~1–13 วิ (WFC 3.7 · GS 13.1)
         เกิดขึ้นเสมอไม่ว่า detail จะเปิดหรือปิด; เรียกซ้ำบริษัทเดิมในโปรเซสเดียวกันจะเร็ว (~1 วิ)
      2) detail=True — ดาวน์โหลดตัว filing **ทีละฉบับ** ~1.2–2.5 วิ/ฉบับ (IBM 8-K 20 ฉบับ = +23.1 วิ)
         อ่าน metadata เปล่า ๆ หลังก้อนที่ 1 แล้ว = 0.03 วิ/20 ฉบับ (แทบไม่มีต้นทุน)
      → limit=100 พร้อม detail=True ≈ 2–4 นาที เสี่ยง client timeout
    (item code กับ exhibits ใช้ไฟล์ดาวน์โหลดก้อนเดียวกัน จึงรวมเป็นสวิตช์เดียว)
    ใช้ท่านี้: detail=False ก่อนเพื่อดูว่ามีฉบับไหนบ้าง → เปิด detail=True กับ limit น้อย ๆ
    เมื่อต้องรู้จริงว่า 8-K แต่ละฉบับแจ้งเรื่องอะไร.
    """
    require_us(ticker, "filings")
    from edgar import set_identity, Company
    _set_edgar_identity(set_identity)
    limit = limit if isinstance(limit, int) and limit > 0 else 20
    form = (form or "").strip() or None

    c = Company(ticker)
    try:
        filings = c.get_filings(form=form) if form else c.get_filings()
    except Exception as e:  # noqa: BLE001
        raise MarketDataError("NO_DATA", f"EDGAR ไม่คืน filing ของ {ticker} (form={form}): {type(e).__name__}",
                              provider="edgar", source="EDGAR", source_tier=1) from e

    total = len(filings)
    is_8k = bool(form) and form.upper().startswith("8-K")
    recs = []
    for f in filings:
        filed = _filing_date_str(f)
        if start and filed and filed < start:
            continue
        if end and filed and filed > end:
            continue
        rec = {"form": str(getattr(f, "form", "") or "") or None,
               "filed": filed or None,
               "accession": getattr(f, "accession_no", None),
               "url": getattr(f, "url", None)}
        if detail:
            # ทั้งสองบรรทัดนี้บังคับให้ดาวน์โหลดตัว filing (~1.2 วิ/ฉบับ) — จึงอยู่หลังสวิตช์เดียวกัน
            if is_8k:
                try:
                    rec["items"] = list(getattr(f.obj(), "items", []) or []) or None
                except Exception:  # noqa: BLE001 — item เป็นของแถม ไม่ใช่ blocker
                    rec["items"] = None
            try:
                rec["exhibits"] = _exhibit_rows(f) or None
            except Exception:  # noqa: BLE001
                rec["exhibits"] = None
        recs.append(rec)
        if len(recs) >= limit:
            break

    note = None
    if form and form.upper().removesuffix("/A") not in {k.upper() for k in KNOWN_FORMS}:
        note = (f"form '{form}' ไม่อยู่ในชุดที่ใช้บ่อย ({', '.join(KNOWN_FORMS)}) — "
                f"ถ้าไม่ได้ผลลัพธ์ ให้ตรวจการสะกดตามชื่อฟอร์มจริงของ SEC")
    # total = จำนวนที่ตรงกับ "ฟอร์ม" เท่านั้น (ยังไม่ผ่านตัวกรองวันที่) — ตั้งชื่อให้ตรงความหมาย
    # กัน ผู้เรียกเห็นเลขใหญ่แล้วนึกว่ายังมีของเหลือให้ขอต่อ ทั้งที่ช่วงวันที่ที่ขอหมดแล้ว
    meta = {"source": "EDGAR", "source_tier": 1, "as_of": today_iso(),
            "form": form, "returned": len(recs), "detail": detail}
    if start or end:
        meta["date_filter"] = {"start": start, "end": end}
        meta["total_matching_form_before_date_filter"] = total
        meta["exhausted"] = len(recs) < limit   # ไล่ครบทุกฉบับในช่วงแล้วหรือยัง
    else:
        meta["total_matching_form"] = total
    return {"ticker": ticker, "data": recs, "note": note, "metadata": meta}


def _pick_filing(c, ticker: str, form: str | None, accession: str | None):
    """เลือก filing ที่จะอ่าน — ระบุ accession = เจาะฉบับ, ไม่ระบุ = ฉบับล่าสุดของฟอร์มนั้น."""
    if accession:
        acc = accession.strip()
        pool = c.get_filings(form=form) if form else c.get_filings()
        for f in pool:
            if str(getattr(f, "accession_no", "")) == acc:
                return f
        raise MarketDataError("NO_DATA",
                              f"ไม่พบ accession '{acc}' ของ {ticker} (form={form}) — "
                              f"ตรวจเลขด้วย fetch_filings ก่อน",
                              recoverable=False, provider="edgar", source="EDGAR", source_tier=1)
    if not form:
        raise MarketDataError("INVALID_INPUT", "ต้องระบุ form หรือ accession อย่างน้อยหนึ่งอย่าง",
                              recoverable=False, provider="edgar")
    latest = c.get_filings(form=form).latest()
    if latest is None:
        raise MarketDataError("NO_DATA", f"ไม่พบ filing form={form}",
                              provider="edgar", source="EDGAR", source_tier=1)
    return latest


def _section_text(f, section: str) -> str:
    """ข้อความรายหัวข้อ (10-K/10-Q: 'Item 1A', 'Item 7' ...). ฟอร์มที่ไม่รองรับ → error พร้อมรายการที่มี."""
    try:
        obj = f.obj()
    except Exception as e:  # noqa: BLE001
        raise MarketDataError("NO_DATA",
                              f"อ่านโครงสร้าง filing ไม่ได้ ({type(e).__name__}) — เรียกโดยไม่ใส่ section "
                              f"เพื่อเอาข้อความทั้งฉบับแทน",
                              provider="edgar", source="EDGAR", source_tier=1) from e
    available = list(getattr(obj, "items", []) or [])
    want = section.strip()
    match = next((it for it in available if it.lower() == want.lower()), None)
    key = _tenk_item_key(str(getattr(f, "form", "") or ""), want)
    if key:  # same guard + heading-split fallback as fetch_filing_section_full
        text = str(obj[match] or "") if match is not None else ""
        if match is None or (text.strip() and _section_heading_conflicts(text, key)):
            split = _heading_split(str(f.text() or ""), key)
            if split is not None:
                return split
            if match is not None:
                raise MarketDataError("NO_DATA", f"parser ให้เนื้อ section '{section}' ที่หัวเรื่องไม่ตรง และตัดจากหัวข้อ "
                                      f"ITEM ในเนื้อเอกสารไม่ได้ — เรียกโดยไม่ใส่ section เพื่อเอาข้อความทั้งฉบับแทน",
                                      provider="edgar", source="EDGAR", source_tier=1)
        else:
            return text
    if match is None:
        raise MarketDataError("INVALID_INPUT",
                              f"filing นี้ไม่มี section '{section}'" +
                              # คั่นด้วย ' | ' ไม่ใช่ ', ' — ชื่อ section ของ 10-Q มีจุลภาคในตัวเอง
                              (f" — ที่มีให้เลือก: {' | '.join(available)}" if available
                               else " (ฟอร์มนี้ไม่แบ่ง section — เรียกโดยไม่ใส่ section)"),
                              recoverable=False, provider="edgar", source="EDGAR", source_tier=1)
    return str(obj[match] or "")


_ITEM_REQ_RE = re.compile(r"item[\s\xa0]+(\d{1,2})([a-d])?", re.I)
_ITEM_HEAD_RE = re.compile(r"^[ \t\xa0]*item[ \t\xa0]+(\d{1,2})([a-d])?[ \t\xa0]*[.:\-–—](?!\d)", re.I | re.M)
_NOTE_HEAD_RE = re.compile(r"^[ \t\xa0]*note[ \t\xa0]*\d+\b", re.I)
_LEAD_SKIP_RE = re.compile(r"^(table of contents|parts? [ivx]+( and [ivx]+)?)\W*$", re.I)
# In-sentence cross-references that happen to start a line: 'See\n\nItem 7. "Management's ..."'
_QUOTED_TITLE_RE = re.compile(r"[ \t\xa0]*[\"“‘']")
_MID_SENTENCE_RE = re.compile(r"(,|\b(see|in|and|or|under|of|to|also|within))[ \t\xa0]*$", re.I)
# Table-of-contents / cross-reference-index row: title padded out to a page column
# ("Item 1B. Unresolved ...      31" · "Item 1.   Business   4-7, 9-10, 71-73" · "...   Not applicable")
_TOC_ROW_RE = re.compile(r"[ \t\xa0]{2,}(\d{1,3}([ \t\xa0]*[,\-–][ \t\xa0]*\d{1,3})*|not applicable|none|n/a)[ \t\xa0]*$", re.I)


def _tenk_item_key(form: str, section: str) -> tuple[int, str] | None:
    """(number, letter) for a 10-K 'Item N' request; None = guard/fallback do not apply."""
    m = _ITEM_REQ_RE.fullmatch(section.strip())
    if not str(form).upper().startswith("10-K") or not m:
        return None
    return int(m.group(1)), (m.group(2) or "").lower()


def _section_heading_conflicts(text: str, key: tuple[int, str]) -> bool:
    """True when the parser's text opens with a *different* heading (e.g. 'NOTE 7' for 'Item 7').

    Permissive on purpose: text that opens with no Item heading at all (cross-reference-index
    10-Ks such as 'RISK FACTORS.') is not a conflict — only a contradicting label is.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:5]
    for line in lines:
        if _LEAD_SKIP_RE.match(line):
            continue
        head = _ITEM_HEAD_RE.match(line) or re.match(r"^item[\s\xa0]+(\d{1,2})([a-d])?\b", line, re.I)
        if head:
            return (int(head.group(1)), (head.group(2) or "").lower()) != key
        return bool(_NOTE_HEAD_RE.match(line))
    return False


def _heading_split(full_text: str, key: tuple[int, str]) -> str | None:
    """Cut one 10-K Item out of the full filing text by its 'ITEM N.' line headings.

    Each candidate heading runs to the next heading of a *later* item. Table-of-contents
    rows (padded page number) and in-sentence references (quoted title, or the previous line
    ends mid-sentence) are not headings; the longest remaining candidate is the body section.
    """
    heads = []
    for m in _ITEM_HEAD_RE.finditer(full_text):
        before = full_text[:m.start()].rstrip()
        prev_line = before[before.rfind("\n") + 1:]
        line_end = full_text.find("\n", m.end())
        line = full_text[m.start():len(full_text) if line_end < 0 else line_end]
        if (_QUOTED_TITLE_RE.match(full_text, m.end()) or _MID_SENTENCE_RE.search(prev_line)
                or _TOC_ROW_RE.search(line)):
            continue
        heads.append((m.start(), (int(m.group(1)), (m.group(2) or "").lower())))
    best = None
    for i, (pos, k) in enumerate(heads):
        if k != key:
            continue
        end = next((p for p, k2 in heads[i + 1:] if k2 > key), len(full_text))
        if best is None or end - pos > best[1] - best[0]:
            best = (pos, end)
    return full_text[best[0]:best[1]].strip() if best else None


def validate_filing_section_request(ticker: str, form: str, accession: str, section: str) -> None:
    """Validate literal identifiers before any provider call or filesystem write."""
    valid = (
        isinstance(ticker, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]{0,31}", ticker)
        and isinstance(accession, str) and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)
        and isinstance(form, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{0,39}", form)
        and form == form.strip()
        and isinstance(section, str) and bool(section.strip()) and len(section) <= 200
        and all(ch.isprintable() for ch in section)
    )
    if not valid:
        raise MarketDataError("INVALID_INPUT", "Invalid ticker, form, accession or empty/invalid section",
                              recoverable=False, provider="edgar")
    require_us(ticker, "filing-bundle")


def fetch_filing_section_full(ticker: str, form: str, accession: str, section: str) -> dict:
    """Local-artifact API: complete parser text, without the MCP pagination cap.

    This separate entry point does not change fetch_filing_text's legacy contract.
    Completeness here is relative to the parser, not proof of SEC HTML coverage.
    """
    validate_filing_section_request(ticker, form, accession, section)
    from edgar import Company, set_identity
    _set_edgar_identity(set_identity)
    try:
        # Search the exact accession independently of form, then verify both.
        f: Any = _pick_filing(Company(ticker), ticker, None, accession)
    except MarketDataError as e:
        if e.code == "NO_DATA":
            raise MarketDataError("FILING_NOT_FOUND", "Requested accession could not be located",
                                  recoverable=False, provider="edgar") from e
        raise
    except Exception as e:  # provider boundary; no raw response/credential logging
        raise MarketDataError("PROVIDER_ERROR", f"Filing lookup failed ({type(e).__name__})",
                              provider="edgar") from e
    for actual, expected, code in ((getattr(f, "accession_no", None), accession, "ACCESSION_MISMATCH"),
                                   (getattr(f, "form", None), form, "FORM_MISMATCH")):
        if actual != expected:
            raise MarketDataError(code, "Retrieved filing identity differs from request",
                                  recoverable=False, provider="edgar")
    key = _tenk_item_key(form, section)
    method = "parser"
    try:
        obj: Any = f.obj()
        available = list(getattr(obj, "items", []) or [])
        match = next((it for it in available if it.lower() == section.strip().lower()), None)
        text = obj[match] if match is not None else None
        if match is not None and not isinstance(text, str):
            raise MarketDataError("PARSER_ERROR", "Parser returned non-string section content",
                                  provider="edgar")
        # Parser missed the item, or labelled something else (e.g. 'NOTE 7') as it →
        # cut the item from the official full text by its own 'ITEM N.' heading instead.
        if key and (match is None or (text.strip() and _section_heading_conflicts(text, key))):
            split = _heading_split(str(f.text() or ""), key)
            if split is None:
                raise MarketDataError(
                    "SECTION_DISCOVERY_FAILED" if match is None else "PARSER_ERROR",
                    "Parser did not locate requested section; not a disclosure finding" if match is None
                    else "Parser section heading contradicts request and heading split found no match",
                    provider="edgar")
            text, method = split, "heading-split"
        if match is None and method == "parser":
            raise MarketDataError("SECTION_DISCOVERY_FAILED", "Parser did not locate requested section; not a disclosure finding",
                                  provider="edgar")
    except MarketDataError:
        raise
    except Exception as e:
        raise MarketDataError("PARSER_ERROR", f"Section parsing failed ({type(e).__name__})",
                              provider="edgar") from e
    if not text.strip():
        raise MarketDataError("EMPTY_SECTION", "Parser returned empty section text", provider="edgar")
    return {"ticker": ticker, "text": text, "metadata": {
        "source": "SEC EDGAR (edgartools)", "source_tier": 1, "as_of": today_iso(),
        "form": str(getattr(f, "form", "") or ""),
        "accession": getattr(f, "accession_no", None),
        "filing_date": _filing_date_str(f) or None, "url": getattr(f, "url", None),
        "section": section, "total_chars": len(text), "section_method": method,
    }}


def _exhibit_text(f, exhibit: str) -> str:
    """ข้อความของไฟล์แนบ เช่น EX-99.1 = ข่าวประชาสัมพันธ์ผลประกอบการที่แนบมากับ 8-K."""
    want = exhibit.strip().upper()
    found = []
    for a in getattr(f, "attachments", []) or []:
        dt = str(getattr(a, "document_type", "") or "")
        found.append(dt)
        if dt.upper() == want:
            return str(a.text() or "")
    raise MarketDataError("INVALID_INPUT",
                          f"filing นี้ไม่มี exhibit '{exhibit}' — ที่แนบมา: {' | '.join(found) or '(ไม่มี)'}",
                          recoverable=False, provider="edgar", source="EDGAR", source_tier=1)


def fetch_filing_text(ticker: str, form: str | None = None, accession: str | None = None,
                      section: str | None = None, exhibit: str | None = None,
                      max_chars: int = FILING_TEXT_DEFAULT_CHARS, offset: int = 0) -> dict:
    """ข้อความจริงใน filing ของ SEC EDGAR (tier 1) — 10-K/10-Q รายหัวข้อ · 8-K + exhibit · DEF 14A.

    เลือกได้ 3 ระดับ (ไล่จากแคบไปกว้าง): exhibit → section → ทั้งฉบับ

    ⚠️ ชื่อ section **ไม่เหมือนกันทุกฟอร์ม** — ใส่ผิดจะได้ INVALID_INPUT พร้อมรายการที่มีจริง:
      10-K   : 'Item 1A' (ความเสี่ยง) · 'Item 7' (MD&A) · 'Item 8' (งบ)
      10-Q   : ต้องมี Part นำหน้าเสมอ — 'Part I, Item 2' (MD&A) · 'Part II, Item 1A' (ความเสี่ยง)
      DEF 14A: ไม่แบ่ง section → เรียกโดยไม่ใส่ section

    ผลลัพธ์ถูกตัดตาม max_chars เสมอและบอก next_offset ให้อ่านต่อ — filing ใหญ่มาก
    (AAPL DEF 14A ~357k · 10-K ~261k · TSM 20-F ~1.02 ล้านตัวอักษร) การดึงทั้งก้อนรวดเดียว
    จะกิน context ของผู้เรียกจนหมด; ระบุ section/exhibit ให้แคบคือวิธีที่ถูกกว่าการไล่ offset.
    """
    require_us(ticker, "filing-text")
    from edgar import set_identity, Company
    _set_edgar_identity(set_identity)

    if section and exhibit:
        raise MarketDataError("INVALID_INPUT", "ระบุ section กับ exhibit พร้อมกันไม่ได้ — เลือกอย่างใดอย่างหนึ่ง",
                              recoverable=False, provider="edgar")
    if not isinstance(max_chars, int) or max_chars <= 0:
        max_chars = FILING_TEXT_DEFAULT_CHARS
    max_chars = min(max_chars, FILING_TEXT_MAX_CHARS)
    offset = offset if isinstance(offset, int) and offset > 0 else 0

    c = Company(ticker)
    f = _pick_filing(c, ticker, (form or "").strip() or None, accession)

    if exhibit:
        text, scope = _exhibit_text(f, exhibit), f"exhibit {exhibit}"
    elif section:
        text, scope = _section_text(f, section), f"section {section}"
    else:
        text, scope = str(f.text() or ""), "ทั้งฉบับ"

    total = len(text)
    chunk = text[offset:offset + max_chars]
    end_pos = offset + len(chunk)
    return {
        "ticker": ticker,
        "text": chunk,
        "metadata": {
            "source": "SEC EDGAR (edgartools)", "source_tier": 1, "as_of": today_iso(),
            "form": str(getattr(f, "form", "") or "") or None,
            "filing_date": _filing_date_str(f) or None,
            "accession": getattr(f, "accession_no", None),
            "url": getattr(f, "url", None),
            "scope": scope,
            "total_chars": total,
            "returned_chars": len(chunk),
            "offset": offset,
            "has_more": end_pos < total,
            "next_offset": end_pos if end_pos < total else None,
        },
    }


# ---------------------------------------------------------------- macro (FRED)
def fetch_macro(series_id: str, start: str | None = None, end: str | None = None,
                limit: int | None = None) -> dict:
    """time series มหภาคจาก FRED (fredapi). value เป็น string (preserve).

    limit = จำนวนแถว 'ล่าสุด' ที่คืน (None = เต็ม history). ใช้กัน payload บวม —
    series รายวันเต็ม history อาจหลายหมื่นแถว (~1MB) ล้น context ผู้เรียก.
    """
    if not series_id or not series_id.strip():
        raise MarketDataError("INVALID_INPUT", "ต้องระบุ series_id (เช่น DGS10, CPIAUCSL, FEDFUNDS)",
                              recoverable=False)
    key = keychain("fred-api")
    if not key:
        raise MarketDataError("MISSING_SECRET",
                              "ไม่มี fred-api ใน Keychain — เซฟด้วย: "
                              "security add-generic-password -U -a friday -s fred-api -w '<KEY>'",
                              recoverable=False, provider="fred", source="FRED", source_tier=1)
    from fredapi import Fred
    fred = Fred(api_key=key)
    # fredapi โยน ValueError เมื่อ series id ผิด/ไม่มีข้อมูลจริง (ไม่ควร retry — สิ้นเปลือง),
    # แต่โยน ParseError/network error เมื่อ FRED ตอบกลับไม่ครบเป็นครั้งคราว (transient — retry ได้).
    # retry เฉพาะ transient สูงสุด 3 ครั้ง backoff สั้น ๆ กัน NO_DATA หลอกจากอาการสะดุดชั่วคราว.
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            s = fred.get_series(series_id)
            break
        except ValueError as e:  # series id ผิด/ไม่มีข้อมูล — final ทันที
            raise MarketDataError("NO_DATA", f"FRED ไม่คืน series '{series_id}' ({type(e).__name__}) — ตรวจ series id",
                                  provider="fred", source="FRED", source_tier=1) from e
        except Exception as e:  # noqa: BLE001 — ParseError/HTTPError/URLError = transient
            last_exc = e
            if attempt < 2:
                time.sleep(0.6 * (attempt + 1))
    else:
        raise MarketDataError("NO_DATA",
                              f"FRED ไม่คืน series '{series_id}' ({type(last_exc).__name__}) หลัง retry 3 ครั้ง "
                              "— อาจเป็นอาการชั่วคราวฝั่ง FRED ลองใหม่อีกครั้ง",
                              provider="fred", source="FRED", source_tier=1) from last_exc
    if s is None or not len(s):
        raise MarketDataError("NO_DATA", f"FRED ไม่คืน series '{series_id}' (ตรวจ series id)",
                              provider="fred", source="FRED", source_tier=1)
    s = s.dropna()
    full_rows = len(s)
    if start:
        s = s[s.index >= start]
    if end:
        s = s[s.index <= end]
    if not len(s):
        # เช็ค NO_DATA ตัวบนอยู่ "ก่อน" กรองช่วง จึงไม่จับเคสนี้ — ถ้าไม่เช็คซ้ำผู้เรียกจะได้ data: []
        # เปล่า ๆ โดยไม่รู้ว่าเพราะ series ไม่มีข้อมูล หรือเพราะช่วงวันที่ที่ขอไม่มี (ขัดหลัก NO MAGIC)
        raise MarketDataError(
            "NO_DATA",
            f"series '{series_id}' มีข้อมูล {full_rows} แถว แต่ไม่มีแถวใดอยู่ในช่วงที่ขอ "
            f"(start={start or 'ไม่ระบุ'}, end={end or 'ไม่ระบุ'}) — ตรวจช่วงวันที่",
            recoverable=False, provider="fred", source="FRED", source_tier=1)
    total = len(s)
    truncated = False
    if limit is not None and limit > 0 and total > limit:
        s = s.iloc[-limit:]   # เก็บแถวล่าสุด
        truncated = True
    data = [{"date": str(i.date()), "value": str(v)} for i, v in s.items()]
    meta = {"source": "FRED", "source_tier": 1, "series_id": series_id, "as_of": today_iso()}
    if truncated:
        meta["truncated"] = True
        meta["returned_rows"] = len(data)
        meta["total_rows"] = total
        meta["note"] = (f"คืน {len(data)} แถวล่าสุดจากทั้งหมด {total} — "
                        "ระบุ start/end เพื่อช่วงที่ต้องการ หรือเพิ่ม limit")
    return {
        "series_id": series_id,
        "data": data,
        "metadata": meta,
    }


# ---------------------------------------------------------------- estimates (FMP — ชั้น 3 ธง)
def fetch_estimates(ticker: str, limit: int = 5) -> dict:
    """consensus/analyst estimates — ชั้น 3 (ธงไม่ official). best-effort: ไม่มี key/ไม่คืน → note ไม่ใช่ error."""
    require_us(ticker, "estimates")
    limit = limit if isinstance(limit, int) and limit > 0 else 5
    note = "consensus/analyst estimates ไม่มีแหล่งทางการฟรี — ชั้น 3 (ธง) ใช้ประกอบเท่านั้น"

    key = keychain("fmp-api")
    meta = {"source": "FMP stable", "source_tier": 3, "as_of": today_iso(),
            "endpoint_family": "stable", "fallback_used": False}
    if not key:
        return {"ticker": ticker, "data": [],
                "note": note + " | ไม่มี fmp-api ใน Keychain → ดึงมือจากเว็บ (IR/analyst) แล้วติดธง secondary",
                "metadata": {**meta, "source": "(none)"}}

    # period เป็นพารามิเตอร์ **บังคับ** ของ stable/analyst-estimates — เดิมไม่ได้ส่งไป FMP จึงตอบ
    # HTTP 400 "Invalid or missing query parameter - period" กับ **ทุก ticker** แม้แต่ตัวที่อยู่ในชุดฟรี
    # แล้วโค้ดเดิมแปลงเป็น data: [] เงียบ ๆ (วัดจริง 2026-09-03; quarter = พรีเมียม 402 → ใช้ annual)
    url = (f"https://financialmodelingprep.com/stable/analyst-estimates?symbol={ticker}"
           f"&period=annual&limit={limit}&apikey={key}")
    j, code, err = _fmp_get(url, "stable/analyst-estimates")
    if code:
        return {"ticker": ticker, "data": [],
                "note": note + f" | {err} → ใช้เว็บแล้วติดธง", "metadata": {**meta, "error_code": code}}
    if not (isinstance(j, list) and j):
        return {"ticker": ticker, "data": [],
                "note": note + " | FMP ตอบ HTTP 200 แต่ไม่มี estimates ของ ticker นี้ "
                               "→ ใช้เว็บแล้วติดธง", "metadata": {**meta, "error_code": "NO_DATA"}}
    return {"ticker": ticker, "data": j[:limit], "note": note, "metadata": meta}


# ---------------------------------------------------------------- universe (Nasdaq screener — ชั้น 3 ธง)
import re as _re  # noqa: E402 — เฉพาะ universe (regex ตัด non-common); แยกชัดจาก logic เดิม

# Nasdaq public screener (download=true) — แหล่ง "screener จริง" ฟรี: คืน marketCap+sector+country+
# industry ต่อ ticker. tier 3: ไม่ official, เปราะ (Nasdaq เปลี่ยน schema/บล็อกได้). ไม่ต้องใช้ key.
_NASDAQ_URL = "https://api.nasdaq.com/api/screener/stocks"
_NASDAQ_HDR = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/",
}
_VALID_EXCHANGES = ("NYSE", "NASDAQ", "AMEX")
# ตัด non-common (warrant/unit/right/preferred/note) — ไม่ใช่หุ้นสามัญที่ screener ต้องการ
_NONCOMMON_RE = _re.compile(r"\b(warrant|unit|right|preferred|depositary|notes?|debenture)s?\b", _re.I)


def _capnum(s) -> Decimal | None:
    """marketCap string ('$36,882,787,567.00') → Decimal; เสียรูป/ว่าง → None."""
    try:
        return Decimal(str(s).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def fetch_universe(exchanges: list[str] | None = None, market_cap_min=0, market_cap_max=Decimal("1e15"),
                   sector_keep: list[str] | None = None, sector_exclude: list[str] | None = None,
                   us_only: bool = True) -> dict:
    """รายชื่อหุ้น US (NYSE/NASDAQ/AMEX) ตาม market-cap band + sector จาก Nasdaq screener (tier 3, ธง).

    sector taxonomy = Nasdaq ('Finance','Real Estate','Health Care','Technology' — ไม่ใช่ GICS).
    ไม่บังคับกำไรบวก (ต่างจาก S&P) — ผู้เรียกกรอง NI>0 ต่อเอง. คืน dict (return-only, ไม่ print).
    """
    import requests

    exch = [e.strip().upper() for e in (exchanges or list(_VALID_EXCHANGES)) if str(e).strip()]
    bad = [e for e in exch if e not in _VALID_EXCHANGES]
    if bad:
        raise MarketDataError("INVALID_INPUT",
                              f"exchange ไม่รองรับ: {bad} (รองรับ {list(_VALID_EXCHANGES)})",
                              recoverable=False, source="nasdaq-screener", source_tier=3)
    lo = _capnum(market_cap_min)
    hi = _capnum(market_cap_max)
    if lo is None or hi is None or lo < 0 or hi < 0:
        raise MarketDataError("INVALID_INPUT",
                              f"market_cap_min/max ต้องเป็นตัวเลข >= 0 (ได้ min={market_cap_min} max={market_cap_max})",
                              recoverable=False, source="nasdaq-screener", source_tier=3)
    if lo > hi:
        raise MarketDataError("INVALID_INPUT",
                              f"market_cap_min ({lo}) ต้อง <= market_cap_max ({hi})",
                              recoverable=False, source="nasdaq-screener", source_tier=3)
    keep = [s.strip() for s in (sector_keep or []) if str(s).strip()]
    drop = [s.strip() for s in (sector_exclude or []) if str(s).strip()]

    seen: set[str] = set()
    rows: list[dict] = []
    warnings: list[str] = []
    for ex in exch:
        try:
            r = requests.get(_NASDAQ_URL, params={"download": "true", "exchange": ex},
                             headers=_NASDAQ_HDR, timeout=60)
        except requests.RequestException as e:
            warnings.append(f"{ex}: เรียกไม่ได้ ({type(e).__name__})")
            continue
        if r.status_code != 200:
            warnings.append(f"{ex}: HTTP {r.status_code}")
            continue
        try:
            data = r.json().get("data", {}) or {}
        except ValueError:
            warnings.append(f"{ex}: ตอบกลับไม่ใช่ JSON")
            continue
        raw = data.get("rows") or data.get("table", {}).get("rows") or []
        for x in raw:
            sym = (x.get("symbol") or "").strip().upper()
            # Nasdaq เขียนคลาสรองด้วยสแลช ('BRK/B') และหุ้นบุริมสิทธิด้วย '^' ('ABR^D') — วัดจริง
            # NYSE 2708 รายการ: '/' 12 ตัว · '^' 366 ตัว · จุด 0 ตัว. บุริมสิทธิไม่ใช่หุ้นสามัญ → ตัด;
            # คลาสรองเป็นหุ้นสามัญแท้ → แปลงเป็นขีดกลางที่ EDGAR/yfinance รับได้ ไม่ใช่ปล่อยรูปที่ใช้ต่อไม่ได้
            if not sym or "^" in sym:
                continue
            sym = us_class_ticker(sym)
            if sym in seen:
                continue
            if _NONCOMMON_RE.search(x.get("name", "") or ""):
                continue
            cap = _capnum(x.get("marketCap"))
            if cap is None or cap <= 0 or cap < lo or cap > hi:
                continue
            sec = (x.get("sector") or "").strip() or "?"
            if keep and sec not in keep:
                continue
            if drop and sec in drop:
                continue
            country = (x.get("country") or "").strip()
            if us_only and country != "United States":
                continue
            seen.add(sym)
            rows.append({"symbol": sym, "market_cap": _plain_num(cap), "sector": sec,
                         "country": country or None, "industry": (x.get("industry") or "").strip() or None})

    if not rows and len(warnings) == len(exch):
        raise MarketDataError("NETWORK_ERROR",
                              f"ดึง Nasdaq screener ไม่สำเร็จทุก exchange: {warnings}",
                              provider="nasdaq", source="nasdaq-screener", source_tier=3)

    return {
        "universe": rows,
        "metadata": {
            "source": "nasdaq-screener", "source_tier": 3, "as_of": today_iso(), "count": len(rows),
            "filters": {"exchanges": exch, "market_cap_min": _plain_num(lo),
                        "market_cap_max": _plain_num(hi), "sector_keep": keep or None,
                        "sector_exclude": drop or None, "us_only": us_only},
            "exchange_warnings": warnings or None,
            "note": "Nasdaq taxonomy ('Finance'/'Real Estate' ≠ GICS); ไม่บังคับกำไรบวก → กรอง NI>0 เอง",
        },
    }
