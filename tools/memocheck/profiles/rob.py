"""profiles/rob.py — สเปกเมโมของ 'ร็อบ' (นักวิเคราะห์คูเมือง สไตล์ Morningstar Moat Rating)

ต่างจากโทนี่ 4 จุด:
  1. YAML มีคำตัดสิน moat_rating / moat_trend ได้ **แต่บังคับมีฟิลด์ _basis คู่กันเสมอ**
     — คำตัดสินที่ไม่มีที่อ้างอิงคือความรู้สึก ไม่ใช่ข้อสรุป
  2. §2 / §4 / §7 บังคับให้มีทั้งบรรทัด **Bull:** และ **Bear:** (กฎ 2c-required-line)
  3. ภาคผนวกมี 3 ตาราง — เพิ่ม 'ตารางคู่แข่ง' 6 ช่อง
  4. ตารางคำนวณล็อกไว้ที่ 5 ช่องพอดี (โทนี่/ทอมมุนเปิดปลาย) เพราะภาคผนวกจำแนกตาราง
     ด้วย 'จำนวนช่อง' — ปล่อยเปิดปลายเมื่อไหร่ ตารางคู่แข่ง 6 ช่องจะถูกกลืนเข้าตารางคำนวณ

ค่า moat_rating ที่แปลว่า 'ไม่มีคูเมือง' ต้องเขียนว่า `No Moat` เท่านั้น

  แก้ 2026-09-01 — docstring เดิมเขียนว่า "YAML อ่าน None เป็น null แล้วเครื่องตรวจจะนับว่า
  ฟิลด์ขาด" ซึ่ง **ผิดสองชั้น**: (ก) PyYAML อ่าน `None` เป็น *สตริง* 'None' ไม่ใช่ null
  (null คือ `null` / `Null` / `NULL` / `~` / ค่าว่างหลังโคลอนเท่านั้น) และ (ข) เครื่องตรวจ
  ตอนนั้นดูแค่ว่า 'มีคีย์ไหม' จึงไม่ได้ตรวจค่าอะไรเลย — `moat_rating: None` PASS เงียบ ๆ
  ตอนนี้ปิดสองทาง: enum_yaml_fields จับค่าที่ไม่อยู่ในรายการ (รวม 'None') และกฎค่าว่าง
  ในแกนจับ null/สตริงว่าง/list ว่างของทุกฟิลด์บังคับ
"""

from __future__ import annotations

from ..core import POST_FILING_LINE, Profile, TableSpec

SECTIONS = [
    (0, "THE ARENA"),
    (1, "MARKET SIZING & PROFIT POOL"),
    (2, "MOAT SOURCES"),
    (3, "PORTER'S 5 FORCES"),
    (4, "MOAT TREND"),
    (5, "PRICING POWER"),
    (6, "THREATS & VALUE MIGRATION"),
    (7, "ROB'S VERDICT"),
    (8, "PLAIN-LANGUAGE SUMMARY"),
    (9, "APPENDIX"),
]

# บรรทัด Bull / Bear — ต้องเขียนเป็นหัวข้อตัวหนาจริง ไม่ใช่คำว่า bull ที่โผล่ในเนื้อความ
_BULL = (r"\*\*Bull\s*[::]?\s*\*\*", "บรรทัด '**Bull:**' (ฝั่งที่บอกว่าคูเมืองแข็ง)")
_BEAR = (r"\*\*Bear\s*[::]?\s*\*\*", "บรรทัด '**Bear:**' (ฝั่งที่บอกว่าคูเมืองเปราะ)")

