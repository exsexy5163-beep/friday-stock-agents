# CLAUDE.md — friday

## About

`friday` คือทีมนักวิเคราะห์หุ้นสหรัฐด้วย AI ห้าตัวที่ทำงานใน Claude Code งานวิเคราะห์ทั้งหมด
**เพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน** ห้ามตอบว่าควรซื้อหรือขายหุ้นตัวใด

API key อยู่ใน macOS Keychain (account = `friday`, service: `fmp-api` · `alphavantage-api` · `fred-api`)
อีเมลสำหรับ SEC อยู่ที่ `tools/marketdata/.edgar-identity` ทั้งสองอย่างตั้งด้วย `./setup.sh` ห้าม print ค่า key

## Routing Rules

- **AI ต้องไม่เดา** — งานกำกวม → ถามก่อน
- **คำถามเกี่ยวกับบริษัทจดทะเบียนสหรัฐ → เลือกตาม "คำถาม" ไม่ใช่ตามชื่อหุ้น
  — workspace นี้มีเอเจนต์ 5 ตัวคือ `tony` · `tommun` · `rob` · `adam` และ `damon`:**
  ธุรกิจทำอะไร / รายได้มาจากไหน / โมเดลเก็บเงิน / value chain / operating leverage /
  risk factors / "ชำแหละ X" → **tony** ·
  งบการเงิน / กระแสเงินสด / คุณภาพกำไร / ROIC / เงินทุนหมุนเวียน / การจัดสรรเงิน → **tommun** ·
  คูเมือง (moat) / Porter's five forces / อำนาจกำหนดราคา / โครงสร้างอุตสาหกรรม /
  เทียบคู่แข่ง / ขนาดตลาด (TAM) เป็นหัวข้อหลัก → **rob** ·
  ฝีมือและเจตนาผู้บริหาร / ค่าตอบแทน / ธรรมาภิบาล / บอร์ด / รายการเกี่ยวโยง /
  ถือหุ้นเองแค่ไหน (skin in the game) / "ทำได้ตามที่พูดไหม" → **adam** ·
  มูลค่าที่แท้จริง (intrinsic value) / ราคาถูกแพงเทียบมูลค่า / DCF / margin of safety /
  reverse DCF / scenario · sensitivity ของมูลค่า → **damon** ·
  **"ซื้อดีไหม" ยังปฏิเสธ** — เดมอนรายงาน *ช่องว่างระหว่างราคากับมูลค่า* เป็นข้อเท็จจริง
  ไม่ฟันธงซื้อขาย และไม่มีเอเจนต์ตัวไหนในเวิร์กสเปซนี้ตอบคำถามนั้น
  (**เส้นแบ่งโทนี่ vs ร็อบ = "มองเข้า vs มองออก"** — โทนี่มองอำนาจต่อรองในฐานะชิ้นส่วนหนึ่ง
  ของกลไกหาเงินของบริษัทนี้ (§3 ของเมโมโทนี่) · ร็อบมองแรงกดดันจากโครงสร้างอุตสาหกรรมที่
  กระทำกับบริษัท ตอบได้ด้วย 10-K ใบเดียว → โทนี่ · ต้องเอาคู่แข่งมาวางข้าง ๆ ถึงตอบได้ → ร็อบ)
  (**เส้นแบ่งอดัม vs ทอมมุน = "เจตนา vs คณิต"** — ชนกันจุดเดียวคือการจัดสรรเงิน:
  อดัมถาม *เอาเงินไปทำอะไร ใครได้ประโยชน์* (ซื้อหุ้นคืนตอนราคาสูงระหว่างที่ผู้บริหารขายหุ้น ·
  รายการเกี่ยวโยง · เพิ่มทุนเจือจางรายย่อยตอนวิกฤต) · ทอมมุนถาม *คุ้มทุนไหม* (ROIC / IRR)
  ตัวเลขเดียวกันตอบคนละคำถาม → ถามถึง "คน" = อดัม · ถามถึง "ผลตอบแทนของเงิน" = ทอมมุน)
  (**เส้นแบ่งเดมอน vs ทอมมุน = "อดีต vs อนาคตที่คิดลดกลับมา"** — ทอมมุนอ่านตัวเลขที่
  เกิดขึ้นแล้วในงบ (กำไรเป็นเงินจริงไหม · ROIC ที่ผ่านมาเท่าไร) ใช้ราคาเฉพาะคำนวณ book WACC ไม่สรุปถูก/แพง ·
  เดมอนแปลงอนาคตเป็นมูลค่าวันนี้แล้วเอาราคาตลาดมาวางข้าง ๆ — งบในอดีตเป็นแค่ประตูคุณภาพ
  input ของเขา ไม่ใช่ข้อสรุป → ถามถึง *เลขที่เกิดขึ้นแล้ว* = ทอมมุน · ถามถึง
  *มูลค่าวันนี้เทียบราคา* = เดมอน)
