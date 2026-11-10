# ชุดทดสอบ Option B ของ `tommun_check.py`

## Active contract (แทนที่ expected results เก่าด้านล่าง)

- `good.md` คือ canonical positive สมมติ: CAPM-only, book weights 33.3333/0/66.6667%, accrual k_d 3.63636%, book WACC 7.64%, latest spread 9.21 จุด
- `cases.json` เป็น manifest จริง: แยก active positive, generated unittest cases และ **LEGACY NEGATIVE** ทุกไฟล์เก่านอกจาก good.md
- `should_pass-*` ทั้งสามชื่อเป็นชื่อประวัติศาสตร์เท่านั้น: **ปัจจุบันต้อง FAIL** เพราะไม่มี audit schema และใช้ k_e เฉลี่ย ห้ามใช้ชื่อไฟล์เดาว่าต้องผ่าน
- ไม่ rename/regenerate/edit legacy fixtures; baseline exits/failures และ rules เก็บใน snapshot ที่ cases.json อ้าง
- negative/positive ใหม่สร้าง in-memory หรือ tempfile ใต้ scratch และ cleanup อัตโนมัติ; assert semantic rule ID โดยตรง

```bash
PYTHONDONTWRITEBYTECODE=1 .venv-utils/bin/python -m unittest -v tools.memocheck.test_tommun_semantics
PYTHONDONTWRITEBYTECODE=1 .venv-utils/bin/python tools/tommun_check.py scratch/tommun-check-fixtures/good.md
PYTHONDONTWRITEBYTECODE=1 .venv-utils/bin/python tools/tommun_check.py --rules
```

### Schema §5 (case-sensitive headers)

`### AUDIT ANNUAL`:
`FY | pretax | tax_provision | ETR | statutory | T_used | EBIT | D_begin | P_begin | E_begin | leases_begin | D_end | P_end | E_end | leases_end | IC_avg | NOPAT | ROIC | source | tax_source`

`### AUDIT WACC`: `field | value | source | unit | as_of | coverage`;
fields `FY D P E D_avg interest_expense T_used Rf industry_beta ERP k_e k_p w_d w_p w_e k_d kd_lower kd_upper WACC_low WACC_high spread_low spread_high flag_low flag_high book_wacc spread flag choice debt_coverage_amount`.

`### AUDIT CASH`: `FY | cash | IC_avg | NOPAT | cash_IC_pct | direction | explanation | source`.
`direction/explanation` คู่ canonical: `lower_positive/กด ROIC บวกให้ต่ำลง`, `less_negative/ทำให้ ROIC ติดลบน้อยลง`, `unchanged/ROIC ไม่เปลี่ยน`, `N/A/ไม่สรุปทิศทาง`.

Missing interest และมี supported bound ต้องมี `### AUDIT DEBT`: `instrument | balance | effective_rate | source` ครบทุก tranche, sum balance=D;
coverage ของ kd_upper = `all interest-bearing debt excluding leases`. Endpoint `flag_low` ผูก WACC_low (=flag spread_high), `flag_high` ผูก WACC_high (=flag spread_low).
ธงเหมือนกันเลือก high; ต่างกัน/ไม่มี supported upper → book_wacc/spread `[ข้อมูลไม่พอ]`, flag/choice `N/A`.

หน่วย money/book balances USD million (หรือหน่วยเดียวกันตาม memo), rates/weights/ROIC percent, beta dimensionless, as_of ISO date.
Rf source FRED DGS10 tier1; industry_beta/ERP Damodaran `[tier3]`; beta coverage `Industry group: <ชื่ออุตสาหกรรม>`;
FRED standalone citation เช่น `[FRED DGS10, tier1, as_of 2025-10-31]` ไม่ใช่ filing และไม่ต้องมี SEC Item.
statutory ต้อง official tax note อ้าง FY ของแถว, ห้าม default21. ข้อมูลตัวเลขต้อง Decimal finite ทั้งช่อง; NA ตัวเลข = `[ข้อมูลไม่พอ]` เท่านั้น.
เมื่อ value NA (เช่น E<=0 gate) source/as_of เป็น N/A ได้ ไม่ต้องดึง CAPM หรือแต่งวันที่; ยังต้องระบุ unit และ coverage/blocker. P>0 แต่ k_p ไม่เปิดเผย → dependent WACC/spread NA ไม่เดาต้นทุน preferred.