PROFILE = Profile(
    slug="rob",
    tool_name="rob_check.py",
    required_yaml_fields=[
        "ticker", "company", "form", "fiscal_year", "accession", "filing_date",
        "as_of", "moat_rating", "moat_rating_basis", "moat_trend", "moat_trend_basis",
        "moat_sources", "peers", "tam_usd", "tam_source", "tiers_used", "exec_summary",
    ],
    # สืบสายคะแนน/verdict จากโทนี่ + ปิดสายราคา/มูลค่าเหมือนทอมมุน
    # (ร็อบตัดสิน 'ความกว้างของคูเมือง' ไม่ใช่ 'ราคาหุ้น' — มีฟิลด์พวกนี้แปลว่าออกนอกขอบเขต)
    #
    # หมายเหตุ: การห้าม 'rating'/'verdict' เป็นการห้าม 'ชื่อฟิลด์นั้นตรง ๆ'
    # moat_rating / moat_trend เป็นคนละคีย์ จึงไม่ชนกัน — และทั้งคู่ถูกบังคับให้มี _basis คู่เสมอ
    forbidden_yaml_fields=[
        "score", "conviction", "verdict", "rating", "recommendation",
        "target_price", "fair_value", "คะแนน",
        "price", "market_cap", "pe", "pe_ratio", "ev_ebitda", "valuation",
    ],
    sections=SECTIONS,
    appendix_section=9,
    appendix_tables=[
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
        TableSpec(
            key="peer",
            label="ตารางคู่แข่ง (ticker | บริษัท | gross margin | งวด | ที่มา | เทียบได้ไหม)",
            short="ตารางคู่แข่ง",
            # ล็อก 6 ช่องพอดีด้วยเหตุผลเดียวกับ calc — ภาคผนวกจำแนกตารางด้วยจำนวนช่องล้วน ๆ
            # เปิดปลายไว้เมื่อไหร่ ตารางที่พิมพ์เกินเป็น 7 ช่องจะถูกกลืนมาเป็นตารางคู่แข่งเงียบ ๆ
            min_cols=6, max_cols=6,
            header_keys=("gross margin", "เทียบได้ไหม"),
        ),
    ],
    # §2 / §4 / §7 = สาม section ที่ร็อบ 'ตัดสิน' — บังคับให้เขียนสองฝั่งเสมอ
    # เครื่องตรวจไม่รู้ว่าเนื้อสองฝั่งสมดุลจริงไหม แต่รู้ได้ว่ามีหัวข้อทั้งสองฝั่งหรือเปล่า
    section_required_patterns={
        2: [_BULL, _BEAR],
        4: [_BULL, _BEAR],
        7: [_BULL, _BEAR],
        9: [POST_FILING_LINE],
    },
    # คำตัดสินสองตัวรับได้เฉพาะค่าในกรอบ Morningstar — พิมพ์ผิดแล้วเมโมยังดูปกติ จึงต้องล็อก
    enum_yaml_fields={
        "moat_rating": ("Wide", "Narrow", "No Moat"),
        "moat_trend": ("Positive", "Stable", "Negative"),
    },
    # พรอมต์บังคับคู่แข่งสามรายเพราะ 'การเลือกคู่แข่งคือการนิยามสนาม' — ต้องตรวจได้จริง
    list_len_yaml_fields={"peers": 3},
    opinion_sections=(0, 7),
    require_inference=False,
    rules_opinion_lines=[
        "2b-opinion   §0–§7 ทุกอันต้องมีบรรทัดที่ขึ้นต้นด้วย '(ความเห็น:' อยู่ในตัว section",
    ],
    rules_citation_lines=[
        "4-citation   ทุก 'แถว' ตารางนอก §9 ที่มีตัวเลขข้อเท็จจริง ต้องมี",
        "             [ฟอร์ม ... Item ...] หรือ [tier2]/[tier3] อยู่ในแถวนั้นเอง",
        "             ยกเว้น: เลขลำดับล้วน 1–2 หลัก และแถวที่มี [ไม่เปิดเผย]/[ข้อมูลไม่พอ]",
        "             ตัวเลขจาก WebSearch/เว็บ = [tier3] เสมอ ห้ามใส่เป็น [ฟอร์ม ... Item ...]",
    ],
    rules_appendix_lines=[
        "7-appendix   §9 ต้องมี 3 ตาราง: ที่มา = 4 ช่อง (ตัวเลข|ฟอร์ม|งวด|Item) ·",
        "             คำนวณ = 5 ช่องพอดี (ชื่อ|สูตร|ตัวตั้ง|ตัวหาร|ผล) ·",
        "             คู่แข่ง = 6 ช่อง (ticker|บริษัท|gross margin|งวด|ที่มา|เทียบได้ไหม)",
        "             ห้ามมีช่องว่าง — จำนวนช่องคือตัวจำแนกตาราง ผิดจำนวนจะถูกอ่านผิดกลุ่ม",
        "             + บรรทัด เหตุการณ์หลัง filing: <กระทบ|ไม่กระทบ|ไม่มี 8-K|ไม่มี 6-K> (2c-required-line)",
    ],
    rules_extra_lines=[
        "             วงเล็บ (= ...) คิดได้ทั้ง + − × ÷ และวงเล็บซ้อน",
        "             แถวที่ไม่ใช่การหาร (คูณ/บวก) ให้ใส่ตัวหาร = 1 แล้วผลเท่ากับตัวตั้ง",
        "1-yaml (ร็อบ) ไม่มีคูเมืองให้เขียน 'No Moat' — เขียน None จะถูกจับด้วยรายการ",
        "             ค่าที่ยอมรับข้างบน (PyYAML อ่าน None เป็นสตริง ไม่ใช่ null)",
        "             moat_rating_basis / moat_trend_basis บังคับมีและห้ามเว้นว่าง —",
        "             คำตัดสินต้องมีที่อ้าง เขียน \"\" เปล่า ๆ ไม่ผ่าน",
    ],
)