- **หุ้นไทย / ตลาดนอกสหรัฐ → โทนี่ไม่รับ** (MCP คืน `UNSUPPORTED_MARKET`) — อย่าเรียกแล้วปล่อยให้พัง

## Sandbox Folders

| Folder | หน้าที่ | ห้าม |
|---|---|---|
| `scratch/` | ทดลอง throwaway (one-off script, ลอง prompt) | เก็บงาน final ที่นี่ |
| `outputs/` | deliverable ถาวร | ใส่ข้อมูลดิบ |

**Convention ของ memo จาก agent:** `outputs/<ชื่อ agent>/<TICKER>-YYYY-MM-DD.md`
(ชื่อซ้ำในวันเดียวกัน → เติม `-HHMM` กันทับ) · agent ไม่เซฟไฟล์เอง ตัวหลักเป็นคนเซฟ
(ข้อยกเว้นเดียว: เดมอนเขียนไฟล์ร่างเพื่อตรวจตัวเองได้ที่ `scratch/damon-drafts/<TICKER>.md`
— ตัวหลักเป็นคนคัดลอกร่างที่ PASS ไปเซฟใน `outputs/`)

**ธรรมเนียมการส่งมอบของโทนี่ (`tony`) — ตัวหลักทำ 4 ขั้นตามลำดับ:**

1. โทนี่ return เมโมเป็นข้อความ (ไม่เซฟเอง) → ตัวหลักเซฟลง
   `outputs/tony/<TICKER>-YYYY-MM-DD.md` (ซ้ำวันเดียวกันเติม `-HHMM`)
2. รัน `__FRIDAY_ROOT__/.venv-utils/bin/python tools/tony_check.py <ไฟล์>` **ทันที**
   (ใช้ `.venv-utils` เพราะ `tony_check.py` ต้องใช้ PyYAML ซึ่งไม่ได้อยู่ใน `.venv` แกน)
3. **ไม่ PASS ห้ามส่งให้ผู้ใช้** — ส่งเหตุผล FAIL กลับให้โทนี่แก้แล้วตรวจซ้ำ
4. ใน chat แสดงแค่ **YAML header + §7 TONY'S TAKE + §8 PLAIN-LANGUAGE SUMMARY + path ที่เซฟ**
   (ไม่ต้องแปะเมโมเต็ม)

**ธรรมเนียมการส่งมอบของทอมมุน (`tommun`) — ตัวหลักทำ 4 ขั้นเหมือนกัน คนละไฟล์คนละเครื่องตรวจ:**

1. ทอมมุน return เมโมเป็นข้อความ (ไม่เซฟเอง) → ตัวหลักเซฟลง
   `outputs/tommun/<TICKER>-YYYY-MM-DD.md` (ซ้ำวันเดียวกันเติม `-HHMM`)
2. รัน `__FRIDAY_ROOT__/.venv-utils/bin/python tools/tommun_check.py <ไฟล์>` **ทันที**
3. **ไม่ PASS ห้ามส่งให้ผู้ใช้** — ส่งเหตุผล FAIL กลับให้ทอมมุนแก้แล้วตรวจซ้ำ
4. ใน chat แสดงแค่ **YAML header + §8 TOMMUN'S VERDICT + §9 PLAIN-LANGUAGE SUMMARY + path ที่เซฟ**
   (ไม่ต้องแปะเมโมเต็ม)

**ธรรมเนียมการส่งมอบของร็อบ (`rob`) — ตัวหลักทำ 4 ขั้นเหมือนกัน คนละไฟล์คนละเครื่องตรวจ:**

1. ร็อบ return เมโมเป็นข้อความ (ไม่เซฟเอง) → ตัวหลักเซฟลง
   `outputs/rob/<TICKER>-YYYY-MM-DD.md` (ซ้ำวันเดียวกันเติม `-HHMM`)
2. รัน `__FRIDAY_ROOT__/.venv-utils/bin/python tools/rob_check.py <ไฟล์>` **ทันที**
3. **ไม่ PASS ห้ามส่งให้ผู้ใช้** — ส่งเหตุผล FAIL กลับให้ร็อบแก้แล้วตรวจซ้ำ
4. ใน chat แสดงแค่ **YAML header + §7 ROB'S VERDICT + §8 PLAIN-LANGUAGE SUMMARY + path ที่เซฟ**
   (ไม่ต้องแปะเมโมเต็ม)

