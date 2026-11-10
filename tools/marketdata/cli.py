#!/usr/bin/env python3
"""marketdata CLI — ดึงข้อมูลการเงินตามชนิดข้อมูล แทน Fiscal.ai connector ที่ถอดออกแล้ว.

เรียกผ่าน launcher เสมอ (มันผูก venv 3.12 ของ toolkit ให้):
    tools/marketdata/marketdata <subcommand> <args>

หลักการ (CLAUDE.md §7 — ความถูกต้อง + ความเป็นทางการ):
  ทุก output ขึ้น provenance header: source (+tier) / as_of / endpoint
  ชั้น 1 ทางการ = SEC EDGAR (งบ/insider/ownership US) · FRED (มหภาค)
  ชั้น 2 aggregator (ธง) = FMP stable/ (ratio)
  ชั้น 3 รอง (ธง) = yfinance (ราคา) · alpha-vantage (ราคาสำรอง) · FMP estimates (คาดการณ์)

ขอบเขต: subcommand price = US+ไทย(.BK); ที่เหลือ = US เท่านั้น.\nfilings/filing-text = อ่านตัวเอกสาร SEC (8-K, DEF 14A, 10-K/10-Q รายหัวข้อ) — ชั้น 1 ทางการ.
CLI = ดึงข้อมูลอย่างเดียว คืนค่าดิบ — การคำนวณวิเคราะห์ทำในเอเจนต์บน main .venv (Decimal/numpy/scipy).

หมายเหตุสถาปัตยกรรม: logic ดึงข้อมูลจริงอยู่ใน core.py (ใช้ร่วมกับ mcp_server.py); ไฟล์นี้เป็น
ชั้นนำเสนอ (parse args → เรียก core → พิมพ์ provenance + view) — financials คงเส้นทาง render เดิมไว้.
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import core
from core import MarketDataError, keychain


def today_iso() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def prov(source: str, tier: int, endpoint: str, as_of: str | None = None) -> None:
    """พิมพ์ provenance header บังคับ — ทุก subcommand ต้องเรียกก่อนพิมพ์ข้อมูล."""
    print(f"source={source} (tier {tier})  as_of={as_of or today_iso()}  endpoint={endpoint}")


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _round4(s) -> str | None:
    return str(round(float(s), 4)) if s is not None else None


# ---------------------------------------------------------------- price (yfinance / alpha-vantage)
def cmd_price(args: argparse.Namespace) -> None:
    t = args.ticker
    if args.source == "av":
        key = keychain("alphavantage-api")
        if not key:
            die("ไม่มี alphavantage-api ใน Keychain (แหล่งสำรอง) — ใช้ default yfinance แทน")
        from alpha_vantage.timeseries import TimeSeries
        ts = TimeSeries(key=key, output_format="pandas")
        data, _ = ts.get_daily(t, outputsize="compact")
        prov("Alpha Vantage", 3, "alpha_vantage TIME_SERIES_DAILY (สำรอง 25/วัน)")
        last = data.iloc[0]
        _emit({"ticker": t, "latest_date": str(data.index[0].date()),
               "close": str(last["4. close"]), "rows": len(data)}, args.json)
        return
    res = core.fetch_price(t, period=args.period, market=args.market)
    rows = res["data"]
    prov("Yahoo Finance", 3, f"yfinance history period={args.period} (ราคา = market data ชั้นรอง ติดธง)")
    tail = rows[-args.rows:]
    out = {"ticker": t,
           "last_close": _round4(rows[-1]["adj_close"]),
           "last_date": rows[-1]["date"],
           "tail": [{"date": r["date"], "close": _round4(r["adj_close"])} for r in tail]}
    _emit(out, args.json)


# ---------------------------------------------------------------- financials (edgartools / SEC)
def cmd_financials(args: argparse.Namespace) -> None:
    """เดินผ่าน core.fetch_financials ตัวเดียวกับที่ MCP ใช้ — เดิม subcommand นี้เรียก edgartools เอง
    จึงไม่ได้ concept / filing_form / latest_period / currency และทำ quarterly ไม่ได้."""
    wanted = ["income", "balance", "cashflow"] if args.statement == "all" else [args.statement]
    res = core.fetch_financials(args.ticker, period=args.period, statements=wanted, years=args.years)
    m = res["metadata"]
    prov("SEC EDGAR (edgartools)", 1,
         f"{m.get('filing_form') or '?'} {m.get('filing_date') or '?'} acc={m.get('accession') or '?'} "
         f"path={m.get('data_path')} currency={m.get('currency') or '?'} — ตัวเลขดิบ; ratio คำนวณเองด้วย Decimal")
    if res.get("note"):
        print(f"note: {res['note']}")
    if args.json:
        _emit(res, True)
        return
    for name, recs in res["statements"].items():
        print(f"\n=== {name} === (งวดล่าสุด {m.get('latest_period') or '?'})")
        if not recs:
            print("[ไม่มีข้อมูล]")
            continue
        cols = [k for k in recs[0] if k not in ("line_item", "concept")]
        w = max(len(r["line_item"]) for r in recs)
        print("  ".join([f"{'line_item':<{w}}"] + [f"{c:>18}" for c in cols]))
        for r in recs:
            print("  ".join([f"{r['line_item']:<{w}}"] + [f"{core._fmt_num(r[c]):>18}" for c in cols]))


# ---------------------------------------------------------------- ratios (FMP stable/)
def cmd_ratios(args: argparse.Namespace) -> None:
    res = core.fetch_ratios(args.ticker, limit=args.limit)
    prov("FMP stable/ratios", 2,
         "financialmodelingprep.com/stable/ratios (aggregator — ตรวจทานกับงบดิบ EDGAR)")
    _emit(res["data"], args.json, force_json=True)


# ---------------------------------------------------------------- insider (edgartools Form 4)
def cmd_insider(args: argparse.Namespace) -> None:
    res = core.fetch_insider(args.ticker, limit=args.rows)
    prov("SEC EDGAR (edgartools)", 1,
         f"Company({args.ticker}).get_filings(form=4) — insider transactions (Form 4, enriched)")
    if not res["data"]:
        print(f"NO-DATA: ไม่พบ filing 4 ของ {args.ticker}")
        return
    _emit(res["data"], args.json, force_json=True)


# ---------------------------------------------------------------- ownership (edgartools SC 13D/G)
def cmd_ownership(args: argparse.Namespace) -> None:
    res = core.fetch_ownership(args.ticker, limit=args.rows)
    prov("SEC EDGAR (edgartools)", 1,
         f"Company({args.ticker}).get_filings(form=SC 13D/G) — major/activist stakes "
         f"(13F holders-by-ticker = ไม่รองรับ; %/หุ้นที่ดึงไม่ได้ = null + note)")
    if not res["data"]:
        print(f"NO-DATA: ไม่พบ filing SC 13D/G ของ {args.ticker}")
        return
    _emit(res["data"], args.json, force_json=True)


# ---------------------------------------------------------------- macro (FRED)
def cmd_macro(args: argparse.Namespace) -> None:
    res = core.fetch_macro(args.series)
    rows = res["data"]
    prov("FRED (St. Louis Fed)", 1, f"fred/series/observations id={args.series}")
    tail = rows[-args.rows:]
    _emit({"series": args.series,
           "latest": {"date": rows[-1]["date"], "value": rows[-1]["value"]},
           "tail": tail}, args.json)


# ---------------------------------------------------------------- estimates (FMP — ธงไม่ official)
def cmd_estimates(args: argparse.Namespace) -> None:
    res = core.fetch_estimates(args.ticker)
    print(f"# NOTE: {res.get('note', '')}")
    m = res["metadata"]
    prov(m.get("source", "FMP stable"), m.get("source_tier", 3),
         "financialmodelingprep.com/stable/analyst-estimates (ไม่ official; free มักไม่ครอบคลุม)")
    if not res["data"]:
        print("NO-DATA: ไม่มี estimates → ใช้เว็บแล้วติดธง (ไม่ใช่ error)")
        return
    _emit(res["data"], args.json, force_json=True)


# ---------------------------------------------------------------- universe (Nasdaq screener — ธงไม่ official)
def cmd_universe(args: argparse.Namespace) -> None:
    exch = [e.strip() for e in args.exchanges.split(",") if e.strip()]
    keep = [s.strip() for s in args.keep_sector.split(",") if s.strip()]
    drop = [s.strip() for s in args.exclude_sector.split(",") if s.strip()]
    res = core.fetch_universe(exchanges=exch, market_cap_min=args.cap_min, market_cap_max=args.cap_max,
                              sector_keep=keep or None, sector_exclude=drop or None,
                              us_only=not args.include_foreign)
    m = res["metadata"]
    prov("Nasdaq screener", 3,
         "api.nasdaq.com/api/screener/stocks?download=true (taxonomy = Nasdaq ไม่ใช่ GICS; ไม่บังคับกำไรบวก)")
    print(f"# count: {m['count']}  filters: {m['filters']}")
    if m.get("exchange_warnings"):
        print(f"# WARN: {m['exchange_warnings']}")
    _emit(res["universe"], args.json, force_json=True)


# ---------------------------------------------------------------- filings (edgartools ทุกฟอร์ม)
def cmd_filings(args: argparse.Namespace) -> None:
    res = core.fetch_filings(args.ticker, form=args.form, limit=args.rows,
                             start=args.start, end=args.end, detail=args.detail)
    m = res["metadata"]
    prov("SEC EDGAR (edgartools)", 1,
         f"Company({args.ticker}).get_filings(form={m['form'] or 'ทุกฟอร์ม'}) — metadata เท่านั้น "
         f"(เนื้อ filing ใช้ subcommand filing-text)")
    if res.get("note"):
        print(f"# NOTE: {res['note']}")
    if "total_matching_form" in m:
        print(f"# returned: {m['returned']} / ตรงฟอร์มทั้งหมด: {m['total_matching_form']}")
    else:
        d = m["date_filter"]
        print(f"# returned: {m['returned']} (กรอง {d['start'] or 'เริ่มแรก'} ถึง {d['end'] or 'ล่าสุด'}"
              f"{' — หมดช่วงแล้ว' if m.get('exhausted') else ' — อาจมีอีก เพิ่ม --rows'}) "
              f"/ ตรงฟอร์มทั้งหมดก่อนกรองวันที่: {m['total_matching_form_before_date_filter']}")
    if not res["data"]:
        print(f"NO-DATA: ไม่พบ filing ของ {args.ticker} (form={m['form']})")
        return
    _emit(res["data"], args.json, force_json=True)


# ---------------------------------------------------------------- filing-text (เนื้อ filing, แบ่งหน้า)
def cmd_filing_text(args: argparse.Namespace) -> None:
    res = core.fetch_filing_text(args.ticker, form=args.form, accession=args.accession,
                                 section=args.section, exhibit=args.exhibit,
                                 max_chars=args.max_chars, offset=args.offset)
    m = res["metadata"]
    prov("SEC EDGAR (edgartools)", 1,
         f"{m['form']} {m['filing_date']} acc={m['accession']} — ขอบเขต: {m['scope']}")
    print(f"# chars: {m['returned_chars']} / {m['total_chars']}  offset={m['offset']}  "
          f"has_more={m['has_more']}" + (f"  next_offset={m['next_offset']}" if m["has_more"] else ""))
    print(f"# url: {m['url']}")
    if args.json:
        _emit(res, True)
        return
    print()
    print(res["text"])
    if m["has_more"]:
        print(f"\n# ...ตัดที่ {m['returned_chars']} ตัวอักษร — อ่านต่อ: เติม --offset {m['next_offset']}")


def cmd_filing_bundle(args: argparse.Namespace) -> None:
    """Local artifacts only; never emit the full section text."""
    from filing_bundle import collect_bundle
    result = collect_bundle(args.ticker, args.form, args.accession, args.section)
    prov("SEC EDGAR (edgartools)", 1, "filing-bundle full-section local artifacts")
    _emit(result, True)
    if result["status"] != "COMPLETE":
        sys.exit(2)


# ---------------------------------------------------------------- helpers
def _emit(obj, as_json: bool, force_json: bool = False) -> None:
    if as_json or force_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    else:
        if isinstance(obj, dict):
            for k, v in obj.items():
                print(f"{k}: {v}")
        else:
            print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="marketdata", description="Market-data fetch toolkit CLI")
    p.add_argument("--json", action="store_true", help="output as JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("price", help="ราคาย้อนหลัง (US+ไทย .BK)")
    sp.add_argument("ticker"); sp.add_argument("--period", default="1y")
    sp.add_argument("--rows", "--limit", dest="rows", type=int, default=5)
    sp.add_argument("--market", choices=["US", "TH", "AUTO"], default="AUTO")
    sp.add_argument("--source", choices=["yf", "av"], default="yf")
    sp.set_defaults(func=cmd_price)

    sf = sub.add_parser("financials", help="งบ US ดิบจาก SEC EDGAR")
    sf.add_argument("ticker")
    sf.add_argument("--statement", "--statements", dest="statement",
                    choices=["income", "balance", "cashflow", "all"], default="income")
    sf.add_argument("--period", choices=["annual", "quarterly"], default="annual",
                    help="งวด (เท่ากับ period ของ MCP)")
    sf.add_argument("--years", type=int, default=5, help="จำนวนงวดที่คืน (1-10)")
    sf.set_defaults(func=cmd_financials)

    sr = sub.add_parser("ratios", help="ratio US (FMP stable/ — aggregator)")
    sr.add_argument("ticker"); sr.add_argument("--limit", "--rows", dest="limit", type=int, default=1)
    sr.set_defaults(func=cmd_ratios)

    si = sub.add_parser("insider", help="insider Form 4 (SEC)")
    si.add_argument("ticker"); si.add_argument("--rows", "--limit", dest="rows", type=int, default=10)
    si.set_defaults(func=cmd_insider)

    so = sub.add_parser("ownership", help="ผู้ถือใหญ่/activist SC 13D/G (SEC)")
    so.add_argument("ticker"); so.add_argument("--rows", "--limit", dest="rows", type=int, default=10)
    so.set_defaults(func=cmd_ownership)

    sm = sub.add_parser("macro", help="มหภาค FRED (series id)")
    sm.add_argument("series"); sm.add_argument("--rows", "--limit", dest="rows", type=int, default=5)
    sm.set_defaults(func=cmd_macro)

    se = sub.add_parser("estimates", help="consensus (ชั้น 3 ธง — ไม่ official)")
    se.add_argument("ticker")
    se.set_defaults(func=cmd_estimates)

    su = sub.add_parser("universe", help="list หุ้น US ตาม cap band + sector (Nasdaq screener, ชั้น 3 ธง)")
    su.add_argument("--exchanges", default="NYSE,NASDAQ,AMEX", help="exchange ที่ดึง (คั่น ,)")
    su.add_argument("--cap-min", "--market-cap-min", dest="cap_min", default="0", help="market cap ขั้นต่ำ (เช่น 300e6)")
    su.add_argument("--cap-max", "--market-cap-max", dest="cap_max", default="1e15", help="market cap ขั้นสูง (เช่น 1e9)")
    su.add_argument("--keep-sector", "--sector-keep", dest="keep_sector", default="", help="เก็บเฉพาะ sector เหล่านี้ (คั่น ,)")
    su.add_argument("--exclude-sector", "--sector-exclude", dest="exclude_sector", default="", help="ตัด sector เหล่านี้ (คั่น ,)")
    su.add_argument("--include-foreign", action="store_true", help="เก็บ non-US ด้วย (default ตัดทิ้ง)")
    su.set_defaults(func=cmd_universe)
    sfl = sub.add_parser("filings", help="ลิสต์ filing SEC ทุกฟอร์ม (8-K / DEF 14A / 10-K / 10-Q ...)")
    sfl.add_argument("ticker")
    sfl.add_argument("--form", default=None, help="ฟอร์ม เช่น 8-K, 'DEF 14A', 10-K (ไม่ใส่ = ทุกฟอร์ม)")
    sfl.add_argument("--rows", "--limit", dest="rows", type=int, default=20, help="จำนวน filing ที่คืน")
    sfl.add_argument("--start", default=None, help="กรองวันที่ยื่นตั้งแต่ (YYYY-MM-DD)")
    sfl.add_argument("--end", default=None, help="กรองวันที่ยื่นถึง (YYYY-MM-DD)")
    sfl.add_argument("--detail", action="store_true",
                     help="เติม item code ของ 8-K + รายการไฟล์แนบ — ต้องโหลด filing ทีละฉบับ "
                          "~1.2–2.5 วิ/ฉบับ (20 ฉบับ ≈ 23 วิ) ใช้คู่กับ --rows น้อย ๆ")
    sfl.set_defaults(func=cmd_filings)

    sft = sub.add_parser("filing-text", help="เนื้อข้อความใน filing (10-K รายหัวข้อ / 8-K exhibit / DEF 14A)")
    sft.add_argument("ticker")
    sft.add_argument("--form", default=None, help="ฟอร์มที่จะเอาฉบับล่าสุด เช่น 10-K, 8-K, 'DEF 14A'")
    sft.add_argument("--accession", default=None, help="เจาะ filing ฉบับนั้น (เลขจาก subcommand filings)")
    sft.add_argument("--section", default=None,
                     help="หัวข้อ — ชื่อต่างกันตามฟอร์ม: 10-K ใช้ 'Item 1A' (ความเสี่ยง) / 'Item 7' (MD&A); "
                          "10-Q ต้องมี Part นำหน้า 'Part II, Item 1A' / 'Part I, Item 2'; "
                          "DEF 14A ไม่แบ่ง section (ใส่ผิด → error บอกรายการที่มีจริง)")
    sft.add_argument("--exhibit", default=None, help="ไฟล์แนบ เช่น EX-99.1 (ข่าว earnings ที่แนบกับ 8-K)")
    sft.add_argument("--max-chars", type=int, default=20000, help="ตัดความยาวต่อครั้ง (เพดาน 100000)")
    sft.add_argument("--offset", type=int, default=0, help="เริ่มอ่านจากตัวอักษรที่เท่าไร (อ่านต่อหน้าถัดไป)")
    sft.set_defaults(func=cmd_filing_text)

    sfb = sub.add_parser("filing-bundle", help="เก็บ SEC sections ครบเป็นไฟล์ local; COMPLETE หรือ FAILED")
    sfb.add_argument("ticker")
    sfb.add_argument("--form", required=True, help="ฟอร์มที่ต้องตรงกับ accession")
    sfb.add_argument("--accession", required=True, help="เลขฉบับแบบ 0000000000-00-000000; ไม่ใช้ฉบับล่าสุดแทน")
    sfb.add_argument("--section", action="append", required=True,
                     help="ระบุซ้ำได้ เช่น --section 'Item 1A' --section 'Item 7'; เก็บ comma ในชื่อไว้")
    sfb.set_defaults(func=cmd_filing_bundle)

    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        args.func(args)
    except MarketDataError as e:
        die(e.message)


if __name__ == "__main__":
    main()
