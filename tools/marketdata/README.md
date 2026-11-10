# tools/marketdata — Market-Data Python Toolkit

ชุดเครื่องมือ Python สำหรับดึงข้อมูลการเงิน (งบ / ราคา / ratio) มาแทนชั้น Fiscal.ai connector ที่หายไปจาก `.mcp.json`

> **ใช้งานผ่าน MCP tools เป็นช่องหลัก** (`mcp__friday-marketdata-mcp__*` 11 ตัว) หรือ CLI ตัวเดียว
> `tools/marketdata/marketdata <subcommand>` (ดูหัวข้อ [CLI](#cli) ล่าง) — waterfall = CLAUDE.md §7
>

## ครัวแยก (Python 3.12)

ติดตั้งแยกจาก `.venv` หลัก (Python 3.9.6) เพราะ edgartools ต้องการ Python ≥3.10 และไม่อยากกระทบ
แพ็กเกจที่ pin ไว้กับ 3.9 (vectorbt / numba / llama-index)

```bash
# รันด้วย interpreter ของชุดนี้เสมอ
tools/marketdata/.venv/bin/python <script>
```

สร้างใหม่ (ถ้าต้อง rebuild):

```bash
uv venv --python 3.12 tools/marketdata/.venv
uv pip install --python tools/marketdata/.venv/bin/python -r tools/marketdata/requirements.txt
```

## 5 แหล่งข้อมูล

| แหล่ง | ใช้ทำอะไร | ชั้น | key | หมายเหตุ |
|---|---|---|---|---|
| **edgartools** 5.36.0 | งบ US (10-K/XBRL ดิบ) + **insider (Form 4)** + **ownership (SC 13D/G)** จาก SEC | 1 ทางการ | ไม่ใช้ (ตั้ง `EDGAR_IDENTITY` = อีเมล) | ต้นฉบับงบ US; 13F holders-by-ticker = defer |
| **FRED** (`fredapi` 0.5.2) | มหภาค — rate/CPI/yield/GDP | 1 ทางการ | `fred-api` (Keychain) | St. Louis Fed; series id (CPIAUCSL, DGS10, FEDFUNDS, GDP) |
| **FMP** (REST) | ratio/งบสำเร็จรูป + estimates | 2 aggregator | `fmp-api` (Keychain) | base `stable/` เท่านั้น; estimates free มักไม่คืน → ติดธง |
| **yfinance** 1.4.1 | ราคาย้อนหลัง US + **ไทย (`.BK`)** | 3 รอง | ไม่ใช้ | **แทน stooq**; Yahoo ไม่ทางการ ติดธง |
| **Alpha Vantage** 3.0.0 | ราคา/indicator สำรอง | 3 สำรอง | `alphavantage-api` (Keychain) | **สำรองฉุกเฉิน** — free แค่ 25 ครั้ง/วัน |

## CLI

`tools/marketdata/marketdata <subcommand> [--json]` — launcher ผูก venv 3.12 ให้เอง (รันที่ไหนก็ได้).
> **⚠️ subagent ต้องใช้ absolute path:** `__FRIDAY_ROOT__/tools/marketdata/marketdata <subcommand>` — Bash ของ subagent reset cwd กลับ root ทุก call ทำให้ relative path ได้ `no such file` (launcher resolve dir ตัวเองได้ก็จริง แต่ shell ต้องหาตัว launcher เจอก่อน).
ทุก output ขึ้น **provenance header** บังคับ: `source (+tier) / as_of / endpoint`.
`price` = US+ไทย; subcommand อื่น = **US เท่านั้น** (ticker ไทย → error ชัด).

> **ชื่อธง:** CLI รับได้ทั้งชื่อเดิม (`--rows`, `--cap-min`, `--keep-sector`) และชื่อแบบเดียวกับ
> พารามิเตอร์ฝั่ง MCP (`--limit`, `--market-cap-min`, `--sector-keep`, `--statements`) — ใส่แบบไหนก็ได้.
> ต่างกันอย่างเดียวที่ความหมาย: `--rows` ของ CLI ตัด **ตอนแสดงผล** ส่วน `limit` ของ MCP ตัด **ตอนดึง**

| subcommand | ตัวอย่าง | แหล่ง/ชั้น |
|---|---|---|
| `price <T>` | `marketdata price AAPL` · `price PTT --market TH` · `price AAPL --source av` | yfinance / AV (3) |
| `financials <T>` | `marketdata financials AAPL --statement income\|balance\|cashflow\|all [--period annual\|quarterly] [--years N]` | EDGAR (1) ดิบ |
| `ratios <T>` | `marketdata ratios AAPL` | FMP stable/ (2) |
| `insider <T>` | `marketdata insider AAPL` | EDGAR Form 4 (1) |
| `ownership <T>` | `marketdata ownership AAPL` | EDGAR SC 13D/G (1) |
| `macro <SERIES>` | `marketdata macro CPIAUCSL` | FRED (1) |
| `estimates <T>` | `marketdata estimates AAPL` | FMP/เว็บ (3, ธงไม่ official) |
| `universe` | `marketdata universe --cap-min 300e6 --cap-max 1e9` | Nasdaq screener (3, ธง) |
| `filings <T>` | `marketdata filings AAPL --form 8-K --rows 5` (+`--detail` เพื่อดู item code, ช้าขึ้น) | EDGAR ทุกฟอร์ม (1) |
| `filing-text <T>` | 10-K: `--section 'Item 1A'` · 10-Q: `--section 'Part II, Item 1A'` · 8-K: `--exhibit EX-99.1` | EDGAR เนื้อเอกสาร (1) |

CLI = ดึงข้อมูลดิบเท่านั้น — การคำนวณวิเคราะห์ทำในเอเจนต์บน **main `.venv`** (Decimal/numpy/scipy) ไม่ใช่ venv นี้

### ตัวอย่างใช้งานสั้น ๆ

```python
# ราคา (yfinance) — US + ไทย
import yfinance as yf
yf.Ticker("AAPL").history(period="1y")
yf.Ticker("PTT.BK").history(period="1y")   # หุ้นไทยเติม .BK

# งบ US (edgartools)
from edgar import set_identity, Company
set_identity("your-email@example.com")
Company("AAPL").get_filings(form="10-K").latest()

# FMP ratio — ต้องใช้ stable/ เท่านั้น
import requests, subprocess
key = subprocess.run(["security","find-generic-password","-s","fmp-api","-a","friday","-w"],
                     capture_output=True, text=True).stdout.strip()
requests.get(f"https://financialmodelingprep.com/stable/ratios?symbol=AAPL&apikey={key}").json()
```

## API key — macOS Keychain

key ไม่เคยอยู่ในไฟล์/repo — เก็บใน Keychain เท่านั้น ดูคำสั่งเซฟ/อ่าน/ลิงก์สมัครใน [.env.example](.env.example)

## วินัยตัวเลข (CLAUDE.md §8)

- edgartools ให้ตัวเลข **ดิบ** → คำนวณ ratio/margin/% ด้วย `decimal.Decimal` เสมอ ห้าม `float` มักง่าย
- FMP ให้ ratio คำนวณมาแล้ว แต่ควร verify กับงบดิบ (edgartools) ได้

## Filing bundle — CLI/local artifacts only

`filing-bundle` collects all requested sections before returning `COMPLETE`.
It does not call specialists, add an MCP tool, or change `get_filing_text`.

```bash
__FRIDAY_ROOT__/tools/marketdata/marketdata filing-bundle ISRG \
  --form 10-K --accession 0001035267-25-000017 \
  --section "Item 1A" --section "Item 7"
```

Ticker, form, accession and at least one section are required. Accession must
match `0000000000-00-000000` literally; malformed input is rejected, not repaired.
Use repeatable `--section`: a 10-Q name such as `"Part I, Item 2"` remains a
single name. There is no comma splitting, per-ticker section list or latest-filing
fallback. Duplicate section names (ignoring case/outer whitespace) fail validation.

### Why full-section retrieval, not pagination (Option A)

The existing core `_section_text` already obtains the full `obj[match]` string;
`fetch_filing_text` only slices it afterward. The new public
`fetch_filing_section_full` reads the complete parser section once per worker
attempt and writes it directly to a local UTF-8 artifact. It does not repeatedly
reparse the filing for each offset or send full text through an MCP response.
Legacy `_section_text`, `fetch_filing_text`, CLI `filing-text`, and the MCP schema
retain their existing behavior and pagination limits.

`COMPLETE` proves collection of the entire string returned by the parser,
identity checks and local artifact integrity. It does **not** independently prove
the parser's section boundaries match every byte of the original SEC HTML.
The v1 helper requires parser-discoverable sections. A form without that support
fails explicitly; it does not silently substitute full-filing text.

**10-K heading guard + heading-split (added 2026-09-24, GEV case).** Some 10-Ks list
"Note N" rows inside the table of contents; edgartools (5.36 and 5.58) then returns
`NOTE 7. LEASES` as "Item 7" with no error. For 10-K/10-K/A `Item N` requests only:
if the parser text opens with a contradicting label (`NOTE n` or another Item number),
or the parser did not list the item, the section is cut from the same filing's full
text at its own `ITEM N.` line heading, up to the next later item. Table-of-contents /
cross-reference-index rows (padded page column) and in-sentence references (quoted
title, or previous line ending "See"/"in"/","…) are ignored. No usable heading →
the original `SECTION_DISCOVERY_FAILED` / `PARSER_ERROR` (fail closed; a GE-style
cross-reference-index 10-K still fails for items the parser does not find).
Text with no Item label at all is not treated as a conflict. Each section's metadata
records `section_method`: `parser` or `heading-split`. The MCP/CLI `filing-text`
section path applies the same guard (its metadata/scope is unchanged). 10-Q and
other forms are untouched.

### Output and no-overwrite policy

- Completed: `scratch/filing-bundles/<TICKER>/<ACCESSION>/manifest.json` and
  `sections/section-001.txt`, `section-002.txt`, etc., in request order.
- CLI stdout: provenance header followed by compact JSON with `status`, path
  and failures; no section body. Exit 0 only for `COMPLETE`; retrieval/collection
  failure exits 2. Argument-parser usage errors also exit nonzero before retrieval.
- Manifest includes ticker/form/accession, source `SEC EDGAR (edgartools)`, tier 1,
  as-of date, collection method, existing-target policy, max attempts and per-section
  status, relative file path, character count, SHA-256, metadata and attempt history.
  Section metadata retains filing date, URL and source retrieval date.
- Character counts are Unicode characters in decoded UTF-8 (not bytes). Hashes
  come from file bytes read back after writing. All sections, identities, lengths,
  hashes and the manifest are checked before publishing by a same-filesystem
  atomic directory rename. V1 uses macOS `renamex_np` with `RENAME_EXCL` and
  `RENAME_NOFOLLOW_ANY`: even a target created after the preflight check is not
  overwritten. Platforms without this primitive fail closed, with no ordinary
  rename fallback.
- Any section failure makes the whole run `FAILED`. Diagnostic bundles are kept
  separately in `scratch/filing-bundles/.failed/<run-id>/`, with `manifest.json`;
  they may contain successful sections and untrusted partial worker outputs, but
  are never an analysis-ready bundle. Invalid input creates no filesystem output.
- Existing target, even an empty directory: `BUNDLE_EXISTS`. V1 never overwrites,
  automatically reuses, deletes or merges it and has no `--force` option. Inspect
  and verify the existing artifact; relocating/removing it is a separate explicit
  user decision, not something this helper does.
- Root is fixed; no `--output` override. Traversal and existing symlink components
  are rejected. A per-target exclusive lock serializes cooperating helper runs.
  This assumes a trusted local filesystem: pathname checks do not defend against
  a hostile local actor replacing ancestor directories between a check and a file
  operation. Full directory-descriptor-based isolation is outside v1 scope.
- A killed process may leave `.pending-*` and a lock. Neither is a completed
  bundle; verify the owner process has stopped before any manual cleanup. No
  automatic stale-lock deletion. If publication succeeds but lock cleanup fails,
  the valid bundle remains `COMPLETE` with a `LOCK_CLEANUP_FAILED` CLI warning.
  If disk/path errors prevent saving even a failed
  manifest, CLI returns `FAILED` with `FAILED_ARTIFACT_WRITE` instead of claiming
  an artifact exists. Atomic visibility is not a power-loss durability guarantee.

### Retry and error semantics

Parent holds no edgartools objects. Every attempt runs a new subprocess using
`__FRIDAY_ROOT__/tools/marketdata/.venv/bin/python`, an argument list
and `shell=False`. Each section has at most two attempts, 120 seconds per attempt.
Timeout terminates the worker before the next attempt. The worker returns only
metadata/errors on stdout; the full text travels through a local file.

Retry allowlist: `PROVIDER_ERROR`, `NETWORK_ERROR`, `RATE_LIMITED`, `PARSER_ERROR`,
`SECTION_DISCOVERY_FAILED`, `EMPTY_SECTION`, `WORKER_TIMEOUT`, and only if marked
recoverable. A fresh process is an isolation/retry mechanism, not evidence that
it fixes a historical parser defect.

Malformed input and duplicates fail before workers start. Identity mismatch,
protocol/encoding errors, count mismatch, missing interpreter, filesystem failure,
existing target and lock conflicts are not retried. The final error code and
attempt count remain in the failed manifest; a recovered error remains in the
successful section's `attempt_history`.

The new full-section API accepts only actual strings from the parser. Dicts,
lists, bytes, numbers, objects and null are `PARSER_ERROR`, never stringified into
apparently valid section text. Legacy `get_filing_text` coercion is unchanged.

If a requested section cannot be discovered, including a standard form section,
the result after retry is `SECTION_DISCOVERY_FAILED`. This deliberately remains
a retrieval failure, not a claim that the company omitted information. Missing
exact accession is `FILING_NOT_FOUND`, also not company non-disclosure. There is
no conversion to `[ข้อมูลไม่พอ]` or `[ไม่เปิดเผย]` in this workflow.

### Tests

No new dependencies are required; offline tests use standard-library unittest
with mocked providers plus real fresh worker subprocesses using a fake provider.

```bash
# Offline only; live tests are skipped without the opt-in environment variable.
tools/marketdata/.venv/bin/python -B -m unittest discover \
  -s tools/marketdata -p 'test_filing_bundle*.py' -v

# Live SEC: creates the pinned ISRG bundle without overwriting, checks headings,
# identities, files and hashes, then runs legacy SEC-only smoke/pagination cases.
MARKETDATA_SEC_LIVE=1 tools/marketdata/.venv/bin/python -B -m unittest discover \
  -s tools/marketdata -p test_filing_bundle_live.py -v

# Explicitly verify an already published bundle instead of fetching it again.
# This is a test-harness option, not silent reuse in the production collector.
# Legacy SEC probes still run live.
MARKETDATA_SEC_LIVE=1 MARKETDATA_BUNDLE_VERIFY_EXISTING=1 \
  tools/marketdata/.venv/bin/python -B -m unittest discover \
  -s tools/marketdata -p test_filing_bundle_live.py -v
```

The live harness executes the SEC-only statements in
`mcp_smoke_test.py` and `smoke_test.test_edgartools` without running their
Keychain/FMP/FRED/price endpoints. One fixture is explicitly corrected in memory:
the EX-99.1 test pins a filing whose exhibit was first verified with `get_filings`.
The original smoke assumes the latest AAPL 8-K always has EX-99.1; both the
prechange and current core returned the same `INVALID_INPUT` on 2026-09-07 because
the latest was a management 8-K/A without that exhibit. The original smoke source
is unchanged; the harness does not weaken its success assertions. Baseline evidence
is in `scratch/filing-bundle-work/legacy-exhibit-baseline.json`.
It does not pin a character-count threshold;
the upstream parser can change. Live PASS without reproducing the old failure
does not establish a historical root cause or a historical bug fix.

## Verify

```bash
tools/marketdata/.venv/bin/python tools/marketdata/smoke_test.py
```

## MCP Server

`friday-marketdata-mcp` — MCP server (thin gateway) ที่ห่อ logic เดียวกับ CLI (`core.py`) เพื่อให้
orchestrator/เอเจนต์เรียกเครื่องมือ market-data **โดยตรงผ่าน MCP** (ได้ structured JSON + metadata
source/tier/as-of ทุกครั้ง) แทนการ parse stdout ของ CLI.

- **ไฟล์เซิร์ฟเวอร์:** [mcp_server.py](mcp_server.py) · แกนดึงข้อมูลร่วม (CLI ใช้ตัวเดียวกัน): [core.py](core.py)
- **Transport:** stdio · **Runtime:** ต้องเป็น venv 3.12 ของชุดนี้เท่านั้น

### วิธีรัน (standalone)

```bash
# รันเซิร์ฟเวอร์ตรง ๆ (ปกติ MCP client เป็นคนสตาร์ทให้)
__FRIDAY_ROOT__/tools/marketdata/.venv/bin/python \
  __FRIDAY_ROOT__/tools/marketdata/mcp_server.py
```

### Tools ที่ expose (11)

| tool | แหล่ง/ชั้น | subcommand (CLI) | หมายเหตุ |
|---|---|---|---|
| `health_check` | — | — | ตรวจ interpreter/CLI/deps/EDGAR identity + การมี key ใน Keychain (bool, ไม่เผยค่า) |
| `get_price_history` | yfinance (3) | `price` | OHLCV เต็ม US+ไทย; `market` = US\|TH\|AUTO (TH→เติม `.BK`) |
| `get_financials` | EDGAR (1) | `financials` | งบดิบ; `period` annual\|quarterly; v1 EDGAR-only (`fallback_used=false`). แต่ละแถวมี `concept` (XBRL tag) คู่กับ `line_item` — **ใช้ `concept` แยกแถวที่ label ซ้ำกัน** (EPS basic/diluted ใช้ label เดียวกันว่า `Earnings Per Share (Derived)`). ⚠️ `concept` **ไม่ใช่คีย์ที่ไม่ซ้ำ**: บนเส้นทาง `filing-xbrl` ตาราง XBRL เอาแถวยอดรวมมาแสดงซ้ำได้ (TSM: `ifrs-full_ProfitLoss` เคยโผล่ 2 รอบค่าเท่ากันเป๊ะ) — ตั้งแต่ 2026-08-26 ระบบตัดแถวที่ซ้ำทั้ง concept/label/ค่าทุกงวดออกให้แล้ว แต่อย่าถือว่า `concept` เป็น primary key ในการรวมยอดเอง. metadata มี `filing_form` + `latest_period`: ที่มาเลือกจากฉบับที่ยื่นล่าสุดในชุดฟอร์มที่ป้อนข้อมูลงวดนั้นจริง (quarterly รวม 10-K เพราะไตรมาสสุดท้ายของปีบัญชีถูก derive จากงบปี; FPI ใช้ 20-F/40-F) — ถ้า `latest_period` เก่ากว่า `filing_date` มาก แปลว่า XBRL ต้นทางยังไม่อัปเดต. **FPI/ข้อมูลค้าง:** ถ้าฉบับล่าสุดเป็น 20-F/40-F หรือ company-facts เก่ากว่างวดของฉบับที่ยื่น จะสลับไปอ่าน **XBRL ของ filing ฉบับนั้นตรง ๆ** (`data_path="filing-xbrl"`) ซึ่งได้งวดล่าสุด + **สกุลเงินเดียว** + label ที่บริษัทตั้งเอง; ทุกครั้งมี `currency` ใน metadata (TSM=TWD · SAP=EUR · US=USD) — ตัวเลข FPI ไม่ใช่ USD อย่าเอาไปเทียบตรง ๆ ต้องแปลงพร้อมติด as-of FX |
| `get_ratios` | FMP stable/ (2) | `ratios` | ต้องมี `fmp-api` ใน Keychain |
| `get_insider_transactions` | EDGAR (1) | `insider` | Form 4; value คำนวณด้วย `Decimal` เมื่อ filing ไม่ระบุ |
| `get_ownership` | EDGAR (1) | `ownership` | SC 13D/G; ชื่อผู้ถือดึงได้ แต่ %/หุ้นมักเป็น `null` กับ filing เก่า → ดู `url` |
| `get_macro_series` | FRED (1) | `macro` | ต้องมี `fred-api`; เช่น DGS10, CPIAUCSL, FEDFUNDS, GDP. default คืน 250 แถวล่าสุด (กัน payload บวม) — ใส่ `start`/`end` เจาะช่วง หรือ `limit=0` ดึงเต็ม; transient error ฝั่ง FRED retry 3 ครั้งอัตโนมัติ |
| `get_estimates` | FMP stable/ (3, ธง) | `estimates` | best-effort; ไม่มีข้อมูล → `note` ไม่ใช่ error |
| `get_universe` | Nasdaq screener (3, ธง) | `universe` | list หุ้น US (NYSE/NASDAQ/AMEX) ตาม cap band + sector; taxonomy = Nasdaq (`Finance`/`Real Estate` ≠ GICS); ไม่บังคับกำไรบวก → กรอง NI>0 เอง; ไม่ใช้ key |
| `get_filings` | EDGAR (1) | `filings` | ลิสต์ filing ทุกฟอร์ม (`8-K`, `DEF 14A`, `10-K`, `10-Q`, `20-F`, `6-K` …) — **metadata เท่านั้น** payload เบา. `detail` **default `false`**; `true` = เติม item code ของ 8-K (`Item 2.02` = ประกาศผลประกอบการ) + รายการ exhibit แต่ต้องโหลด filing ทีละฉบับ **~1.2–2.5 วิ/ฉบับ** (ดูตารางต้นทุนล่าง) |
| `get_filing_text` | EDGAR (1) | `filing-text` | **เนื้อข้อความจริง** 3 ระดับ: `exhibit` (`EX-99.1` = ข่าว earnings ที่แนบกับ 8-K) → `section` (ชื่อต่างกันตามฟอร์ม ดูตารางล่าง) → ทั้งฉบับ; ตัดที่ `max_chars` เสมอ (default 20k, เพดาน 100k) + คืน `has_more`/`next_offset` ให้อ่านต่อเป็นหน้า |

US-only ทุก tool ยกเว้น `price` (US+ไทย); ticker ไทยใน tool US-only → error `UNSUPPORTED_MARKET`.
**หุ้นสหรัฐคลาสรอง (`BRK.B` · `BF.B`) ใช้ได้ปกติ** — "ไม่ใช่ US" ตัดสินจาก suffix ตลาดจริง (`.BK` `.HK`
`.T` …) ไม่ใช่จาก "มีจุด"; ระบบแปลงเป็นรูปขีดกลาง (`BRK-B`) ให้เอง เพราะวัดจริงแล้ว EDGAR รับทั้งสองรูป
แต่ **yfinance รับเฉพาะขีดกลาง** และ Nasdaq screener คืนมาเป็น `BRK/B` ซึ่งไม่มีเจ้าไหนรับ (แก้ 2026-08-26).
`get_universe` = US screener (exchange NYSE/NASDAQ/AMEX), `us_only=true` default.

#### ต้นทุนเวลาของ `get_filings` (วัดจริง แคชเปล่า)

| ก้อน | เมื่อไหร่ | เวลา |
|---|---|---|
| โหลดสารบัญ filing ของบริษัท | **ครั้งเดียวต่อบริษัทต่อโปรเซส** — เกิดเสมอไม่ว่า `detail` เปิดหรือปิด | ~1–13 วิ (WFC 3.7 · GS 13.1); เรียกซ้ำบริษัทเดิม ~1 วิ |
| อ่าน metadata (`detail=false`) | หลังก้อนแรก | 0.03 วิ / 20 ฉบับ — แทบไม่มีต้นทุน |
| `detail=true` | ดาวน์โหลด filing **ทีละฉบับ** | ~1.2–2.5 วิ/ฉบับ (IBM 8-K 20 ฉบับ = +23.1 วิ) |

> `limit=100` พร้อม `detail=true` ≈ **2–4 นาที** เสี่ยง client timeout — เปิด `detail` คู่กับ `limit` น้อย ๆ เท่านั้น

#### ชื่อ `section` ต่างกันตามฟอร์ม (ใส่ผิด → `INVALID_INPUT` พร้อมรายการที่มีจริง)

| ฟอร์ม | รูปแบบชื่อ | ตัวอย่างที่ใช้บ่อย |
|---|---|---|
| `10-K` | `Item <n>` | `Item 1A` ความเสี่ยง · `Item 7` MD&A · `Item 8` งบ |
| `10-Q` | **ต้องมี `Part` นำหน้า** | `Part I, Item 2` MD&A · `Part II, Item 1A` ความเสี่ยง · `Part I, Item 1` งบ |
| `20-F` | `Item <n>` | `Item 3` ปัจจัยเสี่ยง/ข้อมูลสำคัญ |
| `DEF 14A` | **ไม่แบ่ง section** | เรียกโดยไม่ใส่ `section` แล้วไล่ `offset` |

> **⚠️ filing ใหญ่กว่าที่คิดมาก** — AAPL: DEF 14A ~357k · 10-K ~261k · 10-Q ~123k ตัวอักษร;
> TSM 20-F = **~1.02 ล้านตัวอักษร** (ที่ `max_chars` default 20k = 51 หน้า)
> `get_filing_text` จึงบังคับแบ่งหน้าเสมอ ห้ามตั้ง `max_chars` สูงสุดโดยไม่จำเป็น จะกิน context จนหมด
> **วิธีที่ถูก:** ระบุ `section`/`exhibit` ให้แคบ (Item 1A ของ 10-K = 68k เทียบทั้งฉบับ 261k → ประหยัด 74%)
> ประหยัดกว่าการไล่ `offset` ทั้งฉบับมาก; หา accession ที่ต้องการก่อนด้วย `get_filings` (เบา ~230 ตัวอักษร/ฉบับ)
>
> **WebFetch ใช้แทนไม่ได้** — SEC ตอบ `HTTP 403` ถ้าไม่ติด User-Agent ที่มีอีเมลติดต่อ (ยืนยันด้วย curl:
> ไม่ใส่ UA → 403, ใส่ → 200) และ WebFetch ตั้ง UA เองไม่ได้ · อีกทั้งมันคืน "คำสรุปจากโมเดลเล็ก"
> ไม่ใช่ตัวเลขดิบ ซึ่งตรวจย้อนต้นทางไม่ได้ตาม CLAUDE.md §7

### ต่อกับ MCP client

**`.mcp.json` (โปรเจกต์นี้ — ลงทะเบียนไว้แล้ว) / Claude Desktop / Codex:**

```json
{
  "mcpServers": {
    "friday-marketdata-mcp": {
      "command": "__FRIDAY_ROOT__/tools/marketdata/.venv/bin/python",
      "args": ["__FRIDAY_ROOT__/tools/marketdata/mcp_server.py"]
    }
  }
}
```

### Smoke test

```bash
# ทดสอบ tools ผ่าน core + import server (แยกประเภท fail: code/environment/provider/missing-secret)
tools/marketdata/.venv/bin/python tools/marketdata/mcp_smoke_test.py
```

### Security / source-tier

- API key อ่านจาก **macOS Keychain เท่านั้น** — ไม่ hardcode/print/log/ใส่ใน response; error ถูก sanitize (redact `apikey`)
- traceback แสดงเฉพาะเมื่อ env `MARKETDATA_MCP_DEBUG=1`
- stdio ใช้ stdout เป็นช่อง protocol → `core.py` ไม่ print + เซิร์ฟเวอร์ redirect stdout→stderr กัน library print หลง
- ทุก response แนบ metadata `source` / `source_tier` / `as_of` (officialness tiers เดียวกับ CLI: EDGAR/FRED=1, FMP=2, yfinance/AV=3)
- ทุก tool เป็น **read-only** (annotated: readOnly/idempotent/non-destructive — ไม่แก้/ลบข้อมูล) และทุก response คืน **`structuredContent`** (JSON มีโครงสร้าง machine-readable — client อ่านตรงได้ ไม่ต้อง parse ข้อความเอง)
