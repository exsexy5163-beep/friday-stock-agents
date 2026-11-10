# ชุดทดสอบของ `damon_check.py`

ไฟล์ในนี้เป็น **เมโมสมมติ** — บริษัท `NWSY / Northwind Systems, Inc.` **ไม่มีอยู่จริง**
ตัวเลขทุกตัวแต่งขึ้นให้ **ผูกกันทางคณิตศาสตร์** เพื่อให้เครื่องตรวจคิดซ้ำได้จริง
(ราคา 152.40 · IV 118.00 / 165.00 / 205.00 · WACC 8.46% · มูลค่าถ่วงน้ำหนัก 163.60)

> **ข้อควรระวังเฉพาะชุดนี้:** เดมอนเป็น profile เดียวที่ **ปิดกฎ `3-verdict` ทั้งข้อ**
> ไฟล์ในชุดนี้จึงพูดคำว่า *fair value · upside · undervalued · มูลค่าเหมาะสม* ได้โดยไม่ FAIL
> — นั่นคือพฤติกรรมที่ถูกต้อง ไม่ใช่ช่องโหว่ (ดู `should_pass-valuation-words.md`)
> **สิ่งที่กันการฟันธงซื้อ/ขายจึงเหลือแค่บรรทัด DISCLAIMER ใน §11** กับวินัยในพรอมต์
> ห้ามคัดลอกประโยคใน `§10`/`§11` ของไฟล์เหล่านี้ไปใช้กับบริษัทจริงโดยไม่เปลี่ยนหลักฐาน

รันทั้งชุด:

```bash
# ไล่ตรวจทุกไฟล์ในชุด แล้วพิมพ์ PASS/FAIL ทีละบรรทัด
for f in scratch/damon-check-fixtures/*.md; do
  printf '%-34s ' "$(basename $f)"
  __FRIDAY_ROOT__/.venv-utils/bin/python tools/damon_check.py "$f" >/dev/null 2>&1 \
    && echo PASS || echo FAIL
done
```

| ไฟล์ | ต้องได้ | กฎที่ทดสอบ |
|---|---|---|
| `good.md` | **PASS** | โครงครบทุกข้อ — ใช้เป็นตัวอย่างรูปแบบได้ด้วย |
| `should_pass-valuation-words.md` | **PASS** | `3-verdict` ถูกปิด — `fair value` · `upside` · `downside` · `undervalued` · `มูลค่าเหมาะสม` · `ราคาที่เหมาะสม` ต้องผ่าน |
| `bad-stance-mismatch.md` | FAIL | `1-yaml-stance` — ราคาอยู่ในช่วง IV แต่เขียน `Premium` (เครื่องตรวจคิดซ้ำด้วย `Decimal`) |
| `bad-price-nonnumeric.md` | FAIL | `1-yaml-stance` — `price: "n/a"` แปลงเป็นตัวเลขไม่ได้ |
| `bad-iv-inverted.md` | FAIL | `1-yaml-stance` — `iv_bear` (210.00) มากกว่า `iv_bull` (205.00) ช่วงกลับหัว |
| `bad-stance-enum.md` | FAIL | `1-yaml` — `valuation_stance: Neutral` ไม่อยู่ในสามค่าที่ยอมรับ |
| `bad-method-enum.md` | FAIL | `1-yaml` — `method: DCF` ไม่อยู่ใน `FCFF/FCFE/DDM/NAV` |
| `bad-yaml-nobasis.md` | FAIL | `1-yaml` — `valuation_stance_basis: ""` มีคีย์แต่ค่าว่าง |
| `bad-yaml-forbidden.md` | FAIL | `1-yaml` — มีฟิลด์ `verdict` ที่ห้ามมี |
| `bad-section.md` | FAIL | `2-sections` — `§8 REVERSE DCF` หายไป |
| `bad-opinion.md` | FAIL | `2b-opinion` — §5 ไม่มีบรรทัด `(ความเห็น: ...)` |
| `bad-projection-head.md` | FAIL | `2c` §2 — หัวตารางพยากรณ์ไม่มีช่อง `FCFF` ในแถวหัวเดียวกัน |
| `bad-scenario-head.md` | FAIL | `2c` §7 — หัวตาราง scenario ไม่มีช่อง `ความน่าจะเป็น` / `IV/share` |
| `bad-scenario-row.md` | FAIL | `2c` §7 — ไม่มี**แถว**ฉาก `Base` (หัวตารางถูกอย่างเดียวไม่พอ) |
| `bad-nobull.md` | FAIL | `2c` §10 — ไม่มีบรรทัด `**Bull:**` |
| `bad-nobear.md` | FAIL | `2c` §10 — ไม่มีบรรทัด `**Bear:**` |
| `bad-nopricegap.md` | FAIL | `2c` §10 — บรรทัด `PRICE GAP` ไม่มีตัวเลข % (หัวข้อเปล่าไม่ใช่ข้อสรุป) |
| `bad-noereturn.md` | FAIL | `2c` §10 — ไม่มีบรรทัด `E[Return]` |
| `bad-no-disclaimer.md` | FAIL | `2c` §11 — เขียนคำว่า `DISCLAIMER` เฉย ๆ แต่ไม่ครบสี่องค์ประกอบที่ล็อกไว้ |
| `bad-assumption-missing.md` | FAIL | `4-citation` — แถวพยากรณ์ไม่มีธงใด ๆ (ไม่มีทั้ง `[Item]` `[tier2/3]` `[สมมติฐาน:]`) |
| `bad-placeholder.md` | FAIL | `5-placeholder` — มี `[ยังไม่มีข้อมูล]` ค้าง |
| `bad-page.md` | FAIL | `6-page-cite` — อ้าง "หน้า 42" |
| `bad-appendix6col.md` | FAIL | `7-appendix` — แถวภาคผนวก 6 ช่อง ไม่ตรงตารางไหนเลย |
| `bad-appendix5col.md` | FAIL | `8-recompute` — แถว**ตารางที่มา**ที่บวมเป็น 5 ช่อง ถูกอ่านเป็น**ตารางคำนวณ** แล้วคิดเลขไม่ได้ |
| `bad-math.md` | FAIL | `8-recompute` — ผลในตารางคำนวณเขียน 175.00 ทั้งที่ `9,570.00 ÷ 58.00 = 165.00` |
| `bad-assumption-count.md` | FAIL | `9-assumption` — ธง `[สมมติฐาน: ...]` 24 บรรทัด แต่ตารางสมมติฐานเหลือ 19 แถว |
| `bad-yaml-no-ivalt.md` | FAIL | `1-yaml` (V23) — ตัด `iv_base_alt` + `_basis` ออกจาก YAML |
| `bad-no-evdef.md` | FAIL | `2c` §0 (V33) — ไม่ประกาศ `นิยามมูลค่ากิจการ` |
| `bad-no-terminal-ic.md` | FAIL | `2c` §5 (V28) — ไม่มี `เงินทุนที่ลงไปปลายทาง` (ROIC ปลายทางลอย) |
| `bad-no-primitive.md` | FAIL | `2c` §8 (V24) — ไม่แปลงค่าที่แก้ย้อนกลับเป็น `ตัวแปรตั้งต้น` |
| `bad-no-bothways.md` | FAIL | `2c` §8 (V25) — ไม่แก้ย้อนอีกทิศด้วยการ `ตรึงมูลค่าปลายทาง` |
| `bad-no-discretion.md` | FAIL | `2c` §9 (V23) — หัวตารางดุลพินิจไม่ครบ (`ดุลพินิจ` + `ทิศ` + `IV`) |
| `bad-nwc-one-period.md` | FAIL | `2c` §12 (V27) — ΔNWC เป็นเลขลอย ไม่แกะเป็น `NWC ต้นงวด` พร้อมนิพจน์ `(= ...)` |

