# ชุดทดสอบ tony_check.py

รันทั้งหมดทุกครั้งที่แก้ `tools/tony_check.py` — ชุดนี้คือตาข่ายกันแก้แล้วพังที่อื่น

## ชุดเดิม (สร้างพร้อมเครื่องตรวจ)

| ไฟล์ | ผลที่ต้องได้ |
|---|---|
| `good.md` | PASS |
| `bad-math.md` · `bad-misc.md` · `bad-missing-section.md` · `bad-nocite.md` · `bad-page.md` · `bad-summary.md` · `bad-verdict.md` | FAIL ตามชื่อเคส |

## ชุดเพิ่ม 2026-08-31 (ตอนแก้ false positive)

| ไฟล์ | ผลที่ต้องได้ | จงใจทดสอบอะไร |
|---|---|---|
| `should_pass.md` | **PASS** | เมโมถูกต้องที่มีคำเคยทำให้พังผิด ๆ — "เข้าซื้อกิจการ" (M&A) · "สินค้าราคาถูก" · "หุ้นถูกซื้อคืน" (buyback, "ถูก" = passive) · แถว YoY แบบส่วนต่าง · เลขลำดับในตาราง §6 |
| `should_fail.md` | **FAIL ที่ `3-verdict`** | คำแนะนำลงทุนของจริง (น่าซื้อ · ควรเข้าซื้อ · หุ้นถูก · ราคาเป้าหมาย) |

## รัน

```bash
# ต้อง PASS 2 ไฟล์
.venv-utils/bin/python tools/tony_check.py scratch/tony-check-fixtures/good.md
.venv-utils/bin/python tools/tony_check.py scratch/tony-check-fixtures/should_pass.md
# ที่เหลือต้อง FAIL ทุกไฟล์
for f in scratch/tony-check-fixtures/bad-*.md scratch/tony-check-fixtures/should_fail.md; do
  .venv-utils/bin/python tools/tony_check.py "$f" | head -1
done
```

ดูกฎที่บังคับจริง: `.venv-utils/bin/python tools/tony_check.py --rules`

## ชุดเพิ่ม 2026-09-03 (กฎ 10-adjust-pair · 11-adjust-period)

ที่มา: ตรวจเมโม `outputs/tony/TER-2026-09-02.md` แล้วพบว่าโทนี่ถอดกำไรขายธุรกิจ 57.1
ออกจากฐาน FY2024 เพื่อคิด incremental margin FY2025 ใหม่ แต่ปล่อยแถว FY2024 ไว้บนฐานเดิม
แล้วเอาสองแถวคนละฐานมาเทียบกัน — ปรับให้ครบทั้งสองปีแล้วตัวเลขกลับด้าน (24.81% → 30.63%
คือดีขึ้น ไม่ใช่แย่ลง) เครื่องตรวจเดิม PASS เพราะทุกแถวคิดซ้ำแล้วตรงสูตรหมด

| ไฟล์ | ผลที่ต้องได้ | จงใจทดสอบอะไร |
|---|---|---|
| `bad-adjust-pair.md` | **FAIL ที่ `10-adjust-pair`** | ถอด one-off ออกจากฐาน FY2024 แล้วมีแถวปรับของ incremental FY2025 แต่ไม่มีของ FY2024 |
| `bad-adjust-period.md` | **FAIL ที่ `11-adjust-period`** | รายการที่ถอดออกจากฐาน FY2024 แต่ตารางที่มาลงงวดเป็น FY2025 |
| `should_pass-adjust.md` | **PASS** | เคสเดียวกันที่ปรับครบทั้งสองปีและลงงวดถูก |

> กฎทั้งสองเปิดจาก `paired_adjustment_check=True` ใน `profiles/tony.py` — profile อื่นปิดอยู่