**ธรรมเนียมการส่งมอบของอดัม (`adam`) — ตัวหลักทำ 4 ขั้นเหมือนกัน คนละไฟล์คนละเครื่องตรวจ:**

1. อดัม return เมโมเป็นข้อความ (ไม่เซฟเอง) → ตัวหลักเซฟลง
   `outputs/adam/<TICKER>-YYYY-MM-DD.md` (ซ้ำวันเดียวกันเติม `-HHMM`)
2. รัน `__FRIDAY_ROOT__/.venv-utils/bin/python tools/adam_check.py <ไฟล์>` **ทันที**
3. **ไม่ PASS ห้ามส่งให้ผู้ใช้** — ส่งเหตุผล FAIL กลับให้อดัมแก้แล้วตรวจซ้ำ
4. ใน chat แสดงแค่ **YAML header + §7 ADAM'S VERDICT + §8 PLAIN-LANGUAGE SUMMARY + path ที่เซฟ**
   (ไม่ต้องแปะเมโมเต็ม)

> **เพิ่มเติมเฉพาะอดัม:** เมโมของอีกสามคนพูดถึง *บริษัท* เมโมของอดัมพูดถึง *คนจริง* —
> PASS จากเครื่องตรวจไม่ได้แปลว่าข้อความปลอดภัย **ตัวหลักต้องอ่าน §7 ด้วยตาทุกครั้ง**
> ว่าข้อกล่าวหาทุกข้อมีหลักฐานอ้างจริง และ Bull ไม่ได้เป็นหุ่นฟาง
> อดัมมีสิทธิ **ยกเลิกงานแล้วรายงานกลับ** ถ้าเปิด DEF 14A ไม่ได้ — นั่นคือพฤติกรรมที่ถูกต้อง
> ไม่ใช่ความล้มเหลว ห้ามสั่งให้เขียนเมโมเต็มทับ

**ธรรมเนียมการส่งมอบของเดมอน (`damon`) — ตัวหลักทำ 4 ขั้นเหมือนกัน คนละไฟล์คนละเครื่องตรวจ:**

1. เดมอน return ใบเสร็จ + `<<<MEMO>>>` + บรรทัดเดียว
   `MEMO-FILE: <path ไฟล์ร่าง> · sha256: <hash>` (ไม่พิมพ์เมโมซ้ำ — แก้ 2026-10-18)
   → ตัวหลักรัน `shasum -a 256` กับไฟล์ร่าง **ต้องตรง hash ที่ส่งมา** (ไม่ตรง = ตีกลับ)
   แล้วคัดลอกไฟล์ร่างไปที่ `outputs/damon/<TICKER>-YYYY-MM-DD.md` (ซ้ำวันเดียวกันเติม `-HHMM`)
   · กรณีเดมอนเขียนร่างไม่ได้แล้วใช้โหมด stdin → หลัง `<<<MEMO>>>` เป็นเมโมเต็ม ให้เซฟข้อความนั้นแบบเดิม
2. รัน `__FRIDAY_ROOT__/.venv-utils/bin/python tools/damon_check.py <ไฟล์>` **ทันที**
   แล้ว **คำนวณ TV → EV → IV ฉาก Base ซ้ำเองด้วย `Decimal`** จากตัวเลขในเมโม — ไม่ตรงระดับปัดเศษ = ส่งกลับ
3. **ไม่ PASS ห้ามส่งให้ผู้ใช้** — ส่งเหตุผล FAIL กลับให้เดมอนแก้แล้วตรวจซ้ำ
4. ใน chat แสดงแค่ **YAML header + §10 DAMON'S VERDICT + §11 PLAIN-LANGUAGE SUMMARY + path ที่เซฟ**
   (ไม่ต้องแปะเมโมเต็ม)