## เจ็ดไฟล์ล่างของตาราง — ชุด V23–V33 (เพิ่ม 2026-09-03)

มาจาก `/scrutinize` เมโมจริง `outputs/damon/META-2026-09-02.md` ซึ่ง **PASS เครื่องตรวจ**
แต่มี BLOCKER 3 ข้อ (รายงานเต็ม: `outputs/scrutinize/damon-META-2026-09-02-audit.md`)

> **บทเรียนจากการสร้างชุดนี้ — เก็บไว้เตือนคนถัดไป**
>
> 1. **regex `IC ปลายทาง` ใช้ไม่ได้** เพราะเป็น substring ของ `ROIC ปลายทาง` → เมโม META
>    จะผ่านฟรี 12 แมตช์โดยไม่ต้องทำอะไรเลย ต้องใช้คำว่า `เงินทุนที่ลงไปปลายทาง`
> 2. **`bad-nwc-one-period.md` รอบแรกสร้างผิด** — ตัดคำออกจากชื่อแถวอย่างเดียว แต่คำว่า
>    `NWC ต้นงวด` ยังอยู่ในช่องสูตร ทำให้ไฟล์ PASS ทั้งที่ควร FAIL
>    → **ผลพลอยได้: รัดกฎ V27 ให้ต้องมีนิพจน์ `(= ...)` ในบรรทัดเดียวกันด้วย**
>    ไม่งั้นเขียนคำลอย ๆ ในช่องสูตรก็ผ่าน ซึ่งไม่ได้กันบั๊กจริง (`-841` ของ META)
>
> ทุกไฟล์ในชุดนี้ยืนยันแล้วว่า **FAIL ข้อเดียว ตรงกฎที่ตั้งใจ** และไม่มี `bad-*` ตัวเดิม
> ตัวไหนล้มด้วยกฎใหม่พ่วง

> **`bad-appendix5col.md` คือกับดักที่ควรจำ** — จำนวนช่องคือ *ตัวจำแนกตาราง* ไม่ใช่แค่รูปแบบ
> แถวตารางที่มาที่พิมพ์เกินไปหนึ่งช่องจึงไม่ได้ FAIL ว่า "ช่องเกิน" แต่ไปโผล่เป็น **แถวตารางคำนวณ
> ที่คิดเลขไม่ได้** ข้อความ FAIL ชี้ไปคนละกฎกับสาเหตุจริง (ตรงกับคำเตือนใน
> [tools/memocheck/README.md](../../tools/memocheck/README.md))
