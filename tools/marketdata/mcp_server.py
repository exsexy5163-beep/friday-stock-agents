#!/usr/bin/env python3
"""friday-marketdata-mcp — MCP server (thin gateway) ห่อ core.py ของ Market-Data Fetch Toolkit.

รัน (stdio) ด้วย interpreter ของ toolkit venv เท่านั้น:
    __FRIDAY_ROOT__/tools/marketdata/.venv/bin/python \
        __FRIDAY_ROOT__/tools/marketdata/mcp_server.py

expose 11 tools: health_check, get_price_history, get_financials, get_ratios,
get_insider_transactions, get_ownership, get_macro_series, get_estimates, get_universe,
get_filings, get_filing_text.

🔴 stdout hygiene: MCP stdio ใช้ stdout เป็นช่อง JSON-RPC — ทุก provider call ถูกครอบด้วย
redirect_stdout→stderr กัน library print หลงเข้า stdout (จะพังทั้ง connection). core.py ก็ไม่ print เลย.

Security: API key อ่านจาก macOS Keychain เท่านั้น (ไม่ hardcode/print/log); error ถูก sanitize
(redact apikey); traceback แสดงเฉพาะเมื่อ env MARKETDATA_MCP_DEBUG=1.
"""
from __future__ import annotations

import contextlib
import importlib
import importlib.metadata as _md
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

import core
from core import MarketDataError

HERE = os.path.dirname(os.path.abspath(__file__))
DEBUG = os.environ.get("MARKETDATA_MCP_DEBUG") == "1"

mcp = FastMCP("friday-marketdata-mcp")

# tool annotations (hint สำหรับ client — ไม่ใช่ security boundary). ทุก tool เป็น read-only:
# อ่านข้อมูลอย่างเดียว ไม่แก้/ลบอะไร, เรียกซ้ำด้วย args เดิมได้ผลเดิม (idempotent).
_EXT = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True,
        "openWorldHint": True}    # ดึงข้อมูลจากภายนอก (SEC/FRED/FMP/yfinance)
_LOCAL = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True,
          "openWorldHint": False}  # ตรวจสภาพ local เท่านั้น ไม่ออกเน็ต