> **เพิ่มเติมเฉพาะเดมอน — เขาเป็นตัวเดียวที่เครื่องตรวจ *ปิด* กฎ `3-verdict` ทั้งข้อ**
> (เมโมประเมินมูลค่าต้องพูดคำว่า *มูลค่าเหมาะสม · upside · discount* เป็นปกติ เปิดกฎไว้จะ FAIL
> ทุกใบ) ตาข่ายแทนคือกฎ `3b-forbidden` ที่จับ **คำสั่งตรง ๆ** (น่าซื้อ · ควรซื้อ · แนะนำถือ ·
> ทยอยซื้อ ฯลฯ — เพิ่ม 2026-10-18) + **บรรทัด DISCLAIMER บังคับใน §11** + วินัยในพรอมต์
> แต่ **ประโยคที่สื่อเป็นนัย** อย่าง "ที่ราคานี้คุ้มมาก" · "หุ้นถูก" **ยัง PASS** เครื่องตรวจ
> → **ตัวหลักต้องอ่าน §10 และ §11 ด้วยตาทุกครั้ง** ว่าไม่มีประโยคไหนกลายเป็นคำแนะนำซื้อขาย
> (§11 เสี่ยงสุด เพราะ *"ถูก/แพง"* ในภาษาคนแทบแปลว่า *"ซื้อ/ขาย"*)
> เดมอนมีสิทธิ **ยกเลิกงานแล้วรายงานกลับ** ถ้าประเมินไม่ได้จริง (FCF ติดลบทุกปี · เพิ่งเข้าตลาด ·
> ข้อมูลไม่พอจนต้องเดา input หลัก) — นั่นคือพฤติกรรมที่ถูกต้อง ไม่ใช่ความล้มเหลว
> **ห้ามสั่งให้เขียนเมโมเต็มทับ และห้ามสั่งให้ปั้นเลขให้ช่องไม่ว่าง**
>
> **ส่วนที่เครื่องตรวจ V29–V32 จับไม่ได้ — ตัวหลักดูด้วยตา** (เครื่องตรวจแค่บรรทัดประกาศกับเลขในบรรทัดนั้น):
> (V29) g/ROIC/WACC ในบรรทัด `ตัวคูณขาออกตามทฤษฎี` ตรงกับ §2/§3/§5 และไม่ได้ใช้การเทียบคู่เดียวกันหนุนสองข้อสรุปที่สวนกัน ·
> (V30) ไม่ได้เขียนเองว่ากฎให้ผลผิดหลักการ แล้วยังเอาผลนั้นเป็นพาดหัว ·
> (V31) วลี *ลด/หัก/ราว X ต่อหุ้น* ที่เครื่องไม่จับ (จับแค่คำว่า "กระทบ") ·
> (V32) ลิสต์ "เรียงตาม…" ที่อยู่ในตาราง

> เครื่องตรวจห้าตัวใช้แกนร่วมที่ `tools/memocheck/` — `tony_check.py` · `tommun_check.py` ·
> `rob_check.py` · `adam_check.py` · `damon_check.py` เป็นเปลือกบาง ๆ ที่ล็อก profile ไว้เท่านั้น
> (ดู [tools/memocheck/README.md](tools/memocheck/README.md))

---

## AI Behavior Rules

### 1. NO MAGIC
ตัวเลข / ชื่อไฟล์ / path ทุกตัวต้อง verify จาก source จริง — ห้ามเดา ห้าม hallucinate
ไม่มีข้อมูล → เขียน `[ยังไม่มีข้อมูล]`

### 2. VERIFY BEFORE DONE
ห้าม claim "เสร็จแล้ว" ก่อนเห็น output / diff ของการเปลี่ยนแปลงจริง
ที่ task completion → แสดงรายชื่อไฟล์ที่ create/update + diff สำคัญ

### 3. R0 / R1 / R2 Reversibility

| Tier | ตัวอย่าง | ต้องทำ |
|---|---|---|
| **R0** (ย้อนไม่ได้) | credentials/Keychain · ลบ `outputs/` ที่ผู้ใช้ยืนยันว่า final | **STOP ถามก่อน** |
| **R1** (ย้อนแพง) | ลบไฟล์ใน `outputs/` · แก้ `CLAUDE.md` / `.mcp.json` · bulk rename | **warn + diff + confirm** |
| **R2** (ถูก) | สร้าง/แก้ไฟล์ใน `scratch/` | **ทำเลย** |

### 7. FINANCIAL DATA SOURCING WATERFALL

ดึง **ข้อมูลทางการเงิน** (งบ · ราคา · market cap · multiples · ratio · segment/KPI · insider · มหภาค)
— **ทั้งตัวหลักและ agent ทุกตัว** — ผ่าน **Market-Data Fetch Toolkit** เรียกได้ 2 ช่องทางที่ห่อ
logic เดียวกัน (`core.py`) แหล่ง/tier เดียวกัน:

- **ช่องทางที่ 1 — MCP tools** (`mcp__friday-marketdata-mcp__*`, 11 ตัว): **ช่องหลัก** — เรียกตรง
  ได้ JSON + metadata (source/tier/as-of) ครบทุก response ไม่ต้อง parse และ **ไม่ติดปัญหา cwd**
- **ช่องทางที่ 2 — CLI** ผ่าน Bash: ได้ provenance header — ช่องสากล ใช้เมื่อ MCP ไม่พร้อม

**ลำดับชั้นความเป็นทางการ (เหมือนกันทั้ง 2 ช่องทาง — `tool` / `subcommand`):**

