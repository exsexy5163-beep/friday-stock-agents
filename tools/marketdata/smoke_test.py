#!/usr/bin/env python3
"""Market-data toolkit smoke test — ยืนยันว่าทั้ง 4 แหล่งดึงข้อมูลได้จริง.

รันด้วย venv 3.12 ของชุดนี้เท่านั้น (ไม่ใช่ .venv หลัก 3.9):
    tools/marketdata/.venv/bin/python tools/marketdata/smoke_test.py

- อ่าน API key จาก macOS Keychain (ไม่เก็บ key ในไฟล์)
- ถ้าไม่มี key → ข้าม FMP/Alpha Vantage อย่างสุภาพ ไม่ crash
- Alpha Vantage free = 25 ครั้ง/วัน → สคริปต์นี้ยิงแค่ครั้งเดียว
"""
import re
import subprocess
from pathlib import Path

import requests

EDGAR_IDENTITY = (Path(__file__).with_name(".edgar-identity").read_text(encoding="utf-8").strip()
                  if Path(__file__).with_name(".edgar-identity").exists() else "")  # setup.sh เป็นคนเขียนไฟล์นี้
KEYCHAIN_ACCOUNT = "friday"


def redact(text: str) -> str:
    """ลบ API key ที่ติดมากับข้อความ error ก่อนพิมพ์.

    ข้อความ exception ของ requests **มี URL เต็มติดมาด้วย** เช่น
    'Max retries exceeded with url: /stable/ratios?symbol=AAPL&apikey=<คีย์จริง>'
    การพิมพ์ตรง ๆ = key หลุดออกหน้าจอ/ลง log (ผิด CLAUDE.md §2b ห้าม log secrets).
    """
    text = re.sub(r"(apikey=)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE)
    text = re.sub(r"(api[_-]?key[\"'=:\s]+)[^&\s\"']+", r"\1<redacted>", text, flags=re.IGNORECASE)
    return text


def keychain(service: str) -> str | None:
    """อ่านค่า secret จาก macOS Keychain ."""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def test_yfinance():
    print("1) yfinance — ราคา US (AAPL) + ไทย (PTT.BK)")
    import yfinance as yf
    for sym in ["AAPL", "PTT.BK"]:
        df = yf.Ticker(sym).history(period="5d")
        if len(df):
            print(f"   {sym}: {len(df)} rows, last close = {round(float(df['Close'].iloc[-1]), 2)}")
        else:
            print(f"   {sym}: NO DATA")


def test_edgartools():
    print("2) edgartools — งบ US จาก SEC (AAPL 10-K ล่าสุด)")
    from edgar import set_identity, Company
    set_identity(EDGAR_IDENTITY)
    f = Company("AAPL").get_filings(form="10-K").latest()
    print(f"   form={f.form} filed={f.filing_date} accession={f.accession_no}")


def _fmp_probe(label: str, url: str) -> None:
    """ยิง FMP หนึ่งครั้งแล้วรายงาน "ความจริง" — status ก่อนเสมอ ห้ามเหมาว่าเน็ตพัง.

    body ที่ไม่ใช่ JSON ต้อง **ไม่** โยน JSONDecodeError ทะลุออกไป: มันเป็นคลาสลูกของ
    requests.RequestException ผู้เรียกที่ดักรวมกันจะสรุปผิดว่า "เรียกไม่ได้" ทั้งที่ FMP ตอบแล้ว
    (บั๊กที่เจอจริง 2026-09-03 ใน core.fetch_ratios/fetch_estimates)
    """
    r = requests.get(url, timeout=25)
    try:
        j = r.json()
    except ValueError:
        print(f"   {label}: HTTP {r.status_code} · body ไม่ใช่ JSON → {redact(r.text)[:110]}")
        return
    if isinstance(j, list) and j:
        row = j[0]
        print(f"   {label}: HTTP {r.status_code} OK · rows={len(j)} "
              f"fiscalYear/date={row.get('fiscalYear') or row.get('date')}")
    else:
        print(f"   {label}: HTTP {r.status_code} · ไม่มีข้อมูล → {redact(str(j))[:110]}")


def test_fmp():
    print("3) FMP — ratio + estimates (ต้องใช้ stable/ API; v3 เก่าตายแล้ว)")
    key = keychain("fmp-api")
    if not key:
        print("   [ข้าม] ยังไม่ได้เซฟ fmp-api ใน Keychain")
        return
    base = "https://financialmodelingprep.com/stable"
    # FMP เลิก support endpoint /api/v3/ แล้ว — ต้องใช้ base /stable/ เท่านั้น
    #
    # ยิงสองตัวเสมอ: ticker **ในชุด** ที่แพ็กเกจครอบคลุม กับ ticker **นอกชุด** —
    # เดิมทดสอบแต่ AAPL อย่างเดียวจึงผ่านตลอดและมองไม่เห็นว่า tier 2 ใช้กับหุ้นเล็ก/กลางไม่ได้
    # (วัดจริง 2026-09-03: AAPL/MSFT/JNJ/XOM/V ผ่าน · TER/COHU/KEYS/ATEYY/BRK.B ได้ HTTP 402)
    # แถวที่ขึ้น 402 คือ **ผลที่คาดไว้** ของแพ็กเกจฟรี ไม่ใช่ความล้มเหลวของ smoke test
    _fmp_probe("ratios AAPL   (ในชุดฟรี — คาดว่า 200)", f"{base}/ratios?symbol=AAPL&period=annual&limit=1&apikey={key}")
    _fmp_probe("ratios TER    (นอกชุดฟรี — คาดว่า 402)", f"{base}/ratios?symbol=TER&period=annual&limit=1&apikey={key}")
    # period เป็นพารามิเตอร์บังคับของ analyst-estimates — ขาดไปได้ HTTP 400 ทุก ticker
    _fmp_probe("estimates AAPL(ต้องมี period)      ", f"{base}/analyst-estimates?symbol=AAPL&period=annual&limit=1&apikey={key}")


def test_alpha_vantage():
    print("4) Alpha Vantage — สำรองฉุกเฉิน (free = 25 ครั้ง/วัน, ยิงครั้งเดียว)")
    key = keychain("alphavantage-api")
    if not key:
        print("   [ข้าม] ยังไม่ได้เซฟ alphavantage-api ใน Keychain")
        return
    from alpha_vantage.timeseries import TimeSeries
    ts = TimeSeries(key=key, output_format="pandas")
    data, _ = ts.get_daily("AAPL", outputsize="compact")
    print(f"   AAPL daily: {len(data)} rows, latest={data.index[0].date()}")


if __name__ == "__main__":
    for fn in (test_yfinance, test_edgartools, test_fmp, test_alpha_vantage):
        print("=" * 60)
        try:
            fn()
        except Exception as e:  # noqa: BLE001 — smoke test ต้องไม่ล้มทั้งชุดเพราะแหล่งเดียวพัง
            print(f"   FAIL: {type(e).__name__}: {redact(str(e))}")
    print("=" * 60)
    print("done")