Checker ตรวจ arithmetic/provenance syntax ไม่ได้พิสูจน์ว่า filing/series มีตัวเลขนั้นจริง ต้อง manual source review.
Parent regression เพิ่มการทดสอบขอบ spread 0/+5, debt upper-bound rounding ก่อนคิดธง, missing opening balances,
unknown pretax ไม่ auto-fallback, official preferred-rate evidence และคง exact WACC เมื่อเฉพาะ ROIC ขาด.
YAML spread รับ `+X.XX จุด` ตาม native spec; numeric audit cells ยัง strict ไม่รับข้อความหรือ NaN.
Native guard ครอบ builtins.open/io.open/os.open ใน direct checker และสแกน package ไม่ให้มี compatibility references/symlinks;
CLI parity ทดสอบแยก ไม่อ้างว่า guard ดัก OS syscall หรือ filesystem access ทุกชนิดใน subprocess.
Production Tommun เดิมถือ legacy schema ไม่แก้ไฟล์จริง; Tony/Rob/Adam/Damon เทียบทั้ง exits/failures และ --rules กับ baseline เดิม ไม่ซ่อม pre-existing failures.

## ARCHIVED documentation — ไม่ใช่ expected results ปัจจุบัน

ไฟล์ในนี้เป็น **เมโมสมมติ** — บริษัท `FAKE / Fixture Industries, Inc.` ไม่มีอยู่จริง
ตัวเลขทุกตัวแต่งขึ้นให้ **ผูกกันทางคณิตศาสตร์** เพื่อให้เครื่องตรวจคิดซ้ำได้จริง
**ห้ามอ้างอิงตัวเลขในนี้เป็นข้อมูลบริษัทใด ๆ**

รันทั้งชุด:

```bash
for f in scratch/tommun-check-fixtures/*.md; do
  printf '%-28s ' "$(basename $f)"
  __FRIDAY_ROOT__/.venv-utils/bin/python tools/tommun_check.py "$f" >/dev/null 2>&1 \
    && echo PASS || echo FAIL
done
```

| ไฟล์ | ต้องได้ | กฎที่ทดสอบ |
|---|---|---|
| `good.md` | **PASS** | โครงครบทุกข้อ — ใช้เป็นตัวอย่างรูปแบบได้ด้วย |
| `should_pass-no9opinion.md` | **PASS** | `2b-opinion` — §9 PLAIN-LANGUAGE ไม่มี `(อนุมาน:)`/`(ความเห็น:)` ก็ต้องผ่าน (แก้ `opinion_sections` เป็น (0,8) เมื่อ 2026-09-01) |
| `bad-noinference.md` | FAIL | `2b-opinion` — §3 ไม่มีบรรทัด `(อนุมาน: ...)` |
| `bad-verdict.md` | FAIL | `3-verdict` — มีคำแนะนำลงทุนใน §9 (จับได้ 2 คำ) |
| `bad-section.md` | FAIL | `2-sections` — ชื่อ §6 ไม่ตรงสเปก |
| `bad-yaml-price.md` | FAIL | `1-yaml` — มีฟิลด์ `price` ที่ทอมมุนห้ามมี |
| `bad-math.md` | FAIL | `8-recompute` — ROIC เขียน 21.00% แต่ 16,000 ÷ 95,000 = 16.84% |
| `bad-deriv.md` | FAIL | `8-recompute` — นิพจน์ `(=20,000×0.90)` ไม่ตรงกับ 16,000 ที่เขียนนำหน้า |
| `bad-noassumptiontable.md` | FAIL | `7-appendix` + `9-assumption` — ตัดตารางสมมติฐานออก |
| `bad-assumption.md` | FAIL | `9-assumption` — `[สมมติฐาน: ...]` 4 จุด แต่ตารางมี 3 แถว |
| `bad-nocashline.md` | FAIL | `2c-required-line` — ตัดบรรทัดสัดส่วนเงินสด **เทียบสินทรัพย์รวม** ใน §5 ออก (ยังมีบรรทัดเทียบ IC อยู่ จึงโดนกฎเดียว) |
| `bad-noicline.md` | FAIL | `2c-required-line` — ตัดบรรทัดสัดส่วนเงินสด **เทียบ IC** ใน §5 ออก (เพิ่ม 2026-09-03) |
| `bad-nobridge.md` | FAIL | `2c-required-line` — ตัดบล็อกสะพาน NI → OCF ใน §3 ออก (เพิ่ม 2026-09-03) |
| `bad-pe.md` | FAIL | `3b-forbidden` — มีคำว่า P/E ใน §8 (เพิ่ม 2026-09-23) |
| `should_pass-pe-in-appendix.md` | **PASS** | `3b-forbidden` — คำว่า P/E / EV/EBITDA ใน §10 ได้รับยกเว้น |
| `bad-noflag.md` | FAIL | `2c-required-line` — ตัดบรรทัด `ธง ROIC เทียบ book WACC:` ใน §8 ออก |
| `bad-flag-enum.md` | FAIL | `1-yaml` — `roic_wacc_flag: ดีมาก` นอกชุดที่ยอมรับ |
| `bad-nowacc-yaml.md` | FAIL | `1-yaml` — ตัดฟิลด์ `book_wacc` ออก |
| `bad-flag-yaml-vs-s8.md` | FAIL | `1-yaml-flag` — YAML `ทำลายมูลค่า` แต่ §8 `สร้างมูลค่าชัด` (สำเนาเมโม NVDA-2026-09-23 · เพิ่มหลัง /scrutinize) |
| `bad-flag-band.md` | FAIL | `1-yaml-flag` — spread +77.98 แต่ธง `ก้ำกึ่ง` ทั้ง YAML และ §8 |
| `bad-flag-spread-number.md` | FAIL | `1-yaml-flag` — บรรทัดธง §8 เขียน spread +70.00 แต่ YAML +77.98 |
| `should_pass-flag-na.md` | **PASS** | `1-yaml-flag` — spread `[ข้อมูลไม่พอ]` คู่กับธง `N/A` |