1. **ทางการ (tier 1)** — SEC EDGAR: `get_financials`/`financials` (งบ US ดิบ) ·
   `get_insider_transactions`/`insider` (Form 4) · `get_ownership`/`ownership` (SC 13D/G) ·
   `get_filings`/`filings` (ลิสต์ filing ทุกฟอร์ม) · `get_filing_text`/`filing-text` (เนื้อเอกสาร) ·
   `get_macro_series`/`macro` (FRED) · company IR / SET·56-1 (ไทย — ดึงมือด้วย WebFetch, ยังไม่มีใน toolkit)
2. **aggregator น่าเชื่อถือ (tier 2, ติดธง)** — FMP `stable/`: `get_ratios`/`ratios` ·
   stockanalysis / macrotrends
3. **รอง/สะดวก (tier 3, ติดธง + verify จุดสำคัญ)** — `get_price_history`/`price` (yfinance; ไทยเติม `.BK`) ·
   `get_estimates`/`estimates` (FMP consensus — ไม่มีแหล่งทางการฟรี) ·
   `get_universe`/`universe` (Nasdaq screener) ·
   `price --source av` (Alpha Vantage สำรอง) · เว็บการเงิน (Bloomberg/Reuters/WSJ/S&P)

**tool ↔ subcommand (11 tool / 10 subcommand):** `get_price_history`↔`price` ·
`get_financials`↔`financials` · `get_ratios`↔`ratios` · `get_insider_transactions`↔`insider` ·
`get_ownership`↔`ownership` · `get_filings`↔`filings` · `get_filing_text`↔`filing-text` ·
`get_macro_series`↔`macro` · `get_estimates`↔`estimates` · `get_universe`↔`universe` ·
`health_check` = **MCP เท่านั้น ไม่มี subcommand ใน CLI**

**ขอบเขต:** `get_price_history`/`price` = US + ไทย; tool/subcommand อื่น = **US เท่านั้น**
(ticker ไทย → `UNSUPPORTED_MARKET`; งบไทยต้องดึงมือจากเว็บ/IR แล้วติดธง)
**หุ้นสหรัฐคลาสรอง (BRK.B · BF.B) ใช้ได้ปกติทุก tool** — ระบบตัดสิน "ไม่ใช่ US" จาก suffix ตลาดจริง
(`.BK` `.HK` `.T` …) ไม่ใช่จาก "มีจุด"; ภายในแปลงเป็นรูปขีดกลาง (`BRK-B`) ให้เอง เพราะ yfinance
รับเฉพาะรูปนั้น (แก้ 2026-08-26 — ก่อนหน้านี้ถูกปฏิเสธผิด ๆ ว่าไม่ใช่หุ้น US)

**ทุกตัวเลขติด as-of date + ที่มา (tier)** · ratio คำนวณเองด้วย `Decimal` (§8)

**FPI (Foreign Private Issuer — บริษัทต่างชาติจดในตลาดสหรัฐ):** ยื่น **20-F/40-F + 6-K** แทน 10-K/10-Q
→ รายปียังเป็น tier 1 ปกติ แต่รายไตรมาส (6-K) / insider (Form 4) / proxy (DEF 14A) อาจไม่มีหรือไม่
machine-readable → **ติดธง**; งบมักเป็น IFRS ไม่ใช่ US GAAP (XBRL tag คนละชุด, สกุลเงินอาจไม่ใช่ USD
→ แปลง + ติด as-of FX)

**เอกสาร toolkit เต็ม:** [tools/marketdata/README.md](tools/marketdata/README.md) (§MCP Server)

> **⚠️ cwd caveat (เฉพาะช่องทาง CLI):** subagent Bash reset cwd กลับ root หลังทุก call →
> **เรียก CLI ด้วย absolute path เสมอ**
> `__FRIDAY_ROOT__/tools/marketdata/marketdata <subcommand>`
> relative path จะได้ `no such file` แล้วเอเจนต์เข้าใจผิดว่า CLI ใช้ไม่ได้ → ข้าม tier-1 ไปเว็บ
> โดยไม่จำเป็น (คุณภาพตกเงียบ ๆ). **MCP tools ไม่ติดปัญหานี้**

### 7b. FILING BUNDLE GATE — ตัวหลักเป็นเจ้าของการดึง เอเจนต์เป็นผู้อ่าน

ใช้เมื่อจะให้เอเจนต์ห้าตัว (`tony` · `tommun` · `rob` · `adam` · `damon`) อ่าน **เนื้อ section
ของ filing SEC** — ไม่ใช้กับ XBRL · ราคา · estimates · Form 4 · ownership (พวกนั้นเรียก MCP ตรงตาม §7)

