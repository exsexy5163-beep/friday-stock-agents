#!/usr/bin/env python3
"""MCP smoke test — ยืนยันว่า mcp_server import ได้ + tools คืน structured JSON ผ่าน core.

รันด้วย venv 3.12 ของชุดนี้เท่านั้น:
    tools/marketdata/.venv/bin/python tools/marketdata/mcp_smoke_test.py

ออกแบบให้ไม่ crash ทั้งชุดเมื่อแหล่งเดียวพัง และ **แยกประเภทความล้มเหลว**:
    code (โค้ดเรา) · environment (interpreter/import) · provider (เครือข่าย/แหล่ง) · missing-secret (ไม่มี key)
"""
import json
import sys

# --- environment check: import server (รวม FastMCP + ลงทะเบียน tools) -------------
try:
    import mcp_server as srv
except Exception as e:  # noqa: BLE001
    print(f"[FAIL/environment] import mcp_server: {type(e).__name__}: {e}")
    sys.exit(1)
print("[PASS] import mcp_server (FastMCP + tools registered)")


def classify(result: dict) -> tuple[str, str]:
    """แปลง result → (verdict, note). success = PASS; error dict → แยกประเภท."""
    if not isinstance(result, dict):
        return "FAIL/code", f"unexpected type {type(result).__name__}"
    if result.get("ok") is False:
        err = result.get("error", {})
        code = err.get("code", "?")
        bucket = {
            "MISSING_SECRET": "SKIP/missing-secret",
            "NETWORK_ERROR": "FAIL/provider",
            "RATE_LIMITED": "SKIP/provider",
            "NO_DATA": "FAIL/provider",
            "PROVIDER_ERROR": "FAIL/provider",
            "UNSUPPORTED_MARKET": "FAIL/code",
            "INVALID_INPUT": "FAIL/code",
            "INTERNAL_ERROR": "FAIL/code",
        }.get(code, "FAIL/code")
        return bucket, f"{code}: {err.get('message', '')[:80]}"
    return "PASS", ""


def show(name: str, result: dict, extra: str = "") -> None:
    verdict, note = classify(result)
    print(f"[{verdict}] {name} {extra}".rstrip() + (f" — {note}" if note else ""))


# --- 1) health_check -------------------------------------------------------------
hc = srv.health_check()
hc_ok = "PASS" if hc.get("ok") else "WARN"
print(f"[{hc_ok}] health_check ok={hc.get('ok')} python_venv={hc['config']['python_is_toolkit_venv']} "
      f"edgar_identity={hc['config']['edgar_identity_present']} "
      f"keys={ {k: v for k, v in hc['config']['keychain_present'].items()} }")
missing = [k for k, v in hc["dependencies"].items() if not v["ok"]]
if missing:
    print(f"   [environment] missing deps: {missing}")

# --- 2) macro (FRED) DGS10 -------------------------------------------------------
r = srv.get_macro_series("DGS10")
show("get_macro_series DGS10", r,
     extra=(f"n={len(r.get('data', []))} latest={r['data'][-1] if r.get('data') else '-'}"
            if isinstance(r, dict) and r.get("data") is not None and r.get("ok") is not False else ""))

# --- 3) price AAPL (US) ----------------------------------------------------------
r = srv.get_price_history("AAPL", period="5d")
show("get_price_history AAPL", r,
     extra=(f"used={r.get('ticker_used')} n={len(r.get('data', []))}" if r.get("ok") is not False else ""))

# --- 4) price PTT market=TH → PTT.BK --------------------------------------------
r = srv.get_price_history("PTT", period="5d", market="TH")
ok_bk = r.get("ticker_used") == "PTT.BK"
show("get_price_history PTT (market=TH)", r,
     extra=(f"used={r.get('ticker_used')} {'OK .BK' if ok_bk else 'WARN no .BK'}"
            if r.get("ok") is not False else ""))

# --- 5) ratios AAPL (ต้องมี FMP key) --------------------------------------------
r = srv.get_ratios("AAPL", limit=1)
show("get_ratios AAPL", r,
     extra=(f"n={len(r.get('data', []))}" if r.get("ok") is not False else ""))