> **2026-09-23 — book WACC:** ทุกไฟล์ในชุดถูกเติม 3 จุดเหมือนกัน (YAML 3 ฟิลด์ · ตาราง book WACC ใน §5 ·
> บรรทัดธงใน §8) แล้วยิงกฎละข้อเท่าเดิม

**bad-* ทุกไฟล์สร้างจาก `good.md` โดยแก้จุดเดียว** — ถ้าแก้ `good.md` ต้องสร้าง bad-* ใหม่ด้วย

> **2026-09-03 — เพิ่มบรรทัดบังคับสองข้อจากบทเรียนเมโม TER จริง**
> (`outputs/scrutinize/tommun-TER-2026-09-02-audit.md`) `good.md` จึงมีของเพิ่มสามจุด:
> บล็อกสะพาน NI → OCF ใน §3 · บรรทัดเงินสด % ของ IC ใน §5 · แถวรองรับสองแถวใน §10 ตารางคำนวณ
> — bad-* เดิมทั้ง 9 ไฟล์ถูก regenerate ตามแล้ว ทุกไฟล์กลับไปยิงกฎละข้อเท่าเดิม
> (ยกเว้น `bad-noassumptiontable` และ `bad-verdict` ที่ยิง 2 ข้อมาแต่ไหนแต่ไร)
>
> **กฎใหม่ทั้งสองข้อเป็น "บรรทัดบังคับ" ไม่ใช่การพิสูจน์เนื้อหา** — เครื่องตรวจดูแค่ว่ามีคำว่า
> "สะพาน"+"OCF" ใน §3 และมี "% ของ invested capital" ใน §5 · **ยอดสะพานจะปิดจริงหรือไม่
> เครื่องตรวจไม่รู้** (ไม่มีงบในมือ) วินัยข้อนั้นอยู่ในพรอมต์ทอมมุน วินัยตัวเลข ข้อ 7

## ชุดนี้พิสูจน์อะไร และ **ไม่** พิสูจน์อะไร (อ่านก่อนเอาไปอ้าง)

**พิสูจน์:** กฎทุกข้อในเครื่องตรวจทำงานตามที่เขียนไว้ — จับผิดได้ตรงจุด และไม่ FAIL เมโมที่ถูกต้อง

**ไม่พิสูจน์ 3 อย่าง:**

1. **ว่าเมโมจริงจะผ่าน** — `good.md` เขียนโดยคนที่รู้กฎอยู่แล้วและไม่ต้องไปดึงข้อมูลจริง
   เมโมจริงต้องผ่านการอ่าน 10-K + คำนวณเองทุกตัว ซึ่งเป็นคนละงานกัน
2. **ว่าเนื้อหาครบตามพรอมต์** — เครื่องตรวจดูโครงสร้าง ไม่ได้นับว่าตาราง 5 ปีมีครบ 5 ปีจริงไหม
   (และ **นับไม่ได้ด้วย** เพราะ FPI ที่ยื่น 20-F ได้ข้อมูลแค่ 2-3 งวด ซึ่งถูกต้องแล้ว
   — ดูกฎ FPI ในพรอมต์ของทอมมุน)
3. **ว่าน้ำเสียงผ่าน** — เครื่องตรวจจับได้แค่คำแนะนำ *ซื้อ/ขาย/ราคา* ส่วนข้อห้ามอีกสองข้อของทอมมุน
   (§7 ห้ามให้เกรดผู้บริหาร · §8 ห้ามสรุปเรื่อง moat) **ไม่มีกฎรองรับ** ตัวหลักต้องอ่านเอง

> **ขนาดของ `good.md` เทียบเมโมจริง:** ตารางคำนวณในนี้มีราว 100 แถว หลังขยาย §5/§6 เป็น 5 ปี
> (2026-09-01) เมโมจริงที่ทำครบทุก section น่าจะมากกว่านี้อีกเท่าตัว — ใช้ประเมินภาระงานได้คร่าว ๆ
> แต่อย่าถือว่าเท่ากัน

> ชุดของโทนี่อยู่ที่ `scratch/tony-check-fixtures/` — แก้ `tools/memocheck/core.py` เมื่อไหร่
> ต้องรัน **ทั้งสองชุด** เทียบก่อน-หลังเสมอ