**เครื่องมือคือของกลางชุดเดียว:**

```bash
# ดึง section ครบทั้งชุดลงไฟล์ local — --section ระบุซ้ำได้ ห้ามรวมด้วย comma
__FRIDAY_ROOT__/tools/marketdata/marketdata filing-bundle ISRG \
  --form 10-K --accession 0001035267-25-000017 \
  --section "Item 1A" --section "Item 7"
```

**ตัวหลักทำ 7 ขั้นตามลำดับ ห้ามข้าม:**

1. **เขียน source plan ก่อน retrieval** — ticker · form · **exact accession** (จาก `get_filings`
   ไม่ใช่ "ฉบับล่าสุด" ลอย ๆ) · **required sections** · **optional sections** · non-bundle sources
   → แยก required/optional จาก **คำถามและบทบาทของเอเจนต์** ตามแผนแหล่งมาตรฐานในไฟล์เอเจนต์แต่ละตัว
   **ห้ามลด required เป็น optional หลังดึงล้มเพื่อให้ผ่าน**
   - **เหตุการณ์หลัง filing — บังคับทุกงาน** (เพิ่ม 2026-10-09 จากบทเรียน BWXT: เมโมห้าใบยืนบน 10-K
     ที่ยื่นมา 7 เดือน ไม่มีใบไหนเห็น 8-K ที่ประกาศขายธุรกิจ — ข่าวอยู่ใน EX-99.1 ของ Item 2.02 ไม่มี 8-K แยก)
     เรียก `get_filings form=8-K start=<filed ของ annual report หลัก +1 วัน> detail=true limit=10` ครั้งเดียว
     (FPI: `form=6-K limit=20`) · ได้ครบเท่า limit = ระบุใน handoff ว่ารายการอาจไม่ครบ ·
     ไม่มีฉบับใดในช่วง = ระบุ `ไม่มี 8-K` · ติดป้าย `ต้องอ่าน`:
     (ก) EX-99.1 ของ **Item 2.02 ฉบับล่าสุด — เสมอ** ·
     (ข) item 1.01 · 1.02 · 2.01 · 2.03 · 2.05 · 2.06 · 4.02 ·
     (ค) 7.01/8.01 และ 6-K ที่แนบ EX-99.x → ดึง `get_filing_text … max_chars=500` เป็นหัวข่าว
     แล้วติดป้ายถ้าเป็นดีล / ขายกิจการ / guidance / ผลประกอบการ (ชื่อ exhibit บอกเนื้อหาไม่ได้ ต้องเปิดดู) ·
     item อื่น (5.02 · 5.07 …) ใส่ในตารางโดยไม่ติดป้าย ให้เอเจนต์เลือกตามบทบาท
2. **ตรวจ target เดิมก่อนเรียก helper** ที่ `scratch/filing-bundles/<TICKER>/<ACCESSION>/`
   - ไม่มี → เรียก CLI ได้เลย
   - มีและ COMPLETE → **verify ด้วย section set ทั้งหมดใน manifest** แล้วเช็คว่า required ⊆ set นั้น
     ครบ → **reuse แบบ read-only** · ขาด → **ห้ามเรียกซ้ำจนติด `BUNDLE_EXISTS`** ไปใช้ official fallback
   - เสีย / identity ผิด / `.pending-*` / มี `.<accession>.lock` ค้าง / อยู่ใต้ `.failed/`
     → **ห้ามใช้ ห้ามทับ ห้ามลบ ห้ามย้าย ห้าม merge** (v1 ไม่มี `--force` โดยตั้งใจ)
     การย้าย/ลบของเดิมเป็น **การตัดสินใจของผู้ใช้** ไม่ใช่ของ AI
3. **เรียก CLI ครั้งเดียว** — exit 0 = `COMPLETE` เท่านั้น · exit 2 = `FAILED`
   **ห้ามใส่ retry loop ซ้อน** helper มี fresh-worker retry ในตัวแล้ว (2 ครั้งต่อ section)
4. **verify ของจริง** — เปิด `manifest.json` ตรวจ `status`/`failures`/identity/`source_tier`,
   required-section coverage, relative path ใต้ `sections/`, จำนวนตัวอักษร Unicode เทียบ
   `chars` และ `metadata.total_chars`, และ `shasum -a 256` เทียบ `sha256`
5. **สุ่ม probe offsets 3 จุดกลางไฟล์** เก็บข้อความจริงกับ tail ไว้ที่ตัวหลัก
   **ห้ามใส่คำตอบลงในพรอมต์** — จะใช้เทียบใบเสร็จของเอเจนต์
   · exhibit หลัง filing ที่ติดป้าย: ดึงเต็มด้วย `get_filing_text` (accession + exhibit เป๊ะ) แล้วสุ่ม
   **1 probe + tail ต่อฉบับ** (offset นับในข้อความที่ tool คืน) — เทียบกับบรรทัด `post-*` ในใบเสร็จ