# --- 6) financials AAPL (EDGAR) --------------------------------------------------
r = srv.get_financials("AAPL", period="annual", statements=["income"], years=3)
show("get_financials AAPL", r,
     extra=(f"income_rows={len(r.get('statements', {}).get('income', []))} "
            f"accession={r.get('metadata', {}).get('accession')}" if r.get("ok") is not False else ""))

# --- 7) ownership AAPL (13D/G) ---------------------------------------------------
r = srv.get_ownership("AAPL", limit=3)
show("get_ownership AAPL", r,
     extra=(f"n={len(r.get('data', []))} first_owner="
            f"{(r['data'][0].get('owner') if r.get('data') else '-')}" if r.get("ok") is not False else ""))

# --- 8) estimates AAPL (best-effort) --------------------------------------------
r = srv.get_estimates("AAPL", limit=2)
show("get_estimates AAPL", r,
     extra=(f"n={len(r.get('data', []))}" if r.get("ok") is not False else ""))

# --- 9) universe (Nasdaq screener) band 300M–1B, exclude Finance+Real Estate ----
r = srv.get_universe(market_cap_min=300e6, market_cap_max=1e9,
                     sector_exclude=["Finance", "Real Estate"])
if r.get("ok") is False:
    show("get_universe (300M–1B, excl Fin+RE)", r)  # provider/network fail → SKIP/FAIL ตาม code
else:
    meta = r.get("metadata", {})
    n = len(r.get("universe", []))
    ok = n > 0 and meta.get("count") == n and meta.get("source_tier") == 3
    print(f"[{'PASS' if ok else 'FAIL/code'}] get_universe (300M–1B, excl Fin+RE) "
          f"n={n} count={meta.get('count')} tier={meta.get('source_tier')}")

# --- 10) negative path: Thai ticker on US-only tool → UNSUPPORTED_MARKET ----------
r = srv.get_financials("PTT.BK")
expect_unsupported = r.get("ok") is False and r.get("error", {}).get("code") == "UNSUPPORTED_MARKET"
print(f"[{'PASS' if expect_unsupported else 'FAIL/code'}] guard: financials PTT.BK → "
      f"{r.get('error', {}).get('code') if r.get('ok') is False else 'NO ERROR (unexpected)'}")

# --- 11) filings 8-K (item code + exhibit) ---------------------------------------
r = srv.get_filings("AAPL", form="8-K", limit=2, detail=True)
show("get_filings AAPL 8-K", r,
     extra=(f"n={len(r.get('data', []))} items={(r['data'][0].get('items') if r.get('data') else '-')}"
            if r.get("ok") is not False else ""))

# --- 12) filing_text 10-K section Item 1A (ตัด + แบ่งหน้า) ------------------------
r = srv.get_filing_text("AAPL", form="10-K", section="Item 1A", max_chars=500)
m = r.get("metadata", {})
show("get_filing_text AAPL 10-K Item 1A", r,
     extra=(f"chars={m.get('returned_chars')}/{m.get('total_chars')} has_more={m.get('has_more')}"
            if r.get("ok") is not False else ""))

# --- 13) filing_text 8-K exhibit EX-99.1 (ข่าว earnings) --------------------------
r = srv.get_filing_text("AAPL", form="8-K", exhibit="EX-99.1", max_chars=500)
show("get_filing_text AAPL 8-K EX-99.1", r,
     extra=(f"chars={r.get('metadata', {}).get('total_chars')}" if r.get("ok") is not False else ""))

# --- 14) filing_text DEF 14A ทั้งฉบับ --------------------------------------------
r = srv.get_filing_text("AAPL", form="DEF 14A", max_chars=500)
show("get_filing_text AAPL DEF 14A", r,
     extra=(f"chars={r.get('metadata', {}).get('total_chars')}" if r.get("ok") is not False else ""))

# --- 15) negative path: section ที่ไม่มีในฟอร์มนั้น → INVALID_INPUT ---------------
r = srv.get_filing_text("AAPL", form="10-K", section="Item 99")
bad_section = r.get("ok") is False and r.get("error", {}).get("code") == "INVALID_INPUT"
print(f"[{'PASS' if bad_section else 'FAIL/code'}] guard: filing_text section 'Item 99' → "
      f"{r.get('error', {}).get('code') if r.get('ok') is False else 'NO ERROR (unexpected)'}")

print("=" * 60)
print("done — ดู verdict ต่อบรรทัด: PASS / SKIP(missing-secret|provider) / FAIL(code|provider|environment)")
