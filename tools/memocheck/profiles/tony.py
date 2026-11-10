"""profiles/tony.py — สเปกเมโมของ 'โทนี่' (นักวิเคราะห์ตัวธุรกิจ สไตล์ Peter Lynch)

ค่าทุกตัวยกมาจาก tools/tony_check.py เดิมแบบเป๊ะ ๆ — ห้ามเปลี่ยนโดยไม่รันชุดทดสอบที่
scratch/tony-check-fixtures/ ซ้ำ
"""

from __future__ import annotations

from ..core import POST_FILING_LINE, Profile, TableSpec

SECTIONS = [
    (0, "THE STORY & LYNCH CATEGORY"),
    (1, "REVENUE BREAKDOWN"),
    (2, "REVENUE MODEL"),
    (3, "VALUE CHAIN & BARGAINING POWER"),
    (4, "OPERATING LEVERAGE"),
    (5, "CUSTOMER COHORT & RETENTION"),
    (6, "RISK FACTORS"),
    (7, "TONY'S TAKE"),
    (8, "PLAIN-LANGUAGE SUMMARY"),
    (9, "APPENDIX"),
]

PROFILE = Profile(
    slug="tony",
    tool_name="tony_check.py",
    required_yaml_fields=[
        "ticker", "company", "form", "fiscal_year", "accession", "filing_date",
        "as_of", "lynch_category", "revenue_total", "largest_segment",
        "price", "tiers_used", "exec_summary",
    ],
    # ฟิลด์ต้องห้าม — สกอร์ที่ไม่มีสูตรตายตัวคือตัวเลขมั่ว
    forbidden_yaml_fields=[
        "score", "conviction", "verdict", "rating", "recommendation",
        "target_price", "fair_value", "คะแนน",
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
            min_cols=5, max_cols=None,
            header_keys=("สูตร", "ตัวตั้ง"),
            kind="calc",
        ),
    ],
    opinion_sections=(0, 7),
    require_inference=False,
    # โทนี่เป็นตัวเดียวที่ §4 บังคับให้เทียบ operating leverage ข้ามปี — การปรับ
    # รายการครั้งเดียวข้างเดียวจึงพลิกข้อสรุปได้จริง (ดู check_paired_adjustment)
    paired_adjustment_check=True,
    rules_opinion_lines=[
        "2b-opinion   §0–§7 ทุกอันต้องมีบรรทัดที่ขึ้นต้นด้วย '(ความเห็น:' อยู่ในตัว section",
    ],
    rules_citation_lines=[
        "4-citation   ทุก 'แถว' ตารางนอก §9 ที่มีตัวเลขข้อเท็จจริง ต้องมี",
        "             [ฟอร์ม ... Item ...] หรือ [tier2]/[tier3] อยู่ในแถวนั้นเอง",
        "             ยกเว้น: เลขลำดับล้วน 1–2 หลัก (คอลัมน์ # ของ §6) และแถวที่มี",
        "             [ไม่เปิดเผย]/[ข้อมูลไม่พอ]",
    ],
    section_required_patterns={
        9: [POST_FILING_LINE],
    },
    rules_appendix_lines=[
        "7-appendix   §9 ต้องมี 2 ตาราง: ที่มา = 4 ช่อง (ตัวเลข|ฟอร์ม|งวด|Item)",
        "             และคำนวณ = 5 ช่อง (ชื่อ|สูตร|ตัวตั้ง|ตัวหาร|ผล) ห้ามมีช่องว่าง",
        "             + บรรทัด เหตุการณ์หลัง filing: <กระทบ|ไม่กระทบ|ไม่มี 8-K|ไม่มี 6-K> (2c-required-line)",
    ],
)