6. **เรียกเอเจนต์ด้วย Agent tool แบบ native** (`subagent_type: "tony"` ฯลฯ) ส่ง handoff:
   source plan · สถานะ retrieval · path ของ manifest และไฟล์ required ทุกอันพร้อม `chars`/`sha256` ·
   scope ของ fallback ถ้ามี · **probe offsets** · คำสั่งให้ส่ง Reading Coverage Receipt กลับมา ·
   **ตาราง 8-K หลัง filing** (วันที่ · item · accession · exhibit · หัวข่าว · ป้าย `ต้องอ่าน`)
7. **ตัดใบเสร็จออกก่อนเซฟ** — เอเจนต์ส่ง `<<<READING-COVERAGE-RECEIPT>>> … <<<END-RECEIPT>>>`
   แล้วตามด้วย `<<<MEMO>>>` · ตัวหลักเทียบ probe/tail กับของจริง **ไม่ตรง = ไม่ผ่าน ส่งกลับให้อ่านใหม่**
   ตรงแล้วจึงเซฟ **เฉพาะส่วนหลัง `<<<MEMO>>>`** ลง `outputs/<agent>/…` แล้วรันเครื่องตรวจตามธรรมเนียมเดิม
   (เดมอน: ส่วนหลัง `<<<MEMO>>>` เป็นบรรทัด `MEMO-FILE:` → ใช้ขั้นที่ 1 ของธรรมเนียมเดมอนแทน)
   - **marker ผิดรูป = ตีกลับทั้งงาน** ห้ามเดาว่าเมโมเริ่มตรงไหน (ทดสอบ 2026-09-08 พบ 3 ใน 5 ตัว
     เขียนใบเสร็จเป็นฟอร์แมตของตัวเองเมื่อไม่มีการบังคับ)
   - **ตรวจบรรทัด `method:` ทุกครั้ง** — `reading_coverage: COMPLETE` รับได้เฉพาะคู่กับ
     `method: read-windows` เท่านั้น · `machine-scan+spot-read` หรือ `mixed` ต้องเป็น `PARTIAL`
     **ใบเสร็จที่เขียน 100% แต่ method ไม่ใช่ `read-windows` = ใบเสร็จผิด ส่งกลับ**
   - **หลักฐานประกอบที่ตัวหลักดูได้ฟรี:** token ที่ subagent ใช้ — อ่านไฟล์ระดับ 6,000 บรรทัดจริง
     กินราว 300k token; ถ้าใบเสร็จเคลม 100% แต่ใช้ไปไม่ถึงหนึ่งในสาม ให้สงสัยไว้ก่อนแล้วถามกลับ

**เส้นแบ่งความรับผิดชอบ (แก้ข้อขัดกันของกฎ "เอเจนต์ไม่เซฟไฟล์เอง"):**
scratch artifact ทุกชิ้นที่ helper สร้าง **เป็นของตัวหลัก** · เอเจนต์ **ตรวจและอ่านอย่างเดียว**
ห้ามเรียก `filing-bundle` ห้ามแตะ `scratch/` และยังห้ามเซฟเมโมเองเหมือนเดิม
(เอเจนต์มี `Bash` ในมือ จึงต้องเขียนข้อห้ามนี้ไว้ให้ชัด)
**ข้อยกเว้นเดียว:** เดมอนเขียน/แก้ไฟล์ร่างของตัวเองที่ `scratch/damon-drafts/<TICKER>.md` ได้
ด้วย `cat > … <<'EOF'` และ `tools/damon_draft_edit.py` (แทนข้อความตรงตัว) เท่านั้น
— **ห้าม `sed -i`** เพราะ `[ ]` ในป้ายที่มาทำให้แทนผิดที่โดยยัง exit 0 (ทดสอบ 2026-10-18) ·
ร่างที่ PASS คือฉบับที่ตัวหลักคัดลอกไปเซฟ · `outputs/` ยังเป็นของตัวหลักคนเดียว

**สามสถานะที่ห้ามปนกัน:**

| สถานะ | หมายความว่า | ไม่ได้หมายความว่า |
|---|---|---|
| `COMPLETE` ของ helper | เก็บผลที่ parser คืนมาครบ + ไฟล์ integrity ผ่าน | parser ตัดขอบ section ตรง HTML ต้นฉบับ SEC · เอเจนต์อ่านแล้ว |
| `retrieval complete` | ไฟล์/fallback ครอบ source plan | เอเจนต์อ่านครบ |
| `reading coverage complete` | เอเจนต์อ่านถึงบรรทัดสุดท้ายจริง (มีใบเสร็จ) | โมเดลเข้าใจเนื้อหา |

