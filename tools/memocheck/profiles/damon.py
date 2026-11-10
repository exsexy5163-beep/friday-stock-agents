"""profiles/damon.py — สเปกเมโมของ 'เดมอน' (นักวิเคราะห์ประเมินมูลค่า สาย Damodaran)

เดมอนเป็นเอเจนต์ตัวที่ห้า เขียนใหม่
ให้เข้าทรง friday (US เท่านั้น · ไม่มี NotebookLM · ไม่มี skill dcf-model · หัวเมโมเป็น YAML)

**เดมอนกลับด้านกับอีกสี่ตัว** — ราคาและมูลค่าที่อีกสี่คนถูกห้ามพูดถึง คือเนื้องานของเขา
จึงเป็น profile เดียวที่:

  1. **ปิดกฎ `3-verdict` ทั้งข้อ** (`skip_verdict_rule=True`) — เมโมประเมินมูลค่าต้องพูดคำว่า
     intrinsic value · discount/premium · margin of safety · upside เป็นปกติ เปิดกฎไว้ = FAIL ทุกใบ
     → ตาข่ายแทน: **กฎ `3b-forbidden`** จับคำสั่งซื้อขายล้วน (น่าซื้อ · แนะนำถือ ฯลฯ)
     ที่หยิบจากรายการกลางมาโดยตัดคำที่ชนภาษาประเมินมูลค่าออก (เพิ่ม 2026-10-18)
     + **บรรทัด DISCLAIMER บังคับใน §11** (กฎ 2c) + วินัย V13 ในพรอมต์
  2. **รับธง `[สมมติฐาน: ...]` เป็นที่มาที่ถูกต้องของกฎ `4-citation`**
     (`allow_assumption_citation=True`) — ตารางพยากรณ์อนาคตไม่มี filing ให้อ้าง
     การบีบให้ติด `[tier3]` คือการโกหกว่ามีแหล่ง
  3. **มีกฎ `1-yaml-stance`** — เครื่องตรวจคิดซ้ำด้วย `Decimal` ว่า `valuation_stance`
     ตรงกับ `price` เทียบช่วง `iv_bear`–`iv_bull` จริงไหม เพราะเมื่อปิด `3-verdict` แล้ว
     ฟิลด์นี้คือจุดเดียวที่เครื่องตรวจยังจับ "ข้อสรุปที่เถียงกับตัวเลขของตัวเอง" ได้

ภาคผนวกมี **3 ตาราง** (สมมติฐาน 3 ช่อง · ที่มา 4 ช่อง · คำนวณ 5 ช่องพอดี) —
จำนวนช่องคือตัวจำแนก ตัวที่กว้างสุด (calc) จึงต้องล็อก `max_cols=5` ตามบทเรียนของร็อบ
ผลข้างเคียงที่ตั้งใจ: แถวภาคผนวกที่กว้าง 6 ช่องขึ้นไปไม่ตรงตารางไหนเลย → FAIL ทันที
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from ..core import (NUM_RE, POST_FILING_LINE, VERDICT_PATTERNS_TH, Profile, TableSpec,
                    _derivation_expr, _eval_expr, strip_citations, table_rows)

# ---- คำสั่งซื้อขาย (กฎ 3b-forbidden · เพิ่ม 2026-10-18 จาก /scrutinize สเปคเดมอน)
# ปิด 3-verdict ทั้งข้อแล้วไม่มีอะไรจับ "น่าซื้อ" เลย — แต่คำในรายการกลางส่วนใหญ่เป็นคำสั่งล้วน
# ที่ไม่มีที่ในเมโมประเมินมูลค่า จึงหยิบกลับมาใช้ทั้งหมด ยกเว้นคำที่ชนภาษาประเมินมูลค่าปกติ:
# มูลค่าเหมาะสม / ราคาต่ำกว่ามูลค่าที่แท้จริง (เนื้องาน) · หุ้นถูก/แพง (§11 ต้องแปล discount/premium
# เป็นภาษาบ้าน) · ซื้อดีไหม / ราคาเป้าหมาย (บรรทัดปฏิเสธคำถามผสมอาจยกคำถามผู้ใช้มา)
_ADVICE_EXCLUDED_LABELS = {
    "มูลค่าเหมาะสม", "ราคาที่เหมาะสม", "ราคาต่ำ/สูงกว่ามูลค่าที่แท้จริง",
    "หุ้นถูก (ราคาหุ้น)", "หุ้นราคาถูก", "หุ้นแพง", "หุ้นราคาแพง",
    "ซื้อดีไหม", "ราคาเป้าหมาย",
}
ADVICE_PATTERNS = [(pat, label) for pat, label in VERDICT_PATTERNS_TH
                   if label not in _ADVICE_EXCLUDED_LABELS] + [
    # อังกฤษ: เฉพาะคำของเรตติ้ง — upside / downside / fair value / undervalued เป็นเนื้องานปกติ
    (r"\bstrong buy\b|\bbuy rating\b|\bsell rating\b|\boverweight\b|\bunderweight\b",
     "เรตติ้งซื้อขาย (strong buy · buy/sell rating · overweight/underweight)"),
]

SECTIONS = [
    (0, "THE VALUATION SETUP & METHOD CHOICE"),
    (1, "HISTORICAL FINANCIAL FOUNDATION"),
    (2, "PROJECTION ASSUMPTIONS (3 SCENARIOS)"),
    (3, "WACC / DISCOUNT RATE"),
    (4, "DCF VALUATION"),
    (5, "TERMINAL VALUE STRESS"),
    (6, "RELATIVE VALUATION"),
    (7, "SCENARIO SYNTHESIS & EXPECTED RETURN"),
    (8, "REVERSE DCF"),
    (9, "SENSITIVITY ANALYSIS"),
    (10, "DAMON'S VERDICT"),
    (11, "PLAIN-LANGUAGE SUMMARY"),
    (12, "APPENDIX"),
]

# --- บรรทัด/ตารางบังคับ ---------------------------------------------------
# ผูกกับ 'รูปแบบตาราง markdown' ไม่ใช่คำลอย ๆ ในย่อหน้า (บทเรียน 2c ของอดัม)

_BULL = (r"\*\*Bull\s*[::]?\s*\*\*", "บรรทัด '**Bull:**' (กรณีที่ดีที่สุดที่สมมติฐานรองรับได้)")
_BEAR = (r"\*\*Bear\s*[::]?\s*\*\*", "บรรทัด '**Bear:**' (กรณีที่แย่ที่สุดที่สมมติฐานรองรับได้)")

# §2 — ตารางพยากรณ์รายปี: ปีเป็นแถว ไดรเวอร์เป็นคอลัมน์
# บังคับให้ 'ปี · Revenue · FCFF' อยู่ใน "แถวหัวเดียวกัน" — เขียนสมมติฐานเป็นความเรียง
# แล้วโผล่ FCFF ที่ §4 เฉย ๆ ไม่ได้ ต้องเห็นว่าไดรเวอร์เดินไปเป็นกระแสเงินสดยังไงทีละปี
_PROJECTION_HEAD = (
    r"\|[^\n|]*ปี[^\n|]*\|[^\n]*Revenue[^\n]*\|[^\n]*FCFF[^\n]*\|",
    "หัวตารางพยากรณ์ที่มีครบสามช่องในแถวหัวเดียวกัน — 'ปี' · 'Revenue' · 'FCFF' "
    "(ตัวเลขพยากรณ์ต้องเดินให้เห็นเป็นแถว ๆ ไม่ใช่บรรยายลอยแล้วโผล่ผลที่ §4)",
)

# §7 — ตาราง scenario: หัวตารางต้องมีช่องความน่าจะเป็นและช่องมูลค่าต่อหุ้น
# แล้ว **บังคับรายแถว** ว่าครบทั้งสามฉากและแต่ละแถวมีตัวเลขจริง
# (บังคับที่หัวตารางอย่างเดียวไม่พอ — เว้นแถวไหนก็ยังผ่าน บทเรียนสกอร์การ์ดของอดัม)
_SCENARIO_HEAD = (
    r"\|[^\n]*ความน่าจะเป็น[^\n]*\|[^\n]*IV\s*/\s*share[^\n]*\|",
    "หัวตาราง scenario ที่มีช่อง 'ความน่าจะเป็น' และ 'IV/share' ในแถวหัวเดียวกัน",
)
# ต่อท้ายชื่อฉากด้วย _HAS_NUM: ในแถวเดียวกันต้องมีตัวเลขจริง ไม่ใช่แถวเปล่าที่มีแต่ชื่อ
_HAS_NUM = r"[^\n]*\d"
_SCENARIO_ROWS = [
    (r"(?i)\|\s*Bear\s*\|" + _HAS_NUM, "แถว scenario 'Bear' ที่มีตัวเลขในแถวเดียวกัน"),
    (r"(?i)\|\s*Base\s*\|" + _HAS_NUM, "แถว scenario 'Base' ที่มีตัวเลขในแถวเดียวกัน"),
    (r"(?i)\|\s*Bull\s*\|" + _HAS_NUM, "แถว scenario 'Bull' ที่มีตัวเลขในแถวเดียวกัน"),
]

# §10 — สองบรรทัดตัวเลขที่ห้ามหาย: ช่องว่างราคา-มูลค่า และผลตอบแทนที่คาดหวัง
# บังคับให้มี '%' ในบรรทัดเดียวกัน — คำว่า PRICE GAP ที่ไม่มีตัวเลขคือหัวข้อ ไม่ใช่ข้อสรุป
_PRICE_GAP = (
    r"PRICE GAP[^\n]*%",
    "บรรทัด 'PRICE GAP' ที่มีตัวเลข % อยู่ในบรรทัดเดียวกัน "
    "(ช่องว่างราคา-มูลค่าคือข้อสรุปของเมโมทั้งใบ ห้ามเป็นหัวข้อเปล่า)",
)
_EXPECTED_RETURN = (
    r"E\[Return\][^\n]*%",
    "บรรทัด 'E[Return]' ที่มีตัวเลข % อยู่ในบรรทัดเดียวกัน "
    "(ผลตอบแทนที่คาดหวังแบบถ่วงความน่าจะเป็นข้ามสามฉาก)",
)

# §11 — บรรทัด DISCLAIMER
# ⚠️ หนึ่งในสองกลไกที่เหลือหลังปิดกฎ 3-verdict ทั้งข้อ (อีกตัวคือ ADVICE_PATTERNS ข้างบน)
# จึงล็อกถ้อยคำแน่นกว่ากฎ 2c ตัวอื่น: ต้องมีครบสี่องค์ประกอบในบรรทัดเดียวกับคำว่า DISCLAIMER
# (ใช้ lookahead ไม่ล็อกลำดับ แต่ล็อกว่า 'ต้องมี' — เขียนคำว่า DISCLAIMER เฉย ๆ ไม่ผ่าน)
_DISCLAIMER = (
    r"DISCLAIMER"
    r"(?=[^\n]*\bIV\b)"
    r"(?=[^\n]*Margin of Safety)"
    r"(?=[^\n]*Expected Return)"
    r"(?=[^\n]*ไม่ใช่คำสั่งซื้อ/ขาย)",
    "บรรทัด DISCLAIMER ที่ระบุครบในบรรทัดเดียวกันว่า 'IV' · 'Margin of Safety' · "
    "'Expected Return' คือช่องว่างราคา-มูลค่า และ 'ไม่ใช่คำสั่งซื้อ/ขาย' "
    "(หนึ่งในสองกลไกที่กันการฟันธงหลังปิดกฎ 3-verdict — ห้ามดัดถ้อยคำ)",
)

# --- V23–V33 (รอบสอง — ออกจาก /scrutinize เมโม META 2026-09-02) -------------
# ทุกตัวผ่านการทดสอบแล้วว่า "ยิงจริง" กับเมโม META ใบนั้น (ไม่มีตัวไหนผ่านฟรี)
# บทเรียนระหว่างทาง: regex `IC ปลายทาง` ใช้ไม่ได้ เพราะเป็น substring ของ `ROIC ปลายทาง`
# → ต้องใช้คำว่า `เงินทุนที่ลงไปปลายทาง` ที่ไม่ชนของเดิม

# §0 — ประกาศนิยาม EV ครั้งเดียวแล้วใช้ตัวเดียวทั้งเมโม (V33)
_EV_DEF = (
    r"นิยามมูลค่ากิจการ",
    "บรรทัด 'นิยามมูลค่ากิจการ' ที่เขียนสูตร EV ออกมาให้ครบ (V33) — "
    "เมโม META ใช้ EV สองนิยามในย่อหน้าเดียวกันของ §6 ทำให้ตัวคูณอนาคตดูถูกกว่าจริง",
)

# §5 — ROIC ปลายทางต้องผูกกับงบดุลที่ช่วงชัดเจนสร้าง (V28)
_TERMINAL_IC = (
    r"เงินทุนที่ลงไปปลายทาง",
    "บรรทัด 'เงินทุนที่ลงไปปลายทาง' ที่เดินจากเส้น PP&E จริงแล้วคิด ROIC โดยนัย (V28) — "
    "เมโม META ตั้ง ROIC ปลายทาง 20% ทั้งที่งบดุลที่โมเดลสร้างเองให้ 18.32%",
)

# §8 — สองด่านของ DCF ย้อนกลับ
_REVERSE_PRIMITIVE = (
    r"ตัวแปรตั้งต้น",
    "บรรทัดที่แปลงค่าที่แก้ย้อนได้กลับเป็น 'ตัวแปรตั้งต้น' ก่อนตัดสินว่าทำได้จริงไหม (V24) — "
    "เมโม META ประกาศว่า WACC 6.97% 'เท่ากับเบตาติดลบ' ทั้งที่คิดจริงได้ +0.55",
)
_REVERSE_BOTH_WAYS = (
    r"ตรึงมูลค่าปลายทาง",
    "บรรทัดที่แก้ย้อนอีกทิศด้วยการ 'ตรึงมูลค่าปลายทาง' (V25) — "
    "การตรึงช่วงชัดเจนแล้วแก้หาปลายทางทำให้ 100% ของช่องว่างตกที่ปลายทางโดยการก่อสร้าง "
    "จะอ้างสัดส่วนของช่องว่างได้ต้องแก้ย้อนสองทิศ",
)

# §9 — ตารางดุลพินิจ: หัวตารางต้องมีครบสามช่องในแถวหัวเดียวกัน (V23)
_DISCRETION_HEAD = (
    r"\|[^\n|]*ดุลพินิจ[^\n|]*\|[^\n]*ทิศ[^\n]*\|[^\n]*IV[^\n]*\|",
    "หัวตารางดุลพินิจที่มีครบสามช่องในแถวหัวเดียวกัน — 'ดุลพินิจ' · 'ทิศ' · 'IV' (V23) "
    "(ทุกจุดที่เลือกได้มากกว่าหนึ่งทาง ต้องอยู่ในตารางเดียวพร้อมทิศทางและผลต่อ IV "
    "แล้วปิดท้ายด้วย IV เมื่อพลิกทุกแถวพร้อมกัน → iv_base_alt)",
)

# §12 — ΔNWC ต้องแกะกลับได้ถึง NWC สองงวด (V27)
_NWC_TWO_PERIODS = (
    r"NWC\s*ต้นงวด[^\n]*\(\s*=",
    "แถวตารางคำนวณที่แสดง 'NWC ต้นงวด' (คู่กับ NWC ปลายงวด) พร้อมนิพจน์ (= ...) "
    "ที่แกะเลขสองงวดออกมาให้เห็นจริง — เขียนคำลอย ๆ ในช่องสูตรโดยไม่โชว์ตัวเลขไม่ผ่าน (V27) — "
    "เมโม META หัก ΔNWC FY2025 เป็น +841 ที่ไม่มีที่มาและเครื่องหมายสวนธรรมเนียมตัวเอง",
)


# --- V14(ก) · ผลตอบแทนส่วนเพิ่มของฉาก Base เทียบ ROIC อดีต (เพิ่ม 2026-10-10) -----
# บทเรียน BWXT 2026-10-08: §0 เล่าว่า "มาร์จิ้นไม่น่าขยายมาก" แต่ §2 ฉาก Base ใส่ผลตอบแทน
# ส่วนเพิ่มโดยนัย 19.02–30.76% เทียบ ROIC อดีต 11.35–15.08% แล้วอธิบายหนึ่งย่อหน้าแล้วผ่านไป
# เครื่องตรวจหา ROIC อดีตเองไม่ได้ (เมโมแต่ละใบวางไว้คนละที่) จึงบังคับให้ประกาศเป็นบรรทัดเดียว
# ใน §2 แล้วตัดสินด้วย Decimal:
#   Y > X → ทางที่เลือกต้องเป็น '§0 รองรับ' และ §0 ต้องพูดถึง 'ผลตอบแทนส่วนเพิ่ม' จริง
#   Y ≤ X → 'ไม่เกิน' หรือ 'ลด Base' · Y 'ไม่นิยาม' (ลงทุนซ้ำ ≤ 0) → ต้องเป็น 'ลงทุนซ้ำ ≤ 0'
# ถ้า §2 มีตาราง Base ที่มีคอลัมน์ 'ผลตอบแทนส่วนเพิ่มโดยนัย' → Y ต้องเท่าค่าสูงสุดในคอลัมน์นั้น
# (กันประกาศเลขเอง) · ROIC อดีต X ตรวจย้อนไม่ได้ — เป็นวินัยของเอเจนต์ + ตาตัวหลัก
_V14A_RULE = "2c-v14a"
_V14A_LINE = re.compile(
    r"ตรวจผลตอบแทนส่วนเพิ่ม\s*\(V14ก\)\s*:\s*"
    r"ROIC อดีตสูงสุด\s*(?P<x>-?[\d,]+(?:\.\d+)?)\s*%\s*·\s*"
    r"ผลตอบแทนส่วนเพิ่มโดยนัยสูงสุดฉาก Base\s*(?:(?P<y>-?[\d,]+(?:\.\d+)?)\s*%|(?P<undef>ไม่นิยาม))\s*·\s*"
    r"ทางที่เลือก\s*:\s*(?P<choice>ไม่เกิน|ลด Base|§0 รองรับ|ลงทุนซ้ำ ≤ 0)"
)
_V14A_FORMAT = (
    "ตรวจผลตอบแทนส่วนเพิ่ม (V14ก): ROIC อดีตสูงสุด X% · ผลตอบแทนส่วนเพิ่มโดยนัยสูงสุดฉาก Base Y% · "
    "ทางที่เลือก: <ไม่เกิน|ลด Base|§0 รองรับ|ลงทุนซ้ำ ≤ 0>"
)
_INCR_COL = "ผลตอบแทนส่วนเพิ่มโดยนัย"


def _section(lines, heads, num):
    for pos, (n, start) in enumerate(heads):
        if n == num:
            end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
            return lines[start:end]
    return None


def _dec(s):
    try:
        return Decimal(s.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _base_incremental_max(sec):
    """ค่าสูงสุดของคอลัมน์ผลตอบแทนส่วนเพิ่มโดยนัย ในตาราง §2 ที่หัวข้อเหนือตารางระบุ 'Base'
    คืน None ถ้าหาตารางแบบนั้นไม่เจอ (รูปแบบเก่า) — ข้ามการตรวจไขว้ ไม่ FAIL"""
    title = ""
    i = 0
    while i < len(sec):
        ln = sec[i].strip()
        if ln.startswith("|") and _INCR_COL in ln and "ปี" in ln:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            col = next((k for k, c in enumerate(cells) if _INCR_COL in c), None)
            vals = []
            j = i + 2  # ข้ามแถวคั่น |---|
            while j < len(sec) and sec[j].strip().startswith("|"):
                row = [c.strip() for c in sec[j].strip().strip("|").split("|")]
                if col is not None and col < len(row) and re.match(r"(FY)?\d{4}", row[0]):
                    v = _dec(re.sub(r"[^\d.,-]", "", row[col]))
                    if v is not None:
                        vals.append(v)
                j += 1
            if "Base" in title and vals:
                return max(vals)
            i = j
            continue
        if ln and not ln.startswith("|"):
            title = ln
        i += 1
    return None


# ---- V26 · เลขในวงเล็บ (= ...) ของตารางคำนวณต้องไม่ใช่ "เลขลอย" (เพิ่ม 2026-10-10)
# บทเรียน META: FCFF FY2025 (=83,276×0.84+18,616-72,215-841) — 841 ไม่ปรากฏที่อื่นในเมโมเลย
# แบบหลวม (ผู้ใช้เลือก): เลขต้องปรากฏที่อื่นในเมโมสักที่ ไม่บังคับว่าต้องอยู่ในตารางที่มาเท่านั้น
_V26_RULE = "2c-v26"
_V26_CONSTS = {Decimal(x) for x in ("0", "1", "2", "100", "1000", "1000000")}


def _v26_variants(v):
    """ค่าที่ถือว่า 'เลขเดียวกัน': ตัวมันเอง · ×/÷100 · 1−x (เช่น 0.8 = 1 − ภาษี 20%) · x−1 (1.14 = 1 + 14%)"""
    out = {v, v * 100, v / 100}
    if v < 1:
        out |= {1 - v, (1 - v) * 100}
    if 1 < v < 3:
        out |= {v - 1, (v - 1) * 100}
    return out


def _v26_found(tok, pool):
    cands = _v26_variants(tok)
    if cands & pool:
        return True
    for cand in cands:  # ปัดเศษ: ตัวในเมโมเขียนหยาบกว่า แต่ยังมีทศนิยม ≥ 1 ตำแหน่ง
        c_exp = cand.as_tuple().exponent
        for p in pool:
            exp = p.as_tuple().exponent
            if isinstance(exp, int) and isinstance(c_exp, int) and c_exp < exp < 0:
                try:
                    if cand.quantize(Decimal(1).scaleb(exp)) == p:
                        return True
                except InvalidOperation:
                    pass
    return False


def _numbers(s):
    out = set()
    for t in NUM_RE.findall(s):
        v = _dec(t)
        if v is not None:
            out.add(abs(v))
    return out


def check_v26(lines, heads, fail):
    sec12 = _section(lines, heads, 12)
    if sec12 is None:
        return
    start = next(s for n, s in heads if n == 12)
    calc_lines = set()
    in_calc = False
    for i, cells, head in table_rows(sec12):
        if head:
            in_calc = "สูตร" in "".join(cells) and "ตัวตั้ง" in "".join(cells) and len(cells) == 5
            continue
        if in_calc and len(cells) == 5:
            calc_lines.add(start + i - 1)
    line_nums = [_numbers(ln) for ln in lines]
    for idx in sorted(calc_lines):
        cells = [c.strip() for c in lines[idx].strip().strip("|").split("|")]
        pool = set().union(*(ns for k, ns in enumerate(line_nums) if k != idx))
        missing = []
        for cell in (cells[2], cells[3]):
            expr = _derivation_expr(strip_citations(cell))
            if not expr:
                continue
            for t in NUM_RE.findall(expr):
                v = _dec(t)
                if v is None or abs(v) in _V26_CONSTS or _v26_found(abs(v), pool):
                    continue
                if t not in missing:
                    missing.append(t)
        if missing:
            fail(_V26_RULE,
                 f"ตารางคำนวณ §12 แถว '{cells[0]}': เลข {', '.join(missing)} ในวงเล็บ (= ...) "
                 "ไม่ปรากฏที่อื่นในเมโมเลย — เพิ่มแถวในตารางที่มา หรือแตกเป็นแถวคำนวณของตัวเอง (V26)")


# ---- V29 · ตัวคูณขาออกเป็นพีชคณิตของสมมติฐาน → ต้องโชว์ค่าตามทฤษฎี + ประกาศคนละระบอบ (2026-10-10)
# กันลืมได้ + คิดเลขในวงเล็บซ้ำได้ — แต่ไม่รู้ว่า g/ROIC/WACC ในสูตรตรงกับโมเดลจริงไหม (ตัวหลักดูด้วยตา)
_V29_RULE = "2c-v29"
_V29_FORMAT = "ตัวคูณขาออกตามทฤษฎี (V29): <M>x (=<สูตรตัวเลข>)"
_V29_LINE = re.compile(r"ตัวคูณขาออกตามทฤษฎี \(V29\):\s*(?P<m>-?\d[\d,]*(?:\.\d+)?)\s*x?\s*(?P<d>\(\s*=.*)")


def check_v29(lines, heads, fail):
    sec5 = _section(lines, heads, 5)
    if sec5 is None:
        return
    found = None
    for ln in sec5:
        m = _V29_LINE.search(re.sub(r"[*`]", "", ln))
        if m:
            found = m
            break
    if found is None:
        fail(_V29_RULE, f"§5 ไม่มีบรรทัด '{_V29_FORMAT}' (V29)")
    else:
        expr = _derivation_expr(found.group("d"))
        got = _eval_expr(expr) if expr else None
        want = _dec(found.group("m"))
        if got is None or want is None:
            fail(_V29_RULE, "บรรทัด V29 คิดซ้ำไม่ได้ — ในวงเล็บ (= ...) ต้องเป็นเลขกับ + − × ÷ ( ) ล้วน")
        elif abs(got - want) > Decimal("0.01"):
            fail(_V29_RULE, f"บรรทัด V29 เขียน {want}x แต่สูตรในวงเล็บคิดได้ {got.quantize(Decimal('0.01'))}x")
    if not any("คนละระบอบ" in ln for ln in sec5):
        fail(_V29_RULE, "§5 ไม่มีคำว่า 'คนละระบอบ' — เทียบตัวคูณขาออกกับอดีตต้องประกาศว่าคนละระบอบการเติบโต (V29)")


# ---- V30 · หน่วยของโมเดลกับ GDP ต้องตรงกัน (2026-10-10)
_V30_RULE = "2c-v30"
_V30_FORMAT = ("หน่วยโมเดล (V30): <ตัวเงิน|แท้จริง> · เทียบ GDP <ตัวเงิน|แท้จริง> X% · "
               "เพดาน Y% · g_term สูงสุด Z%")
_V30_LINE = re.compile(
    r"หน่วยโมเดล \(V30\):\s*(?P<u>ตัวเงิน|แท้จริง)\s*·\s*เทียบ GDP\s*(?P<gu>ตัวเงิน|แท้จริง)\s*"
    r"(?P<gdp>-?\d+(?:\.\d+)?)\s*%\s*·\s*เพดาน\s*(?P<cap>-?\d+(?:\.\d+)?)\s*%\s*·\s*"
    r"g_term สูงสุด\s*(?P<g>-?\d+(?:\.\d+)?)\s*%")


def _gterm_max(sec2):
    """ค่าสูงสุดของคอลัมน์ g_term ในตารางแรกของ §2 ที่มีคอลัมน์นั้น — None ถ้าหาไม่เจอ (ข้ามการเทียบ)"""
    col, vals = None, []
    for _, cells, head in table_rows(sec2):
        if head:
            if vals:
                break
            col = next((k for k, c in enumerate(cells) if "g_term" in c), None)
            continue
        if col is not None and col < len(cells):
            m = NUM_RE.search(strip_citations(cells[col]).replace("−", "-"))
            v = _dec(m.group(0)) if m else None
            if v is not None:
                vals.append(v)
    return max(vals) if vals else None


def check_v30(lines, heads, fail):
    sec5 = _section(lines, heads, 5)
    if sec5 is None:
        return
    found = None
    for ln in sec5:
        m = _V30_LINE.search(re.sub(r"[*`]", "", ln))
        if m:
            found = m
            break
    if found is None:
        fail(_V30_RULE, f"§5 ไม่มีบรรทัด '{_V30_FORMAT}' (V30)")
        return
    if found.group("u") != found.group("gu"):
        fail(_V30_RULE, f"โมเดล{found.group('u')} แต่เทียบ GDP {found.group('gu')} — หน่วยต้องตรงกัน (V30)")
    gdp, cap, g = _dec(found.group("gdp")), _dec(found.group("cap")), _dec(found.group("g"))
    if cap > gdp:
        fail(_V30_RULE, f"เพดาน {cap}% สูงกว่า GDP {gdp}% — เพดานต้อง ≤ GDP ที่หน่วยตรงกัน")
    if g > cap:
        fail(_V30_RULE, f"g_term สูงสุด {g}% เกินเพดาน {cap}%")
    tmax = _gterm_max(_section(lines, heads, 2) or [])
    if tmax is not None and abs(tmax - g) > Decimal("0.01"):
        fail(_V30_RULE, f"บรรทัด V30 ประกาศ g_term สูงสุด {g}% แต่คอลัมน์ g_term ในตาราง §2 สูงสุด {tmax}%")


# ---- V31 (แบบแคบ) · "กระทบ ... X ต่อหุ้น" ต้องติดป้าย + อยู่ในตารางคำนวณ (2026-10-10)
# จับเฉพาะคำว่า 'กระทบ' — เปลี่ยนคำก็หลบได้ (ผู้ใช้เลือกแบบแคบเพราะแบบกว้างจับผิด 3 ใน 5)
_V31_RULE = "2c-v31"
_V31_RX = re.compile(r"กระทบ(?:มูลค่า)?[^|\n]{0,40}?(?P<n>\d[\d,]*(?:\.\d+)?)\s*(?:USD\s*)?(?:ต่อหุ้น|/หุ้น)")
_V31_TAGS = ("อยู่ในฉากฐานแล้ว", "ส่วนเพิ่ม")


def _calc_results(lines, heads):
    sec12 = _section(lines, heads, 12) or []
    out, in_calc = set(), False
    for _, cells, head in table_rows(sec12):
        if head:
            in_calc = "สูตร" in "".join(cells) and "ตัวตั้ง" in "".join(cells)
            continue
        if in_calc and len(cells) == 5:
            out |= _numbers(strip_citations(cells[4]))
    return out


def check_v31(lines, heads, fail):
    results = _calc_results(lines, heads)
    for pos, (num, start) in enumerate(heads):
        if num == 12:
            continue
        end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
        for ln in lines[start:end]:
            for m in _V31_RX.finditer(ln):
                v = _dec(m.group("n"))
                why = []
                if not any(t in ln for t in _V31_TAGS):
                    why.append("ไม่ระบุ 'อยู่ในฉากฐานแล้ว' หรือ 'ส่วนเพิ่ม'")
                if v is None or not any(abs(v - r) <= Decimal("0.01") for r in results):
                    why.append("ตัวเลขไม่อยู่ในคอลัมน์ผลของตารางคำนวณ §12")
                if why:
                    fail(_V31_RULE, f"§{num} '{m.group(0)}' — " + " · ".join(why) + " (V31)")


# ---- V32 · ลิสต์ที่ประกาศว่าเรียงลำดับ ต้องเรียงจริง (2026-10-10)
# ตรวจเฉพาะลิสต์ (1)(2)… ในบรรทัดเดียว หรือ bullet/เลขข้อในบรรทัดถัดไป — ลิสต์ในตาราง ยังไม่ตรวจ
_V32_RULE = "2c-v32"
_V32_TRIGGER = re.compile(r"เรียงตาม(?:ขนาด|ผล)|มากไปน้อย|น้อยไปมาก")
_V32_ITEM = re.compile(r"\s*(?:\d+[.)]|[-*•])\s")
_V32_USD = re.compile(r"(-?\d[\d,]*(?:\.\d+)?)\s*USD")


def check_v32(lines, heads, fail):
    for pos, (num, start) in enumerate(heads):
        end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
        body = lines[start:end]
        for k, ln in enumerate(body):
            if not _V32_TRIGGER.search(ln):
                continue
            items = re.split(r"\(\d+\)", ln)[1:]
            if len(items) < 2:
                items, j = [], k + 1
                while j < len(body) and not body[j].strip():
                    j += 1
                while j < len(body) and _V32_ITEM.match(body[j]):
                    items.append(body[j])
                    j += 1
            vals = []
            for it in items:
                m = _V32_USD.search(strip_citations(it))
                v = _dec(m.group(1)) if m else None
                if v is not None:
                    vals.append(abs(v))
            if len(vals) < 2:
                continue
            asc = "น้อยไปมาก" in ln
            if vals != sorted(vals, reverse=not asc):
                fail(_V32_RULE,
                     f"§{num} บรรทัด {start + k + 1}: ประกาศว่าเรียงลำดับ แต่ค่า USD ตามลำดับคือ "
                     + " → ".join(str(v) for v in vals)
                     + " — เรียงใหม่ หรือตัดคำว่า 'เรียงตาม...' ออก (V32)")


def check_semantics(text, meta, lines, heads, fail):
    check_v26(lines, heads, fail)
    check_v29(lines, heads, fail)
    check_v30(lines, heads, fail)
    check_v31(lines, heads, fail)
    check_v32(lines, heads, fail)
    sec2 = _section(lines, heads, 2)
    if sec2 is None:
        return  # กฎ 2-sections รายงานไปแล้ว
    found = None
    for ln in sec2:
        m = _V14A_LINE.search(re.sub(r"[*`]", "", ln))
        if m:
            found = m
            break
    if found is None:
        fail(_V14A_RULE, "§2 ไม่มีบรรทัด '" + _V14A_FORMAT + "' (V14ก)")
        return
    x = _dec(found.group("x"))
    y = None if found.group("undef") else _dec(found.group("y"))
    choice = found.group("choice")
    if y is None:
        if choice != "ลงทุนซ้ำ ≤ 0":
            fail(_V14A_RULE, "ผลตอบแทนส่วนเพิ่มฉาก Base 'ไม่นิยาม' ใช้ได้คู่กับ 'ทางที่เลือก: ลงทุนซ้ำ ≤ 0' เท่านั้น")
        return
    if choice == "ลงทุนซ้ำ ≤ 0":
        fail(_V14A_RULE, "'ทางที่เลือก: ลงทุนซ้ำ ≤ 0' ต้องคู่กับผลตอบแทนส่วนเพิ่ม 'ไม่นิยาม'")
    elif y > x and choice != "§0 รองรับ":
        fail(_V14A_RULE,
             f"ผลตอบแทนส่วนเพิ่มโดยนัยสูงสุดฉาก Base {y}% เกิน ROIC อดีตสูงสุด {x}% "
             f"แต่ทางที่เลือกคือ '{choice}' — ต้องเป็น '§0 รองรับ' หรือลด Base จนไม่เกิน {x}%")
    elif y <= x and choice == "§0 รองรับ":
        fail(_V14A_RULE, f"ผลตอบแทนส่วนเพิ่มสูงสุด {y}% ไม่เกิน ROIC อดีต {x}% — ทางที่เลือกต้องเป็น 'ไม่เกิน' หรือ 'ลด Base'")
    if choice == "§0 รองรับ":
        sec0 = _section(lines, heads, 0) or []
        if not any("ผลตอบแทนส่วนเพิ่ม" in ln for ln in sec0):
            fail(_V14A_RULE, "เลือก '§0 รองรับ' แต่ §0 ไม่มีประโยคที่พูดถึง 'ผลตอบแทนส่วนเพิ่ม' เลย")
    table_max = _base_incremental_max(sec2)
    if table_max is not None and abs(table_max - y) > Decimal("0.01"):
        fail(_V14A_RULE,
             f"บรรทัด V14ก ประกาศสูงสุดฉาก Base {y}% แต่คอลัมน์ '{_INCR_COL}' ในตาราง Base สูงสุด {table_max}%")


PROFILE = Profile(
    slug="damon",
    tool_name="damon_check.py",
    # เดมอนกลับด้าน: price / IV ที่อีกสี่ตัวห้ามมี กลายเป็นฟิลด์บังคับ
    required_yaml_fields=[
        "ticker", "company", "form", "fiscal_year", "accession", "filing_date",
        "as_of", "method", "price", "iv_bear", "iv_base", "iv_bull",
        # V23 — IV เมื่อพลิกทางเลือกดุลพินิจ 'ทุกข้อพร้อมกัน' ไม่ใช่ทีละข้อ
        # กันไม่ให้พาดหัวเป็นปลายสุดโต่งของช่วงที่เมโมเองยอมรับว่าชอบธรรมทั้งช่วง
        "iv_base_alt", "iv_base_alt_basis",
        "price_gap_pct", "expected_return_pct",
        "valuation_stance", "valuation_stance_basis", "tiers_used", "exec_summary",
    ],
    # ยังกันคะแนนลอยและคำสั่งซื้อขายที่หัวเมโมเหมือนเดิม —
    # `valuation_stance` เป็นคนละคีย์กับ `verdict` จึงไม่ชนกัน และถูกบังคับให้มี _basis คู่เสมอ
    forbidden_yaml_fields=[
        "score", "คะแนน", "conviction", "rating", "recommendation", "action", "verdict",
    ],
    sections=SECTIONS,
    appendix_section=12,
    appendix_tables=[
        TableSpec(
            key="assumption",
            label="ตารางสมมติฐาน (สมมติฐาน | ค่าที่ใช้ | เหตุผล + ที่มา)",
            short="ตารางสมมติฐาน",
            min_cols=3, max_cols=3,
            header_keys=("สมมติฐาน", "เหตุผล"),
        ),
        TableSpec(
            key="source",
            label="ตารางที่มา (ตัวเลข | ฟอร์ม | งวด | Item)",
            short="ตารางที่มา",
            min_cols=4, max_cols=4,
            header_keys=("ฟอร์ม", "งวด"),
        ),
        TableSpec(
            key="calc",
            label="ตารางคำนวณ (ชื่อ | สูตร | ตัวตั้ง | ตัวหาร | ผล)",
            short="ตารางคำนวณ",
            min_cols=5, max_cols=5,
            header_keys=("สูตร", "ตัวตั้ง"),
            kind="calc",
        ),
    ],
    section_required_patterns={
        0: [_EV_DEF],
        2: [_PROJECTION_HEAD],
        5: [_TERMINAL_IC],
        7: [_SCENARIO_HEAD, *_SCENARIO_ROWS],
        8: [_REVERSE_PRIMITIVE, _REVERSE_BOTH_WAYS],
        9: [_DISCRETION_HEAD],
        10: [_BULL, _BEAR, _PRICE_GAP, _EXPECTED_RETURN],
        11: [_DISCLAIMER],
        12: [_NWC_TWO_PERIODS, POST_FILING_LINE],
    },
    enum_yaml_fields={
        "valuation_stance": ("Discount", "Fair", "Premium"),
        "method": ("FCFF", "FCFE", "DDM", "NAV"),
    },
    stance_range_check=(
        "valuation_stance", "price", "iv_bear", "iv_bull",
        "Discount", "Fair", "Premium",
    ),
    skip_verdict_rule=True,
    # ตาข่ายแทน 3-verdict: เฉพาะคำสั่งซื้อขาย ไม่ยกเว้น section ไหน (§11 เสี่ยงสุด)
    forbidden_body_patterns=ADVICE_PATTERNS,
    semantic_check=check_semantics,
    allow_assumption_citation=True,
    assumption_table_key="assumption",
    opinion_sections=(0, 10),
    require_inference=False,   # ธง [สมมติฐาน: ...] ทำหน้าที่นี้แล้ว
    rules_opinion_lines=[
        "2b-opinion   §0–§10 ทุกอันต้องมีบรรทัดที่ขึ้นต้นด้วย '(ความเห็น:' อยู่ในตัว section",
        "             (§11 ไม่ต้อง เพราะทั้ง section เป็นภาษาคน · §12 ไม่ต้อง เพราะเป็นภาคผนวก)",
    ],
    rules_citation_lines=[
        "4-citation   ทุก 'แถว' ตารางนอก §12 ที่มีตัวเลขข้อเท็จจริง ต้องมี",
        "             [ฟอร์ม ... Item ...] หรือ [tier2]/[tier3] หรือ [สมมติฐาน: ...]",
        "             อยู่ในแถวนั้นเอง",
        "             ยกเว้น: เลขลำดับล้วน 1–2 หลัก และแถวที่มี [ไม่เปิดเผย]/[ข้อมูลไม่พอ]",
        "             [สมมติฐาน: ...] ใช้กับ 'ตัวเลขอนาคต' เท่านั้น (พยากรณ์ · กริด sensitivity ·",
        "             มูลค่าต่อฉาก) — เลขอดีตที่มี filing ให้อ้าง ห้ามหลบมาใช้ธงนี้",
        "             ตัวเลขจาก WebSearch/เว็บการเงิน = [tier3] เสมอ ห้ามใส่เป็น [ฟอร์ม ... Item ...]",
        "9-assumption ทุก 'บรรทัด' ที่ติดธง [สมมติฐาน: ...] ต้องมีแถวคู่ในตารางสมมติฐาน §12",
        "             (เครื่องตรวจนับบรรทัดเทียบจำนวนแถวจริง — ธงนี้จึงเป็นของแพง ใช้เท่าที่จำเป็น)",
    ],
    rules_appendix_lines=[
        "7-appendix   §12 ต้องมี 3 ตาราง: สมมติฐาน = 3 ช่อง (สมมติฐาน|ค่าที่ใช้|เหตุผล) ·",
        "             ที่มา = 4 ช่อง (ตัวเลข|ฟอร์ม|งวด|Item) ·",
        "             คำนวณ = 5 ช่องพอดี (ชื่อ|สูตร|ตัวตั้ง|ตัวหาร|ผล)",
        "             ห้ามมีช่องว่าง — จำนวนช่องคือตัวจำแนกตาราง แถว 6 ช่องขึ้นไปไม่ตรงตารางไหน",
        "             + บรรทัด เหตุการณ์หลัง filing: <กระทบ|ไม่กระทบ|ไม่มี 8-K|ไม่มี 6-K> (2c-required-line)",
    ],
    rules_extra_lines=[
        "             วงเล็บ (= ...) คิดได้ทั้ง + − × ÷ และวงเล็บซ้อน",
        "             แถวที่ไม่ใช่การหาร (คูณ/บวก) ให้ใส่ตัวหาร = 1 แล้วผลเท่ากับตัวตั้ง",
        "1-yaml (เดมอน) method รับแค่ FCFF | FCFE | DDM | NAV — เลือกตามธุรกิจ (V5)",
        "             valuation_stance_basis บังคับมีและห้ามเว้นว่าง — คำตัดสินเชิงมูลค่า",
        "             ที่ไม่บอกว่าอิงสมมติฐานตัวไหน คือตัวเลขที่ตรวจย้อนไม่ได้",
        "             price / iv_bear / iv_base / iv_bull ต้องเป็นตัวเลขล้วน (สกุลเงินไปอยู่ใน",
        "             เนื้อเมโม) เพราะเครื่องตรวจต้องคิดซ้ำ",
        "2c (เดมอน)   §11 ต้องมีบรรทัด DISCLAIMER ครบถ้อยคำ",
        "3b (เดมอน)   ห้ามคำสั่งซื้อขาย (น่าซื้อ · ควรซื้อ · แนะนำถือ · ทยอยซื้อ · จังหวะเข้าซื้อ ฯลฯ)",
        "             ทุก section — ตาข่ายแทน 3-verdict ที่ปิดไว้ · ไม่จับประโยคที่สื่อเป็นนัย",
        "             เช่น 'ที่ราคานี้คุ้ม' — ส่วนนั้นยังเป็นวินัย V13",
        "",
        "--- V23-V33 (รอบสอง — จาก /scrutinize เมโม META 2026-09-02) ---",
        "1-yaml (V23) iv_base_alt + iv_base_alt_basis บังคับมี = IV ฐานเมื่อพลิกทางเลือก",
        "             ดุลพินิจ 'ทุกข้อพร้อมกัน' — เมโม META พาดหัวช่องว่าง 81.93% ทั้งที่",
        "             ช่วงจริงตามธรรมเนียมที่ตัวเองยอมรับคือ 36.20-81.93%",
        "2c (V33)     §0 ต้องมีบรรทัด 'นิยามมูลค่ากิจการ' — EV นิยามเดียวทั้งเมโม",
        "2c (V28)     §5 ต้องมีบรรทัด 'เงินทุนที่ลงไปปลายทาง' — ROIC ปลายทางต้องผูกกับ",
        "             งบดุลที่ช่วงชัดเจนสร้าง ไม่ใช่พารามิเตอร์ลอย",
        "2c (V24)     §8 ต้องมีคำว่า 'ตัวแปรตั้งต้น' — ห้ามประกาศว่าเป็นไปไม่ได้จากสายตา",
        "2c (V25)     §8 ต้องมีคำว่า 'ตรึงมูลค่าปลายทาง' — แก้ย้อนสองทิศก่อนอ้างสัดส่วนช่องว่าง",
        "2c (V23)     §9 ต้องมีหัวตารางดุลพินิจ ('ดุลพินิจ' + 'ทิศ' + 'IV' ในแถวหัวเดียวกัน)",
        "2c (V27)     §12 ต้องมีแถว 'NWC ต้นงวด' — DNWC ต้องแกะกลับได้ถึง NWC สองงวด",
        "",
        "--- V14(ก) (2026-10-10 — จากเมโม BWXT 2026-10-08) ---",
        "2c-v14a      §2 ต้องมีบรรทัด 'ตรวจผลตอบแทนส่วนเพิ่ม (V14ก): ROIC อดีตสูงสุด X% ·",
        "             ผลตอบแทนส่วนเพิ่มโดยนัยสูงสุดฉาก Base Y% · ทางที่เลือก: <ไม่เกิน|ลด Base|",
        "             §0 รองรับ|ลงทุนซ้ำ ≤ 0>' · Y > X → ต้อง '§0 รองรับ' และ §0 พูดถึง",
        "             'ผลตอบแทนส่วนเพิ่ม' · Y 'ไม่นิยาม' ↔ 'ลงทุนซ้ำ ≤ 0' · ถ้าตาราง Base มีคอลัมน์",
        "             'ผลตอบแทนส่วนเพิ่มโดยนัย' Y ต้องเท่าค่าสูงสุดของคอลัมน์ (±0.01)",
        "             ROIC อดีต X ตรวจย้อนไม่ได้ — วินัยเอเจนต์ · V24 ยังเป็นแค่ 'ตัวแปรตั้งต้น'",
        "             (ไม่มีรายการคำต้องห้าม เพราะ 'เป็นไปไม่ได้' ใช้ถูกได้เมื่อขัดข้อจำกัดจริง)",
        "",
        "--- V26 (2026-10-10 — จากเมโม META เลข 841) ---",
        "2c-v26       ทุกเลขในวงเล็บ (= ...) ของช่องตัวตั้ง/ตัวหาร ในตารางคำนวณ §12 ต้องปรากฏ",
        "             ที่อื่นในเมโมอย่างน้อยหนึ่งที่ (นอกแถวตัวเอง) — นับว่าเป็นเลขเดียวกันถ้า",
        "             ปัดเศษแล้วตรง · ×/÷100 · 1−x (0.8 = 1 − ภาษี 20%) · x−1 (1.14 = 1 + 14%)",
        "             ยกเว้นค่าคงที่ 0 · 1 · 2 · 100 · 1000 · 1000000",
        "             แบบหลวม: กันเลขลอยได้ แต่กันเลขที่โผล่ที่อื่นด้วยความบังเอิญไม่ได้",
        "",
        "--- V29 · V30 · V31 · V32 (2026-10-10) ---",
        "2c-v29       §5 ต้องมีบรรทัด 'ตัวคูณขาออกตามทฤษฎี (V29): <M>x (=<สูตรตัวเลข>)'",
        "             สูตรในวงเล็บถูกคิดซ้ำ ต้องได้ M (±0.01) · §5 ต้องมีคำว่า 'คนละระบอบ'",
        "             ไม่รู้ว่า g/ROIC/WACC ในสูตรตรงกับโมเดลไหม และไม่รู้ว่าการเทียบคู่เดียวกัน",
        "             ถูกใช้หนุนสองข้อสรุปสวนทางกันหรือเปล่า — ตัวหลักดูด้วยตา",
        "2c-v30       §5 ต้องมีบรรทัด 'หน่วยโมเดล (V30): <ตัวเงิน|แท้จริง> · เทียบ GDP",
        "             <ตัวเงิน|แท้จริง> X% · เพดาน Y% · g_term สูงสุด Z%' · หน่วยสองช่องต้องตรงกัน ·",
        "             Y ≤ X · Z ≤ Y · Z = ค่าสูงสุดของคอลัมน์ g_term ในตาราง §2 (±0.01) ถ้าหาเจอ",
        "             ไม่จับ 'เขียนเองว่ากฎให้ผลผิดหลักการแต่ยังใช้เป็นพาดหัว' — ตัวหลักดูด้วยตา",
        "2c-v31       ทุกวลี 'กระทบ(มูลค่า) ... X (USD) ต่อหุ้น' นอก §12 ต้องมีคำว่า 'อยู่ในฉากฐานแล้ว'",
        "             หรือ 'ส่วนเพิ่ม' ในบรรทัดเดียวกัน และ X ต้องอยู่ในคอลัมน์ผลของตารางคำนวณ (±0.01)",
        "             แบบแคบ: จับเฉพาะคำว่า 'กระทบ' — 'ลด/หัก/ราว X ต่อหุ้น' ไม่ถูกตรวจ",
        "2c-v32       บรรทัดที่มี 'เรียงตามขนาด/ผล' · 'มากไปน้อย' · 'น้อยไปมาก' + ลิสต์ (1)(2)…",
        "             หรือ bullet ในบรรทัดถัดไป → ค่า 'X USD' ตัวแรกของแต่ละข้อต้องเรียงตามที่ประกาศ",
        "             (ค่าสัมบูรณ์) · ลิสต์ที่อยู่ในตาราง ยังไม่ถูกตรวจ",
    ],
)