# ---------------------------------------------------------------- helpers
def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _redact(text: str) -> str:
    """ลบ secret ที่อาจหลุดในข้อความ error/traceback (apikey ใน URL ฯลฯ)."""
    text = re.sub(r"(apikey=)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE)
    text = re.sub(r"(api[_-]?key[\"'=:\s]+)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE)
    return text


def _err(code: str, message: str, *, recoverable: bool = True, provider: Optional[str] = None,
         source: Optional[str] = None, source_tier: Optional[int] = None,
         include_tb: bool = False) -> dict:
    error = {"code": code, "message": _redact(message), "recoverable": recoverable, "provider": provider}
    if DEBUG and include_tb:
        error["traceback"] = _redact(traceback.format_exc())
    return {"ok": False, "error": error,
            "metadata": {"as_of": core.today_iso(), "source": source, "source_tier": source_tier}}


def _run(fn, *, source: str, source_tier: int, provider: Optional[str] = None, **kwargs) -> dict:
    """เรียก core.fetch_* อย่างปลอดภัย: redirect stdout→stderr (กัน protocol พัง) + แปลง error เป็น structured."""
    try:
        with contextlib.redirect_stdout(sys.stderr):
            return fn(**kwargs)
    except MarketDataError as e:
        return _err(e.code, e.message, recoverable=e.recoverable, provider=e.provider or provider,
                    source=e.source or source, source_tier=e.source_tier or source_tier)
    except Exception as e:  # noqa: BLE001 — ไม่ปล่อย traceback ดิบออก response
        return _err("INTERNAL_ERROR", f"{type(e).__name__}: {e}", recoverable=False,
                    provider=provider, source=source, source_tier=source_tier, include_tb=True)


# ---------------------------------------------------------------- 1) health_check
@mcp.tool(annotations={"title": "Health Check (local only)", **_LOCAL})
def health_check() -> dict[str, Any]:
    """ตรวจสถานะระบบโดยไม่เรียก API ภายนอก — interpreter, CLI, dependency, EDGAR identity,
    และการมีอยู่ของ secret ใน Keychain (เป็น bool เท่านั้น ไม่เปิดเผยค่า)."""
    deps = {}
    for pkg, mod in [("yfinance", "yfinance"), ("fredapi", "fredapi"), ("requests", "requests"),
                     ("edgartools", "edgar"), ("alpha_vantage", "alpha_vantage")]:
        try:
            importlib.import_module(mod)
            try:
                ver = _md.version(pkg)
            except Exception:  # noqa: BLE001
                ver = getattr(sys.modules.get(mod), "__version__", "?")
            deps[pkg] = {"ok": True, "version": ver}
        except Exception as e:  # noqa: BLE001
            deps[pkg] = {"ok": False, "error": type(e).__name__}

    cli_path = os.path.join(HERE, "marketdata")
    expected_py = os.path.realpath(os.path.join(HERE, ".venv", "bin", "python"))
    python_ok = os.path.realpath(sys.executable) == expected_py
    try:
        importlib.import_module("mcp.server.fastmcp")
        mcp_ok = True
    except Exception:  # noqa: BLE001
        mcp_ok = False

    keychain_present = {svc: core.keychain_present(svc)
                        for svc in ("fmp-api", "alphavantage-api", "fred-api")}
    ok = python_ok and mcp_ok and os.path.isfile(cli_path) and all(d["ok"] for d in deps.values())
    return {
        "ok": ok,
        "python": sys.executable,
        "cli_path": cli_path,
        "dependencies": deps,
        "config": {
            "python_is_toolkit_venv": python_ok,
            "mcp_server_importable": mcp_ok,
            "edgar_identity_present": bool(core.EDGAR_IDENTITY),
            "keychain_present": keychain_present,  # bool only — secrets ไม่ถูกเปิดเผย
            "debug_mode": DEBUG,
            "secrets_redacted": True,
        },
        "checked_at": _now_iso(),
    }


# ---------------------------------------------------------------- 2) get_price_history
@mcp.tool(annotations={"title": "Get Price History (US + TH)", **_EXT})
def get_price_history(ticker: str, start: Optional[str] = None, end: Optional[str] = None,
                      period: Optional[str] = None, interval: Optional[str] = "1d",
                      market: Literal["US", "TH", "AUTO"] = "AUTO") -> dict[str, Any]:
    """ราคาย้อนหลัง OHLCV (US + ไทย .BK) จาก yfinance (tier 3). market: US|TH|AUTO."""
    return _run(core.fetch_price, source="yfinance", source_tier=3, provider="yfinance",
                ticker=ticker, start=start, end=end, period=period, interval=interval, market=market)


# ---------------------------------------------------------------- 3) get_financials
@mcp.tool(annotations={"title": "Get Financial Statements (SEC EDGAR)", **_EXT})
def get_financials(ticker: str, period: Literal["annual", "quarterly"] = "annual",
                   statements: Optional[list[Literal["income", "balance", "cashflow"]]] = None,
                   years: Annotated[int, Field(ge=1, le=10)] = 5) -> dict[str, Any]:
    """งบ US ดิบจาก SEC EDGAR (tier 1). period: annual|quarterly; statements: income|balance|cashflow.
    v1 EDGAR-only (ไม่มี FMP fallback; fallback_used=false เสมอ)."""
    return _run(core.fetch_financials, source="SEC EDGAR (edgartools)", source_tier=1, provider="edgar",
                ticker=ticker, period=period, statements=statements, years=years)


# ---------------------------------------------------------------- 4) get_ratios
@mcp.tool(annotations={"title": "Get Financial Ratios (FMP)", **_EXT})
def get_ratios(ticker: str, limit: Annotated[int, Field(ge=1, le=50)] = 5) -> dict[str, Any]:
    """ratio สำเร็จรูป (รายปี/FY) จาก FMP stable/ (tier 2 aggregator — ควร verify กับงบ EDGAR).
    หมายเหตุ: FMP free plan คืนเฉพาะรายปี; quarterly = premium (HTTP 402) จึงไม่ expose period."""
    return _run(core.fetch_ratios, source="FMP stable", source_tier=2, provider="fmp",
                ticker=ticker, limit=limit)


# ---------------------------------------------------------------- 5) get_insider_transactions
@mcp.tool(annotations={"title": "Get Insider Transactions (Form 4)", **_EXT})
def get_insider_transactions(ticker: str, limit: Annotated[int, Field(ge=1, le=100)] = 20,
                             start: Optional[str] = None, end: Optional[str] = None) -> dict[str, Any]:
    """insider transactions (Form 4) จาก SEC EDGAR (tier 1). value คำนวณด้วย Decimal เมื่อ filing ไม่ระบุ."""
    return _run(core.fetch_insider, source="EDGAR", source_tier=1, provider="edgar",
                ticker=ticker, limit=limit, start=start, end=end)


# ---------------------------------------------------------------- 6) get_ownership
@mcp.tool(annotations={"title": "Get Major Ownership (SC 13D/G)", **_EXT})
def get_ownership(ticker: str, form_types: Optional[list[Literal["13D", "13G"]]] = None,
                  limit: Annotated[int, Field(ge=1, le=100)] = 20) -> dict[str, Any]:
    """ผู้ถือใหญ่/activist (SC 13D/G) จาก SEC EDGAR (tier 1).
    หมายเหตุ: ชื่อผู้ถือดึงได้ดี แต่ %/หุ้นมักเป็น null กับ filing ฟอร์แมตเก่า → ดู url ของ filing เพื่อค่าจริง."""
    return _run(core.fetch_ownership, source="EDGAR", source_tier=1, provider="edgar",
                ticker=ticker, form_types=form_types, limit=limit)


# ---------------------------------------------------------------- 7) get_macro_series
@mcp.tool(annotations={"title": "Get Macro Series (FRED)", **_EXT})
def get_macro_series(series_id: str, start: Optional[str] = None, end: Optional[str] = None,
                     limit: Annotated[int, Field(ge=0)] = 250) -> dict[str, Any]:
    """time series มหภาคจาก FRED (tier 1) เช่น DGS10, CPIAUCSL, FEDFUNDS, GDP.

    limit = จำนวนแถวล่าสุดที่คืน (default 250 ≈ ~1 ปี daily) กัน payload บวมล้น context;
    ใส่ start/end เพื่อเจาะช่วง หรือ limit=0 เพื่อดึงเต็ม history.
    """
    return _run(core.fetch_macro, source="FRED", source_tier=1, provider="fred",
                series_id=series_id, start=start, end=end,
                limit=(None if limit == 0 else limit))


# ---------------------------------------------------------------- 8) get_estimates
@mcp.tool(annotations={"title": "Get Analyst Estimates (FMP, flagged tier 3)", **_EXT})
def get_estimates(ticker: str, limit: Annotated[int, Field(ge=1, le=50)] = 5) -> dict[str, Any]:
    """analyst estimates จาก FMP stable/ (tier 3, ธงไม่ official). best-effort: ไม่มีข้อมูล → note ไม่ใช่ error."""
    return _run(core.fetch_estimates, source="FMP stable", source_tier=3, provider="fmp",
                ticker=ticker, limit=limit)


# ---------------------------------------------------------------- 9) get_universe
@mcp.tool(annotations={"title": "Get Stock Universe / Screener (Nasdaq, flagged tier 3)", **_EXT})
def get_universe(exchanges: Optional[list[Literal["NYSE", "NASDAQ", "AMEX"]]] = None,
                 market_cap_min: Annotated[float, Field(ge=0)] = 0,
                 market_cap_max: Annotated[float, Field(ge=0)] = 1e15,
                 sector_keep: Optional[list[str]] = None,
                 sector_exclude: Optional[list[str]] = None,
                 us_only: bool = True) -> dict[str, Any]:
    """รายชื่อหุ้น US (NYSE/NASDAQ/AMEX) ตาม market-cap band + sector จาก Nasdaq screener
    (tier 3, ธงไม่ official — schema เปราะ). sector taxonomy = Nasdaq ('Finance','Real Estate',
    'Health Care','Technology' — ไม่ใช่ GICS). ไม่บังคับกำไรบวก: ผู้เรียกกรอง NI>0 ต่อเอง."""
    return _run(core.fetch_universe, source="nasdaq-screener", source_tier=3, provider="nasdaq",
                exchanges=exchanges, market_cap_min=market_cap_min, market_cap_max=market_cap_max,
                sector_keep=sector_keep, sector_exclude=sector_exclude, us_only=us_only)

# ---------------------------------------------------------------- 10) get_filings
@mcp.tool(annotations={"title": "List SEC Filings (8-K / DEF 14A / 10-K / 10-Q ...)", **_EXT})
def get_filings(ticker: str, form: Optional[str] = None,
                limit: Annotated[int, Field(ge=1, le=100)] = 20,
                start: Optional[str] = None, end: Optional[str] = None,
                detail: bool = False) -> dict[str, Any]:
    """ลิสต์ filing ของบริษัท US จาก SEC EDGAR (tier 1) — metadata เท่านั้น ไม่ดึงเนื้อ (payload เบา).

    form: '8-K' | 'DEF 14A' | '10-K' | '10-Q' | '20-F' | '6-K' ฯลฯ (ไม่ใส่ = ทุกฟอร์ม).
    detail=False (default): form/filed/accession/url เท่านั้น — เร็วมาก (index ก้อนเดียว)
    detail=True: + item code ของ 8-K ('Item 2.02' = ประกาศผลประกอบการ) + รายการ exhibit

    ⚠️ ต้นทุน 2 ก้อน (วัดจริง): (1) โหลดสารบัญบริษัท ~1–13 วิ เกิดครั้งเดียวต่อบริษัท
    ไม่ว่า detail เปิดหรือปิด · (2) detail=True โหลด filing ทีละฉบับ ~1.2–2.5 วิ/ฉบับ
    (IBM 8-K 20 ฉบับ = +23.1 วิ; limit=100 ≈ 2–4 นาที เสี่ยง timeout).
    ท่าที่ถูก: detail=False ดูก่อนว่ามีฉบับไหน → เปิด detail=True กับ limit น้อย ๆ เมื่อจำเป็น;
    ส่วนชื่อ exhibit ไม่ต้องเปิดหาล่วงหน้า — get_filing_text ใส่ผิดจะลิสต์ของที่แนบมาให้ใน error เอง.
    """
    return _run(core.fetch_filings, source="EDGAR", source_tier=1, provider="edgar",
                ticker=ticker, form=form, limit=limit, start=start, end=end, detail=detail)


# ---------------------------------------------------------------- 11) get_filing_text
@mcp.tool(annotations={"title": "Get SEC Filing Text (paginated)", **_EXT})
def get_filing_text(ticker: str, form: Optional[str] = None, accession: Optional[str] = None,
                    section: Optional[str] = None, exhibit: Optional[str] = None,
                    max_chars: Annotated[int, Field(ge=100, le=100_000)] = 20_000,
                    offset: Annotated[int, Field(ge=0)] = 0) -> dict[str, Any]:
    """ข้อความจริงใน filing ของ SEC EDGAR (tier 1) — 10-K/10-Q รายหัวข้อ · 8-K + exhibit · DEF 14A.

    ขอบเขตเลือกได้ 3 ระดับ (แคบ→กว้าง): exhibit ('EX-99.1' = ข่าว earnings ที่แนบกับ 8-K) →
    section → ทั้งฉบับ (ไม่ใส่ทั้งคู่).
    ไม่ใส่ accession = ฉบับล่าสุดของ form นั้น; ใส่ = เจาะฉบับ (เลขจาก get_filings).

    ⚠️ ชื่อ section **ต่างกันตามฟอร์ม** — ใส่ผิดได้ INVALID_INPUT พร้อมรายการที่มีจริง:
      10-K   : 'Item 1A' (ความเสี่ยง) · 'Item 7' (MD&A) · 'Item 8' (งบ)
      10-Q   : ต้องมี Part นำหน้า — 'Part I, Item 2' (MD&A) · 'Part II, Item 1A' (ความเสี่ยง)
      DEF 14A: ไม่แบ่ง section → เรียกโดยไม่ใส่ section

    ⚠️ filing ใหญ่มาก (AAPL DEF 14A ~357k · 10-K ~261k · TSM 20-F ~1.02 ล้านตัวอักษร) —
    ผลลัพธ์ถูกตัดที่ max_chars เสมอ + คืน has_more/next_offset ให้อ่านต่อเป็นหน้า.
    ระบุ section/exhibit ให้แคบ ประหยัด context กว่าการไล่ offset ทั้งฉบับมาก.
    """
    return _run(core.fetch_filing_text, source="SEC EDGAR (edgartools)", source_tier=1, provider="edgar",
                ticker=ticker, form=form, accession=accession, section=section, exhibit=exhibit,
                max_chars=max_chars, offset=offset)


if __name__ == "__main__":
    mcp.run()