**`FAILED` · `BUNDLE_EXISTS` · `BUNDLE_LOCKED` · `SECTION_DISCOVERY_FAILED` · `PARSER_ERROR`
= ดึงไม่สำเร็จ ไม่ใช่ "บริษัทไม่เปิดเผย"** — ห้ามแปลงเป็น `[ไม่เปิดเผย]` เด็ดขาด
**required ล้ม** → หยุดข้อสรุปที่พึ่งส่วนนั้น หรือ valid abort ตามกฎเดิมของเอเจนต์ ·
**optional ล้ม** → ระบุเป็นข้อจำกัด ห้ามเขียนว่า "ตรวจแล้ว"

**ฟอร์มที่ helper ไม่รองรับ** (DEF 14A ไม่แบ่ง section · 6-K ที่ parser ไม่ expose ·
40-F ต้อง probe exact accession ก่อน · exhibit) → ใช้ official fallback `get_filing_text`
แบบระบุ accession เป๊ะ อ่านไล่ `next_offset` จน `has_more=false` พร้อมใบเสร็จเหมือนกัน
**ห้ามเรียก fallback ว่า helper COMPLETE**

### 8. CALCULATION LIBRARIES

**interpreter สำหรับงานคำนวณวิเคราะห์ = `__FRIDAY_ROOT__/.venv/bin/python`**
(Python 3.12, มี `numpy` · `scipy` · `mpmath` · `sympy` · `pandas` · `pydantic` — ดู `requirements-calc.txt`)

**กฎบังคับ 2 ข้อ:**
1. **ห้ามใช้ `python3` ของเครื่อง** (`/usr/bin/python3` = 3.9.6 ที่มากับ macOS หมดซัพพอร์ตแล้ว
   ไลบรารีในนั้นอาจหายเมื่ออัปเดต macOS)
2. **ห้ามใช้ `.venv` ของ marketdata มาคำนวณ** — ตัวนั้นมีไว้ดึงข้อมูลอย่างเดียว
   (`tools/marketdata/.venv/bin/python`)

**เลือกไลบรารีตามงาน:**
- **`decimal.Decimal`** (built-in) = **default** สำหรับ financial ratio / margin / % / เงิน / score —
  **ห้ามใช้ `float` แบบมักง่ายกับเลขการเงิน** (ทศนิยมเพี้ยน)
- **`numpy` + `scipy`** — quant / simulation / portfolio optimization / vectorize (Monte Carlo,
  Black-Scholes); float64 ในชั้นนี้ใช้ได้ เป็นเครื่องมือที่ตั้งใจ
- **`mpmath`** — precision สูงผิดปกติ (error เล็กในขั้นแรกขยายในขั้นถัดไป)
- **`sympy`** — derive สูตร / แก้สมการ algebra แบบ exact
- **`pandas`** — จัดตาราง/time series (ไม่ใช่ตัวคำนวณเลขการเงินขั้นสุดท้าย)

**นโยบาย venv — แยกชุดตามหน้าที่ ห้ามปน:**

| venv | ใช้ทำอะไร | interpreter |
|---|---|---|
| `.venv-utils` | เครื่องตรวจเมโม (PyYAML) | `.venv-utils/bin/python` |
| `tools/marketdata/.venv` | ดึงข้อมูล (yfinance · edgartools · fredapi · alpha_vantage · mcp) | `tools/marketdata/.venv/bin/python` |
| `.venv` (root) | คำนวณวิเคราะห์ (5 ไลบรารีแกน + `pydantic` ตรวจห่อสมมติฐาน — ผู้ใช้อนุมัติ 2026-10-29) | `.venv/bin/python` |

**อยากได้ไลบรารีนอก 5 ตัวแกน (เช่น Excel/Word/PPT · matplotlib · PDF · empyrical) →
สร้าง venv ตัวใหม่แยก ห้ามเติมเข้าสองตัวเดิม** (กันสองชุดพองแล้วพังพร้อมกัน)
ข้อยกเว้น: `pydantic` (ผู้ใช้อนุมัติ 2026-10-29)
สร้างด้วย `uv venv --python 3.12 <path>` แล้ว `uv pip install --python <path>/bin/python <libs>`

---

## Hard Rules

- ห้ามตอบ "ซื้อดีไหม" หรือแนะนำซื้อขายหุ้นรายตัว
- commit เฉพาะเมื่อผู้ใช้สั่ง
