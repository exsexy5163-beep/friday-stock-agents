#!/usr/bin/env python3
"""memocheck.core — แกนตรวจโครงสร้างเมโมของเอเจนต์ (ใช้ร่วมทุกเอเจนต์)

ตรวจ "โครงสร้าง" ไม่ตรวจ "น้ำเสียง" — คืน PASS หรือ FAIL พร้อมเหตุผลรายข้อ

logic ทั้งหมดในไฟล์นี้ย้ายมาจาก tools/tony_check.py (466 บรรทัด) โดยไม่เปลี่ยนพฤติกรรม
สิ่งที่ผูกกับเอเจนต์แต่ละตัว (รายชื่อ section · ฟิลด์ YAML · ตารางในภาคผนวก) ย้ายไป
อยู่ใน memocheck/profiles/<slug>.py แทน
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable

try:
    import yaml
except ModuleNotFoundError:
    sys.stderr.write(
        "FAIL ต้องรันด้วย __FRIDAY_ROOT__/.venv-utils/bin/python "
        "(interpreter ตัวนี้ไม่มี PyYAML)\n"
    )
    sys.exit(2)


# ---------------------------------------------------------------- โครง profile

@dataclass(frozen=True)
class TableSpec:
    """สเปกตารางหนึ่งตัวในภาคผนวก — จำแนกแถวด้วย 'จำนวนช่อง'"""
    key: str                      # ชื่อกลุ่ม (source | calc | assumption ...)
    label: str                    # ข้อความตอนรายงานว่าไม่พบตารางนี้
    short: str                    # ชื่อสั้น ใช้ตอนรายงานว่าแถวมีช่องว่าง
    min_cols: int
    max_cols: int | None          # None = ไม่จำกัด (>= min_cols)
    header_keys: tuple[str, ...]  # คำที่ต้องมีครบในแถวหัวตาราง
    kind: str = "plain"           # plain = ตรวจแค่ช่องว่าง, calc = คิดเลขซ้ำ
    required: bool = True

    def matches(self, ncols: int) -> bool:
        if ncols < self.min_cols:
            return False
        return self.max_cols is None or ncols <= self.max_cols


@dataclass(frozen=True)
class Profile:
    """ทุกอย่างที่ทำให้เครื่องตรวจ 'เป็นของเอเจนต์ตัวนี้'"""
    slug: str
    tool_name: str                       # ชื่อไฟล์ shim ที่ผู้ใช้เรียกจริง
    required_yaml_fields: list[str]
    forbidden_yaml_fields: list[str]
    sections: list[tuple[int, str]]
    appendix_section: int                # section ที่เป็นภาคผนวก (ยกเว้นกฎ citation)
    appendix_tables: list[TableSpec]
    opinion_sections: tuple[int, int]    # ช่วง section ที่บังคับบรรทัดปิดท้าย (รวมปลาย)
    require_inference: bool = False      # บังคับ '(อนุมาน: ...)' ด้วยไหม
    exec_summary_range: tuple[int, int] = (5, 7)
    assumption_table_key: str | None = None  # key ของ TableSpec ที่เก็บสมมติฐาน
    # บรรทัดที่ section หนึ่ง ๆ ต้องมี — {เลข section: [(regex, ชื่อที่แสดงตอน FAIL), ...]}
    # ใช้กับกฎที่ "เงื่อนไขจริงตรวจไม่ได้ แต่บังคับให้เขียนออกมาเสมอแล้วตรวจได้"
    # เช่น สัดส่วนเงินสดของทอมมุน: เครื่องตรวจไม่รู้ว่าเกิน 20% ไหม แต่รู้ว่ามีบรรทัดนั้นหรือเปล่า
    section_required_patterns: dict[int, list[tuple[str, str]]] = field(default_factory=dict)
    # ฟิลด์ YAML ที่รับได้เฉพาะค่าในชุดที่กำหนด — {ชื่อฟิลด์: (ค่าที่ยอมรับ, ...)}
    # ใช้กับฟิลด์ 'คำตัดสิน' ที่พิมพ์ผิดแล้วเมโมยังดูปกติ (เช่น moat_rating ของร็อบ)
    enum_yaml_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # ฟิลด์ YAML ที่ต้องเป็น list ยาวเท่านี้พอดี — {ชื่อฟิลด์: จำนวนรายการ}
    # ใช้กับกฎนับจำนวนที่พรอมต์บังคับไว้ (เช่น peers ของร็อบ = คู่แข่งสามรายพอดี)
    list_len_yaml_fields: dict[str, int] = field(default_factory=dict)
    # ข้ามการตรวจคำ verdict การลงทุนทั้งข้อ (กฎ 3-verdict) — เปิดให้เฉพาะ profile ที่ "งานคือ
    # การประเมินมูลค่า" (เดมอน) ซึ่งต้องพูดคำว่า intrinsic value / discount / premium / MoS เป็นปกติ
    # ⚠️ เปิดแล้ว "น่าซื้อ" / "แนะนำถือ" จะผ่านด้วย — วินัยข้อนี้เหลืออยู่ที่พรอมต์ (V13)
    #    กับบรรทัด DISCLAIMER บังคับใน section_required_patterns เท่านั้น
    skip_verdict_rule: bool = False
    # ธง [สมมติฐาน: ...] นับเป็น "ที่มา" ที่ถูกต้องของกฎ 4-citation ไหม
    # ตารางพยากรณ์อนาคตไม่มีที่มาจาก filing — การติด [tier3] ให้มันคือการโกหกว่ามีแหล่ง
    allow_assumption_citation: bool = False
    # ตรวจว่าคำตัดสินเชิงมูลค่าตรงกับช่วง IV จริงไหม — คิดซ้ำด้วย Decimal
    # (ฟิลด์คำตัดสิน, ฟิลด์ราคา, ฟิลด์ขอบล่าง, ฟิลด์ขอบบน, ค่าเมื่อต่ำกว่าช่วง, ค่าเมื่ออยู่ในช่วง, ค่าเมื่อสูงกว่าช่วง)
    stance_range_check: tuple[str, str, str, str, str, str, str] | None = None
    # ตรวจว่าธงเกณฑ์ตัวเลขตรงกับตัวเลขของตัวเอง และบรรทัดธงในเนื้อเมโมตรงกับ YAML (กฎ 1-yaml-flag)
    # ใช้กับทอมมุน: roic_wacc_flag ต้องตรงกับช่วงของ roic_wacc_spread (เพิ่ม 2026-09-23)
    threshold_flag_check: "ThresholdFlagCheck | None" = None
    # เปิดกฎ 10-adjust-pair + 11-adjust-period (ดู check_paired_adjustment)
    # ปิดไว้เป็นค่าเริ่มต้น — profile อื่นที่ไม่เคยปรับ one-off จะไม่ถูกกระทบ
    paired_adjustment_check: bool = False
    # คำที่ห้ามโผล่ในเมโม นอก section ที่ยกเว้น — [(regex, ชื่อที่แสดงตอน FAIL), ...] (กฎ 3b-forbidden)
    # ต่างจาก 3-verdict ตรงที่เป็นรายการของ profile เอง และยกเว้นบาง section ได้
    # Per-profile body bans; Tommun additionally opts into semantic CAPM checks.
    forbidden_body_patterns: list[tuple[str, str]] = field(default_factory=list)
    forbidden_body_exempt_sections: tuple[int, ...] = ()
    rules_opinion_lines: list[str] = field(default_factory=list)
    rules_citation_lines: list[str] = field(default_factory=list)
    rules_appendix_lines: list[str] = field(default_factory=list)
    rules_extra_lines: list[str] = field(default_factory=list)
    # Optional semantic validator; other profiles retain their exact behavior.
    semantic_check: Callable | None = None
    extra_citation_patterns: tuple[str, ...] = ()


def is_blank(value: object) -> bool:
    """ค่าที่ 'มีคีย์แต่ไม่มีเนื้อ' — นับว่าเท่ากับฟิลด์ขาด

    เหตุผล: YAML อ่าน `None` / `none` / `~` / ค่าว่างหลังโคลอน เป็น null ทั้งหมด
    การเช็คแค่ `key in meta` จึงปล่อยให้ฟิลด์คำตัดสินที่ว่างเปล่าผ่านไปได้
    (เคสจริง: `moat_rating: None` ของร็อบ และ `moat_rating_basis: ""`)
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


# ---------------------------------------------------------------- ค่าคงที่ร่วม

# บรรทัดบังคับในภาคผนวกของทุก profile (กฎ 2c-required-line) — เพิ่ม 2026-10-09 จากบทเรียน BWXT
# เมโมห้าใบยืนบน 10-K ที่ยื่นมา 7 เดือน ไม่มีใบไหนเห็น 8-K ที่ประกาศขายธุรกิจ
# เครื่องตรวจไม่รู้ว่าอ่านจริงไหม (นั่นคือหน้าที่ของ probe ในใบเสร็จ) แต่บังคับให้ "ประกาศผล" ได้
# คำสถานะต้องอยู่บรรทัดเดียวกับหัว — ใช้ [ \t] ไม่ใช่ \s กันการข้ามบรรทัด
POST_FILING_LINE = (
    r"เหตุการณ์หลัง filing(?:\*\*)?[ \t]*:[ \t]*(?:\*\*)?[ \t]*(?:ไม่กระทบ|กระทบ|ไม่มี 8-K|ไม่มี 6-K)",
    "บรรทัด 'เหตุการณ์หลัง filing: <กระทบ|ไม่กระทบ|ไม่มี 8-K|ไม่มี 6-K>'",
)

# คำ verdict การลงทุน (ไทย) — เก็บเป็น regex ไม่ใช่ substring ล้วน
#
# เหตุผล: ภาษาไทยไม่เว้นวรรคระหว่างคำ การจับ substring ตรง ๆ ทำให้เนื้อหาธุรกิจปกติ
# โดน FAIL ผิด ๆ — เคสจริงที่เจอตอนทดสอบ:
#   "เข้าซื้อกิจการ" (M&A)      · "สินค้าราคาถูก" (กลยุทธ์ราคา)
#   "หุ้นถูกซื้อคืน" (buyback)  ← "ถูก" เป็นคำแสดง passive ในภาษาไทย
# จึงผูกคำที่กำกวมเข้ากับ "สมอ" ที่ทำให้เป็นคำแนะนำลงทุนจริง ๆ เสมอ

# คำลงท้ายที่ยังนับเป็นคำเดิม (ใช้กับ _boundary)
_TAIL = r"(?:มาก|ที่สุด|กว่า|เกินไป|ไป|อยู่|ไว้|แล้ว|หุ้น|ตัวนี้)?"


def _boundary(phrase: str) -> str:
    """จับ phrase เมื่อจบวลีจริง ๆ — ไม่ใช่เมื่อมีคำไทยต่อท้ายจนความหมายเปลี่ยน
    เช่น 'ควรขาย' match แต่ 'ควรขายธุรกิจนี้ทิ้ง' (ความเห็นเชิงธุรกิจ) ไม่ match"""
    return phrase + _TAIL + r"(?![ก-๙])"


# กริยาที่ตามหลัง 'ถูก' แบบ passive — เจอแล้วแปลว่าไม่ใช่การบอกว่าหุ้นราคาถูก
_PASSIVE = (
    "ซื้อ|ขาย|จัด|ล็อก|โอน|ออก|เพิก|ระงับ|ปรับ|กำหนด|บันทึก|แปลง|ถือ|นับ|ใช้|ยึด|"
    "เรียก|เสนอ|ลด|เพิ่ม|จำกัด|นำ|แบ่ง|รวม|ตัด|เลือก|มอง|ประเมิน|ระบุ|กล่าว|"
    "วิจารณ์|ฟ้อง|สอบ|ตรวจ|ไล่|บังคับ|แทนที่|ทดแทน|เทรด|ระงับ"
)

# (regex, ชื่อที่จะแสดงตอน FAIL)
VERDICT_PATTERNS_TH: list[tuple[str, str]] = [
    (_boundary("น่าซื้อ"), "น่าซื้อ"),
    (_boundary("น่าขาย"), "น่าขาย"),
    (_boundary("น่าลงทุน"), "น่าลงทุน"),
    (_boundary("น่าสนใจลงทุน"), "น่าสนใจลงทุน"),
    (_boundary("ควรซื้อ"), "ควรซื้อ"),
    (_boundary("ควรขาย"), "ควรขาย"),
    (_boundary("ควรถือ"), "ควรถือ"),
    (_boundary("แนะนำซื้อ"), "แนะนำซื้อ"),
    (_boundary("แนะนำขาย"), "แนะนำขาย"),
    (_boundary("แนะนำถือ"), "แนะนำถือ"),
    (_boundary("ทยอยซื้อ"), "ทยอยซื้อ"),
    (_boundary("ไม่ควรลงทุน"), "ไม่ควรลงทุน"),
    (_boundary("คุ้มที่จะลงทุน"), "คุ้มที่จะลงทุน"),
    # 'เข้าซื้อ' ต้องมีสมอ ไม่งั้นชน 'เข้าซื้อกิจการ' (M&A) ซึ่งเป็นเนื้อหาปกติของ §0/§1/§3
    (r"น่าเข้าซื้อ", "น่าเข้าซื้อ"),
    (r"ควรเข้าซื้อ", "ควรเข้าซื้อ"),
    (r"ทยอยเข้าซื้อ", "ทยอยเข้าซื้อ"),
    (r"(?:จังหวะ|จุด)เข้าซื้อ", "จังหวะ/จุดเข้าซื้อ"),
    (r"เข้าซื้อสะสม", "เข้าซื้อสะสม"),
    (r"ควรเข้าลงทุน", "ควรเข้าลงทุน"),
    (r"ควรออกจาก(?:หุ้น|การลงทุน)", "ควรออกจากหุ้น/การลงทุน"),
    (r"ควรหลีกเลี่ยงหุ้น", "ควรหลีกเลี่ยงหุ้น"),
    # 'ถูก/แพง' ต้องผูกกับ 'หุ้น' ไม่ใช่ราคาสินค้า และต้องไม่ใช่ passive 'ถูก+กริยา'
    # (?<!ผู้ถือ) กัน false positive กับ "ผู้ถือหุ้นถูก…" (ประโยคปกติของงานธรรมาภิบาล
    # เช่น "ผู้ถือหุ้นถูกเจือจางสิทธิ") — ยังจับ "เขาถือหุ้นถูกกว่าราคาตลาด" ได้ตามเดิม
    (r"(?<!ผู้ถือ)หุ้นถูก(?!" + _PASSIVE + r")", "หุ้นถูก (ราคาหุ้น)"),
    (r"หุ้นราคาถูก", "หุ้นราคาถูก"),
    # (?<!ผู้ถือ) เหตุผลเดียวกับ 'หุ้นถูก' — "ผู้ถือหุ้นแพง…" ไม่ใช่คำตัดสินราคาหุ้น
    (r"(?<!ผู้ถือ)หุ้นแพง", "หุ้นแพง"),
    (r"หุ้นราคาแพง", "หุ้นราคาแพง"),
    (r"ราคาเป้าหมาย", "ราคาเป้าหมาย"),
    (r"มูลค่าเหมาะสม", "มูลค่าเหมาะสม"),
    (r"ราคาที่เหมาะสม", "ราคาที่เหมาะสม"),
    (r"ราคา(?:ต่ำ|สูง)กว่ามูลค่าที่แท้จริง", "ราคาต่ำ/สูงกว่ามูลค่าที่แท้จริง"),
    (r"ซื้อดีไหม", "ซื้อดีไหม"),
]
# คำอังกฤษ — จับแบบมีขอบเขตคำ
VERDICT_TERMS_EN = [
    "target price", "price target", "fair value", "upside", "downside",
    "overweight", "underweight", "buy rating", "sell rating",
    "undervalued", "overvalued", "strong buy",
]

PAGE_CITE_PATTERNS = [
    # คำประสมที่มี 'หน้า' แต่ไม่ใช่เลขหน้า: ล่วงหน้า 8 สัปดาห์ · ปีก่อนหน้า 2025 · ข้างหน้า · เบื้องหน้า
    (r"(?<!ล่วง)(?<!ก่อน)(?<!ข้าง)(?<!เบื้อง)หน้า\s*\d+", "อ้าง 'หน้า <เลข>'"),
    # (?<![A-Za-z]\.) กันตัวย่อ 'L.P. 32,010' (ห้างหุ้นส่วน) ไม่ให้อ่านเป็น 'p. 32'
    (r"(?<![A-Za-z]\.)\bp\.\s?\d+", "อ้าง 'p.<เลข>'"),
    (r"\bpage\s+\d+", "อ้าง 'page <เลข>'"),
    (r"\bpp\.\s?\d+", "อ้าง 'pp.<เลข>'"),
]

CITATION_RE = re.compile(r"\[[^\]]*Item[^\]]*\]", re.IGNORECASE)
TIER_RE = re.compile(r"\[tier[23]\]", re.IGNORECASE)
MISSING_FLAG_RE = re.compile(r"\[(ไม่เปิดเผย|ข้อมูลไม่พอ)\]")
LEFTOVER_RE = re.compile(r"\[ยังไม่มีข้อมูล\]")
ASSUMPTION_RE = re.compile(r"\[สมมติฐาน\s*:")

HEADING_RE = re.compile(r"^#{1,6}\s*§\s*(\d+)\s+(.+?)\s*$")


# ---------------------------------------------------------------- helpers

def split_front_matter(text: str) -> tuple[str | None, str]:
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", text, re.DOTALL)
    if not m:
        return None, text
    return m.group(1), m.group(2)


def table_rows(lines: list[str]) -> list[tuple[int, list[str], bool]]:
    """คืน (เลขบรรทัด, cells, เป็นแถวหัวตารางไหม) ของแถวตาราง markdown ที่ไม่ใช่ separator

    แถวหัวตาราง = แถวที่อยู่ 'เหนือเส้นคั่น' ตามนิยามของ markdown — เป็นชื่อคอลัมน์
    ไม่ใช่ข้อเท็จจริง จึงไม่ต้องมีที่มา (หัวตารางแบบ 'FY2025' มีตัวเลขอยู่ในตัวเสมอ)"""
    out: list[list] = []
    for i, ln in enumerate(lines, start=1):
        s = ln.strip()
        if not (s.startswith("|") and s.endswith("|") and s.count("|") >= 3):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            if out and out[-1][0] == i - 1:
                out[-1][2] = True  # แถวก่อนหน้าคือหัวตาราง
            continue  # separator
        out.append([i, cells, False])
    return [(i, cells, head) for i, cells, head in out]


NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def strip_citations(cell: str) -> str:
    return re.sub(r"\[[^\]]*\]", " ", cell)


def first_number(cell: str) -> Decimal | None:
    m = NUM_RE.search(strip_citations(cell))
    if not m:
        return None
    try:
        return Decimal(m.group(0).replace(",", ""))
    except InvalidOperation:
        return None


def has_number(cell: str) -> bool:
    return first_number(cell) is not None


# เลขลำดับ (คอลัมน์ '#' ของตารางจัดอันดับ) ไม่ใช่ข้อเท็จจริงจากงบ จึงไม่ต้องมีที่มา
RANK_RE = re.compile(r"^#?\d{1,2}$")


def is_rank_cell(cell: str) -> bool:
    return bool(RANK_RE.fullmatch(strip_citations(cell).strip()))


def is_fact_number(cell: str) -> bool:
    """ช่องที่มี 'ตัวเลขข้อเท็จจริง' — ตัดเลขลำดับล้วนออก"""
    return has_number(cell) and not is_rank_cell(cell)


# ตัวเลขที่ได้จากการคำนวณ เขียนเป็น  10,000 (=110,000−100,000)  แล้วเครื่องตรวจเลขในวงเล็บให้
#
# รองรับ + − × ÷ และวงเล็บซ้อน เพราะสูตรจริงบางตัวไม่ใช่การหารชั้นเดียว —
# เช่น NOPAT = operating income × (1 − อัตราภาษีจริง) หรือ invested capital ที่บวกกัน 3 ก้อน
_DERIV_START = re.compile(r"\(\s*=\s*")
_DERIV_CHARS = set("0123456789,._-−+×÷*/x() ")
_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?|[-−+×÷*/x()]")


def _derivation_expr(cell: str) -> str | None:
    """ดึงข้อความในวงเล็บ (= ... ) โดยนับวงเล็บให้สมดุล — คืน None ถ้าไม่ใช่นิพจน์เลขล้วน"""
    m = _DERIV_START.search(cell)
    if not m:
        return None
    depth = 0
    for j in range(m.start(), len(cell)):
        if cell[j] == "(":
            depth += 1
        elif cell[j] == ")":
            depth -= 1
            if depth == 0:
                inner = cell[m.end():j]
                if not inner.strip() or any(ch not in _DERIV_CHARS for ch in inner):
                    return None
                return inner
    return None


def _eval_expr(expr: str) -> Decimal | None:
    """คิดนิพจน์เลขด้วย Decimal — × ÷ ก่อน + − · รองรับวงเล็บ · คืน None ถ้านิพจน์ไม่สมบูรณ์"""
    toks = _TOKEN_RE.findall(expr)
    if not toks:
        return None
    pos = 0

    def peek() -> str | None:
        return toks[pos] if pos < len(toks) else None

    def atom() -> Decimal:
        nonlocal pos
        t = peek()
        if t in ("-", "−", "+"):
            pos += 1
            v = atom()
            return -v if t != "+" else v
        if t == "(":
            pos += 1
            v = expression()
            if peek() != ")":
                raise ValueError("วงเล็บไม่ปิด")
            pos += 1
            return v
        if t is None or not t[0].isdigit():
            raise ValueError(f"คาดว่าเป็นตัวเลข แต่พบ {t!r}")
        pos += 1
        return Decimal(t.replace(",", ""))

    def term() -> Decimal:
        nonlocal pos
        v = atom()
        while peek() in ("×", "x", "*", "÷", "/"):
            op = toks[pos]
            pos += 1
            rhs = atom()
            if op in ("÷", "/"):
                if rhs == 0:
                    raise ZeroDivisionError
                v = v / rhs
            else:
                v = v * rhs
        return v

    def expression() -> Decimal:
        nonlocal pos
        v = term()
        while peek() in ("+", "-", "−"):
            op = toks[pos]
            pos += 1
            rhs = term()
            v = v + rhs if op == "+" else v - rhs
        return v

    try:
        value = expression()
    except (ValueError, ZeroDivisionError, InvalidOperation):
        return None
    if pos != len(toks):
        return None
    return value


def derivation_mismatch(cell: str) -> tuple[Decimal, Decimal] | None:
    """คืน (ค่าที่ควรเป็น, ค่าที่เขียนไว้) ถ้านิพจน์ในวงเล็บ (= ...) ไม่ตรงกับตัวเลขนำหน้า

    เผื่อการปัดเศษให้เท่ากับหลักทศนิยมที่เขียนไว้จริง — เขียน 93,187 จาก 93,187.06 ผ่านได้
    แต่เขียนผิดจริง ๆ ยังจับได้เหมือนเดิม"""
    plain = strip_citations(cell)
    expr = _derivation_expr(plain)
    if expr is None:
        return None
    want = _eval_expr(expr)
    if want is None:
        return None
    got = first_number(cell)
    if got is None:
        return want, Decimal(0)
    txt = NUM_RE.search(strip_citations(cell)).group(0).replace(",", "")
    decimals = len(txt.split(".")[1]) if "." in txt else 0
    tol = Decimal(1).scaleb(-decimals) / 2 + Decimal(1).scaleb(-(decimals + 6))
    if abs(want - got) > tol:
        return want, got
    return None


# ---------------------------------------------- กฎ 10/11: การปรับรายการครั้งเดียว
#
# ที่มาของกฎ (เคสจริง TER FY2025 ของโทนี่ 2026-09-02):
# เมโมถอด "กำไรจากการขายธุรกิจ 57.1" ออกจากฐาน FY2024 เพื่อคิด incremental margin
# FY2025 ใหม่ได้ 30.63% แต่ปล่อยแถว incremental margin FY2024 ไว้ที่ 64.58% ซึ่งยัง
# มี 57.1 ก้อนเดิมปนอยู่ แล้วเอาสองแถวคนละฐานมาเทียบกันในเนื้อเมโม — พอปรับให้ครบ
# ทั้งสองปี ตัวเลขกลับด้าน (24.81% → 30.63% = ดีขึ้น ไม่ใช่แย่ลง) ข้อสรุปของ §4 จึงผิด
# เครื่องตรวจเดิมมองไม่เห็น เพราะทุกแถวคิดซ้ำแล้วตรงสูตรหมด

_ADJ_NAME_RE = re.compile(r"ถอด|ที่ปรับ|ปรับแล้ว|ปรับฐาน|ไม่รวม|adjusted|ex-one-off", re.I)
_FY_RE = re.compile(r"FY\s?(\d{4})")


def _cell_operands(cell: str) -> set[Decimal]:
    """ตัวเลขที่ช่องนี้ 'ใช้' — มีวงเล็บ (= ...) เอาตัวในวงเล็บ ไม่เอาผลลัพธ์นำหน้า"""
    expr = _derivation_expr(strip_citations(cell))
    if expr:
        out = set()
        for t in NUM_RE.findall(expr):
            try:
                out.add(abs(Decimal(t.replace(",", ""))))
            except InvalidOperation:
                pass
        return out
    v = first_number(cell)
    return {abs(v)} if v is not None else set()


def _cell_numbers(cell: str) -> set[Decimal]:
    """ตัวเลขทุกตัวในช่อง (รวมผลลัพธ์นำหน้า) — ใช้จับคู่กับตารางที่มา"""
    out = set()
    for t in NUM_RE.findall(strip_citations(cell)):
        try:
            out.add(abs(Decimal(t.replace(",", ""))))
        except InvalidOperation:
            pass
    return out


def check_paired_adjustment(calc_rows, source_rows, fail) -> None:
    """กฎ 10 + 11 — ปรับรายการครั้งเดียวแล้วต้องปรับให้ครบ และต้องปรับให้ถูกปี

    calc_rows   : [(ln_no, ชื่อ, ช่องตัวตั้ง, ช่องตัวหาร)]
    source_rows : [(ln_no, ช่องตัวเลข, ช่องงวด)]

    'แถวปรับฐาน' = แถวที่ชื่อมีคำว่าถอด/ปรับ · ตัวตั้งเป็นการลบในวงเล็บ · และผลลัพธ์
    ของมันถูกเอาไปใช้ต่อในแถวอื่น (ถ้าไม่ถูกใช้ต่อ แปลว่าเป็นแค่ผลต่าง ไม่ใช่ฐานใหม่)
    """
    parsed = []
    for ln_no, name, numer, denom in calc_rows:
        parsed.append({
            "ln": ln_no,
            "name": name,
            "result": abs(first_number(numer)) if first_number(numer) is not None else None,
            "uses": _cell_operands(numer) | _cell_operands(denom),
            "denom": first_number(denom),
            "expr_ops": [
                abs(Decimal(t.replace(",", "")))
                for t in NUM_RE.findall(_derivation_expr(strip_citations(numer)) or "")
            ],
        })

    for adj in parsed:
        if not _ADJ_NAME_RE.search(adj["name"]):
            continue
        if len(adj["expr_ops"]) != 2 or adj["result"] is None:
            continue
        orig, removed = adj["expr_ops"]
        adjusted = adj["result"]
        # ผลลัพธ์ต้องถูกใช้ต่อที่อื่น ถึงจะนับว่าเป็น 'ฐานใหม่' ไม่ใช่ผลต่างธรรมดา
        if not any(r is not adj and adjusted in r["uses"] for r in parsed):
            continue

        # --- กฎ 10: ทุกแถวที่ยังใช้ฐานเดิม ต้องมีคู่ที่ใช้ฐานที่ปรับแล้ว (ตัวหารเดียวกัน)
        for row in parsed:
            if row is adj or orig not in row["uses"]:
                continue
            # แถวคู่ = แถวที่ *ใช้* ฐานที่ปรับแล้ว หรือ *ผลิต* มันออกมา (แถวปรับฐานเอง
            # คือแถวคู่ของ 'op margin ปีเดียวกัน' อยู่แล้ว) โดยต้องหารด้วยตัวหารเดียวกัน
            twin = any(
                r is not row
                and (adjusted in r["uses"] or r["result"] == adjusted)
                and r["denom"] == row["denom"]
                for r in parsed
            )
            if not twin:
                fail(
                    "10-adjust-pair",
                    f"บรรทัด {row['ln']} ({row['name']}): ยังใช้ฐานเดิม {orig} "
                    f"ทั้งที่บรรทัด {adj['ln']} ({adj['name']}) ถอดรายการครั้งเดียว "
                    f"{removed} ออกไปแล้วได้ {adjusted} — ต้องมีแถวคู่ที่คิดค่าเดียวกัน "
                    f"บนฐาน {adjusted} (ตัวหาร {row['denom']}) ด้วย มิฉะนั้นเนื้อเมโม "
                    f"จะเอาสองปีคนละฐานมาเทียบกัน",
                )

        # --- กฎ 11: ปีของรายการที่ถอดออก ต้องตรงกับปีที่ระบุในชื่อแถวปรับฐาน
        fy = _FY_RE.search(adj["name"])
        if not fy or not source_rows:
            continue
        want = fy.group(1)
        hits = []
        for ln_no, num_cell, period_cell in source_rows:
            vals = _cell_numbers(num_cell)
            if any(
                v == removed or v * 1000 == removed or v == removed * 1000
                for v in vals
            ):
                hits.append((ln_no, period_cell))
        if hits and not any(want in p for _, p in hits):
            where = " · ".join(f"บรรทัด {n} งวด '{p}'" for n, p in hits)
            fail(
                "11-adjust-period",
                f"บรรทัด {adj['ln']} ({adj['name']}): ถอดรายการ {removed} ออกจากฐาน "
                f"FY{want} แต่ตารางที่มาระบุรายการนั้นเป็นคนละงวด ({where}) — "
                f"คอลัมน์ 'งวด' คือปีบัญชีที่ตัวเลขเกิด ไม่ใช่ปีของ filing ที่ไปอ่านมา",
            )


def yaml_decimal(value: object) -> Decimal | None:
    """แปลงค่าจาก YAML เป็น Decimal — รับทั้งตัวเลขและสตริงที่มีสัญลักษณ์เงิน/คอมมา

    คืน None ถ้าแปลงไม่ได้ (ผู้เรียกเป็นคนตัดสินว่าจะ FAIL ด้วยข้อความอะไร)
    ตั้งใจ **ไม่** ใช้ float เป็นทางผ่าน — ค่าที่ YAML อ่านเป็น float แล้วจะเพี้ยนตั้งแต่ต้นทาง
    จึงแปลงผ่าน repr ของมันด้วย Decimal(str(...)) ซึ่งได้ค่าที่ "เขียนไว้" ไม่ใช่ค่าไบนารี
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        cleaned = re.sub(r"[^\d.\-]", "", value.replace("−", "-"))
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned or ""):
            return None
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


@dataclass
class ThresholdFlagCheck:
    """สเปกของกฎ 1-yaml-flag — ธงที่ตัดสินจากตัวเลขด้วยเกณฑ์คงที่

    bands เรียงจากสูงไปต่ำ: (ขอบล่าง, รวมขอบไหม, ค่าธง) · ขอบล่าง None = ที่เหลือทั้งหมด
    ตัวเลขเขียนเป็น [ข้อมูลไม่พอ] (แปลงเป็นเลขไม่ได้) → ธงต้องเป็น na_value
    """
    flag_field: str
    number_field: str
    bands: list[tuple[Decimal | None, bool, str]]
    na_value: str
    section: int              # section ที่มีบรรทัดธง
    line_regex: str           # group 1 = ระดับ · group 2 (ถ้ามี) = ตัวเลขในบรรทัด


def check_threshold_flag(meta: dict, profile: Profile, lines: list[str],
                         heads: list[tuple[int, int]], fail) -> None:
    """คิดซ้ำว่าธงตรงกับเกณฑ์ และบรรทัดธงในเนื้อเมโมตรงกับ YAML (กฎ 1-yaml-flag)

    เหตุผล: ธงคือผลลัพธ์หลักที่ผู้อ่านเห็น — จัดระดับผิด หรือหัวเมโมกับเนื้อขัดกัน
    แล้วผ่านเครื่องตรวจ คือเมโมที่เถียงกับตัวเองโดยไม่มีใครรู้ (เจอจาก /scrutinize 2026-09-23)
    """
    spec = profile.threshold_flag_check
    flag = meta.get(spec.flag_field)
    flag = flag.strip() if isinstance(flag, str) else flag
    num_raw = meta.get(spec.number_field)
    have_yaml = not (spec.flag_field not in meta or is_blank(flag)
                     or spec.number_field not in meta or is_blank(num_raw))
    num = yaml_decimal(num_raw) if have_yaml else None

    if have_yaml:
        if num is None:
            want = spec.na_value
        else:
            want = None
            for lo, inclusive, value in spec.bands:
                if lo is None or num > lo or (inclusive and num == lo):
                    want = value
                    break
        if flag != want:
            shown = num if num is not None else f"'{num_raw}' (คำนวณไม่ได้)"
            fail("1-yaml-flag",
                 f"{spec.flag_field} = '{flag}' แต่ {spec.number_field} = {shown} "
                 f"ตามเกณฑ์ต้องเป็น '{want}'")

    # บรรทัดธงในเนื้อเมโมต้องพูดระดับเดียวกับ YAML (และตัวเลขเดียวกันถ้ามี)
    pos = next((i for i, (n, _) in enumerate(heads) if n == spec.section), None)
    if pos is None:
        return  # §ขาด — ข้อ 2 รายงานไปแล้ว
    start = heads[pos][1]
    end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
    rx = re.compile(spec.line_regex)
    for i in range(start, end):
        m = rx.search(lines[i])
        if not m:
            continue
        if have_yaml and m.group(1) != flag:
            fail("1-yaml-flag",
                 f"บรรทัดธง §{spec.section} (บรรทัด {i + 1}) เขียน '{m.group(1)}' "
                 f"แต่ YAML {spec.flag_field} = '{flag}'")
        if have_yaml and num is not None and rx.groups >= 2 and m.group(2):
            line_num = yaml_decimal(m.group(2))
            if line_num is not None and line_num != num:
                fail("1-yaml-flag",
                     f"บรรทัดธง §{spec.section} (บรรทัด {i + 1}) เขียนตัวเลข {m.group(2)} "
                     f"แต่ YAML {spec.number_field} = {num}")
        return  # ตรวจบรรทัดธงแรกพอ — การไม่มีบรรทัดเลย กฎ 2c รายงานเอง


def check_stance_range(meta: dict, profile: Profile, fail) -> None:
    """คิดซ้ำว่าคำตัดสินเชิงมูลค่าตรงกับ 'ราคาเทียบช่วง IV' จริงไหม (กฎ 1-yaml-stance)

    เหตุผลที่ต้องคิดซ้ำ: เดมอนปิดกฎ 3-verdict ทั้งข้อ ฟิลด์คำตัดสินจึงเป็นจุดเดียวที่
    เครื่องตรวจยังจับ 'ข้อสรุปที่ขัดกับตัวเลขของตัวเอง' ได้ — เขียน Premium ทั้งที่ราคาต่ำกว่า
    ขอบล่างของช่วง คือเมโมที่เถียงกับตัวเองแล้วผู้อ่านไม่มีทางรู้
    """
    f_stance, f_price, f_lo, f_hi, v_lo, v_mid, v_hi = profile.stance_range_check
    for fname in (f_stance, f_price, f_lo, f_hi):
        if fname not in meta or is_blank(meta[fname]):
            return  # ฟิลด์ขาด/ว่าง — กฎฟิลด์บังคับรายงานไปแล้ว ไม่ซ้ำ
    stance = meta[f_stance]
    stance = stance.strip() if isinstance(stance, str) else stance
    if stance not in (v_lo, v_mid, v_hi):
        if f_stance not in profile.enum_yaml_fields:
            fail("1-yaml-stance",
                 f"{f_stance} ต้องเป็น {v_lo} | {v_mid} | {v_hi} — พบ '{stance}'")
        return  # ค่านอกชุด — enum รายงานไปแล้ว เทียบช่วงต่อไม่มีความหมาย
    nums: dict[str, Decimal] = {}
    for fname in (f_price, f_lo, f_hi):
        num = yaml_decimal(meta[fname])
        if num is None:
            fail("1-yaml-stance",
                 f"{fname} ต้องเป็นตัวเลข (เครื่องตรวจต้องคิดซ้ำว่า {f_stance} ตรงกับช่วง) "
                 f"— พบ '{meta[fname]}'")
            return
        nums[fname] = num
    price, lo, hi = nums[f_price], nums[f_lo], nums[f_hi]
    if lo > hi:
        fail("1-yaml-stance",
             f"{f_lo} ({lo}) มากกว่า {f_hi} ({hi}) — ช่วงมูลค่ากลับหัว "
             f"ขอบล่างต้องไม่เกินขอบบน")
        return
    if price < lo:
        want = v_lo
    elif price > hi:
        want = v_hi
    else:
        want = v_mid
    if stance != want:
        fail("1-yaml-stance",
             f"{f_stance} เขียนว่า '{stance}' แต่คิดซ้ำจาก {f_price}={price} เทียบช่วง "
             f"{f_lo}={lo}–{f_hi}={hi} ได้ '{want}' "
             f"(ต่ำกว่าช่วง={v_lo} · อยู่ในช่วง={v_mid} · สูงกว่าช่วง={v_hi})")


# ---------------------------------------------------------------- ตัวตรวจ

STDIN_PATH = "-"          # path พิเศษ = อ่านเมโมจาก stdin (ให้เอเจนต์ที่ไม่มีสิทธิเขียนไฟล์ตรวจร่างได้)
STDIN_LABEL = "<stdin>"   # ชื่อที่พิมพ์ในบรรทัด PASS/FAIL แทน '-'


def read_stdin_memo() -> str | None:
    """อ่านเมโมจาก stdin เป็น UTF-8 แบบเดียวกับ open() — แปลง \\r\\n · \\r เป็น \\n
    คืน None ถ้าอ่านไม่ได้ (เขียนเหตุผลลง stderr แล้ว)"""
    stream = sys.stdin
    if stream is None or stream.isatty():
        sys.stderr.write("FAIL ไม่มีเมโมส่งเข้า stdin — ใช้แบบ  ... <<'EOF' หรือ  cat ร่าง | ...\n")
        return None
    try:
        raw = stream.buffer.read() if hasattr(stream, "buffer") else stream.read()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"FAIL อ่าน stdin ไม่ได้: {exc}\n")
        return None
    if not text.strip():
        sys.stderr.write("FAIL stdin ว่าง — ไม่มีเมโมให้ตรวจ\n")
        return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def check_memo(path: str, profile: Profile) -> tuple[int, list[str]]:
    """คืน (exit code, รายการเหตุผล FAIL) — 0 = PASS, 1 = FAIL, 2 = อ่านไฟล์ไม่ได้
    path = '-' → อ่านจาก stdin"""
    failures: list[str] = []

    def fail(check: str, detail: str) -> None:
        failures.append(f"[{check}] {detail}")

    if path == STDIN_PATH:
        stdin_text = read_stdin_memo()
        if stdin_text is None:
            return 2, failures
        text = stdin_text
    else:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            sys.stderr.write(f"FAIL อ่านไฟล์ไม่ได้: {exc}\n")
            return 2, failures

    lines = text.splitlines()
    heading_re = HEADING_RE
    sections = profile.sections

    # ---- 1. YAML header ------------------------------------------------
    raw_yaml, body = split_front_matter(text)
    meta = {}
    if raw_yaml is None:
        fail("1-yaml", "ไม่พบ YAML header (ต้องเปิดไฟล์ด้วย --- และปิดด้วย ---)")
    else:
        try:
            meta = yaml.safe_load(raw_yaml) or {}
        except yaml.YAMLError as exc:
            fail("1-yaml", f"YAML header parse ไม่ผ่าน: {exc}")
            meta = {}
        if not isinstance(meta, dict):
            fail("1-yaml", "YAML header ไม่ใช่ mapping")
            meta = {}
        missing = [f for f in profile.required_yaml_fields if f not in meta]
        if missing:
            fail("1-yaml", "ฟิลด์บังคับขาด: " + ", ".join(missing))
        blank = [f for f in profile.required_yaml_fields
                 if f in meta and is_blank(meta[f])]
        if blank:
            fail("1-yaml",
                 "ฟิลด์บังคับมีคีย์แต่ค่าว่าง (null / สตริงว่าง / list ว่าง): "
                 + ", ".join(blank))
        for fname, allowed in profile.enum_yaml_fields.items():
            val = meta.get(fname)
            if fname not in meta or is_blank(val):
                continue  # รายงานไปแล้วในข้อขาด/ว่าง ไม่ซ้ำ
            if not isinstance(val, str) or val.strip() not in allowed:
                fail("1-yaml",
                     f"{fname} ต้องเป็นค่าใดค่าหนึ่งใน {' | '.join(allowed)} — พบ '{val}'")
        if profile.stance_range_check:
            check_stance_range(meta, profile, fail)
        for fname, want in profile.list_len_yaml_fields.items():
            val = meta.get(fname)
            if fname not in meta or is_blank(val):
                continue
            if not isinstance(val, list):
                fail("1-yaml", f"{fname} ต้องเป็น list {want} รายการ")
            elif len(val) != want:
                fail("1-yaml", f"{fname} ต้องมี {want} รายการพอดี — พบ {len(val)}")
        present_forbidden = [f for f in profile.forbidden_yaml_fields if f in meta]
        if present_forbidden:
            fail("1-yaml", "มีฟิลด์คะแนน/verdict ที่ห้ามมี: " + ", ".join(present_forbidden))
        summary = meta.get("exec_summary")
        lo, hi = profile.exec_summary_range
        if summary is None:
            pass  # นับเป็น missing ไปแล้ว
        elif not isinstance(summary, list):
            fail("1-yaml", "exec_summary ต้องเป็น list")
        elif not (lo <= len(summary) <= hi):
            fail("1-yaml", f"exec_summary ต้องมี {lo}–{hi} รายการ (พบ {len(summary)})")

    # ---- 2. section ครบและเรียงลำดับ -----------------------------------
    found: list[tuple[int, int]] = []  # (เลข section, ลำดับที่เจอ)
    seen: dict[int, str] = {}
    for ln in lines:
        m = heading_re.match(ln.strip())
        if m:
            num = int(m.group(1))
            seen.setdefault(num, m.group(2).strip())
            found.append((num, len(found)))
    for num, title in sections:
        if num not in seen:
            fail("2-sections", f"ไม่พบหัวข้อ §{num} {title}")
        else:
            got = seen[num].upper().replace("’", "'")
            if title.upper() not in got:
                fail("2-sections", f"§{num} ชื่อหัวข้อไม่ตรง — คาด '{title}' พบ '{seen[num]}'")
    last_section = sections[-1][0]
    order = [n for n, _ in found if n in dict(sections)]
    if order != sorted(order) or len(set(order)) != len(order):
        fail("2-sections", f"ลำดับ section ไม่เรียง 0→{last_section}: {order}")

    # ---- 2b. section เนื้อหาต้องปิดท้ายด้วย (อนุมาน:) / (ความเห็น: ...) --
    heads: list[tuple[int, int]] = []  # (เลข section, index บรรทัด)
    for idx, ln in enumerate(lines):
        m = heading_re.match(ln.strip())
        if m:
            heads.append((int(m.group(1)), idx))
    op_lo, op_hi = profile.opinion_sections
    for pos, (num, start) in enumerate(heads):
        if num < op_lo or num > op_hi:
            continue
        end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
        chunk = lines[start:end]
        if profile.require_inference and not any("(อนุมาน:" in l for l in chunk):
            fail("2b-opinion", f"§{num} ไม่มีบรรทัด '(อนุมาน: ...)' ปิดท้าย")
        if not any("(ความเห็น:" in l for l in chunk):
            fail("2b-opinion", f"§{num} ไม่มีบรรทัด '(ความเห็น: ...)' ปิดท้าย")

    # ---- 2c. บรรทัดบังคับรายsection (section_required_patterns) --------
    if profile.section_required_patterns:
        seen_nums = {n for n, _ in heads}
        for num, patterns in sorted(profile.section_required_patterns.items()):
            if num not in seen_nums:
                continue  # §ขาดไปเลย — ข้อ 2 รายงานไปแล้ว ไม่ต้องซ้ำ
            pos = next(i for i, (n, _) in enumerate(heads) if n == num)
            start = heads[pos][1]
            end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
            chunk = "\n".join(lines[start:end])
            for pat, label in patterns:
                if not re.search(pat, chunk):
                    fail("2c-required-line", f"§{num} ไม่มี{label}")

    # ---- 2d. ธงเกณฑ์ตัวเลข ตรงกับตัวเลขและกับเนื้อเมโม (threshold_flag_check) --
    if profile.threshold_flag_check:
        check_threshold_flag(meta, profile, lines, heads, fail)

    # ---- 3. คำ verdict การลงทุน ---------------------------------------
    # profile ที่ตั้ง skip_verdict_rule=True ข้ามทั้งข้อ — งานของมันคือการพูดถึงราคาเทียบมูลค่า
    # ซึ่งใช้คำในรายการนี้เป็นปกติ (intrinsic value · discount · premium) การเปิดกฎไว้จะ FAIL ทุกใบ
    if not profile.skip_verdict_rule:
        lower = text.lower()
        for pat, label in VERDICT_PATTERNS_TH:
            rx = re.compile(pat)
            for i, l in enumerate(lines, 1):
                if rx.search(l):
                    fail("3-verdict", f"พบคำ verdict การลงทุน '{label}' (บรรทัด {i})")
                    break
        for term in VERDICT_TERMS_EN:
            if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", lower):
                ln_no = next((i for i, l in enumerate(lines, 1) if term in l.lower()), 0)
                fail("3-verdict", f"พบคำ verdict การลงทุน '{term}' (บรรทัด {ln_no})")

    # ---- 3b. คำต้องห้ามเฉพาะ profile (ยกเว้นบาง section) --------------
    if profile.forbidden_body_patterns:
        exempt_idx: set[int] = set()
        for pos, (num, start) in enumerate(heads):
            if num in profile.forbidden_body_exempt_sections:
                end = heads[pos + 1][1] if pos + 1 < len(heads) else len(lines)
                exempt_idx.update(range(start, end))
        for pat, label in profile.forbidden_body_patterns:
            rx = re.compile(pat, re.IGNORECASE)
            for i, l in enumerate(lines):
                if i not in exempt_idx and rx.search(l):
                    fail("3b-forbidden", f"พบคำต้องห้าม '{label}' (บรรทัด {i + 1})")
                    break

    # ---- 6. อ้างเลขหน้า (ทำก่อนข้อ 4 เพื่อรายงานเรียงตามความชัด) -------
    for pat, label in PAGE_CITE_PATTERNS:
        for i, ln in enumerate(lines, 1):
            if re.search(pat, ln, re.IGNORECASE):
                fail("6-page-cite", f"บรรทัด {i}: {label} — EDGAR เป็น HTML ไม่มีเลขหน้า")

    # ---- 5. placeholder ค้าง ------------------------------------------
    for i, ln in enumerate(lines, 1):
        if LEFTOVER_RE.search(ln):
            fail("5-placeholder", f"บรรทัด {i}: มี [ยังไม่มีข้อมูล] ค้าง")

    # ---- 4. แถวตารางที่มีตัวเลข ต้องมี citation หรือธง tier ------------
    # ตัดช่วงภาคผนวกออก (มีกติกาของตัวเองในข้อ 7/8)
    app_num = str(profile.appendix_section)
    appendix_start = next(
        (i for i, ln in enumerate(lines, 1)
         if heading_re.match(ln.strip()) and heading_re.match(ln.strip()).group(1) == app_num),
        len(lines) + 1,
    )
    body_lines = lines[: appendix_start - 1]
    for ln_no, cells, is_head in table_rows(body_lines):
        if is_head:
            continue  # ชื่อคอลัมน์ ไม่ใช่ข้อเท็จจริง
        row_text = " | ".join(cells)
        if not any(is_fact_number(c) for c in cells):
            continue
        if MISSING_FLAG_RE.search(row_text):
            continue
        if CITATION_RE.search(row_text) or TIER_RE.search(row_text):
            continue
        if any(re.search(pattern, row_text, re.I) for pattern in profile.extra_citation_patterns):
            continue
        # ตารางพยากรณ์อนาคตไม่มี filing ให้อ้าง — profile ที่เปิด allow_assumption_citation
        # รับ [สมมติฐาน: ...] เป็นธงที่ถูกต้อง ดีกว่าบีบให้ติด [tier3] ซึ่งเป็นการโกหกว่ามีแหล่ง
        if profile.allow_assumption_citation and ASSUMPTION_RE.search(row_text):
            continue
        extra = " หรือ [สมมติฐาน: ...]" if profile.allow_assumption_citation else ""
        fail(
            "4-citation",
            f"บรรทัด {ln_no}: แถวตารางมีตัวเลขแต่ไม่มี [ฟอร์ม ... Item ...] "
            f"หรือ [tier2]/[tier3]{extra}",
        )

    # ---- 7 + 8. ภาคผนวก -------------------------------------------------
    appendix_title = dict(sections).get(profile.appendix_section, "APPENDIX")
    if appendix_start > len(lines):
        fail("7-appendix", f"ไม่พบ §{app_num} {appendix_title}")
    else:
        app_lines = lines[appendix_start - 1:]
        rows = table_rows(app_lines)
        buckets: dict[str, list[tuple[int, list[str]]]] = {
            spec.key: [] for spec in profile.appendix_tables
        }
        head_lines: set[int] = set()
        for off, cells, is_head in rows:
            ln_no = appendix_start - 1 + off
            if is_head:
                head_lines.add(ln_no)
            spec = next((s for s in profile.appendix_tables if s.matches(len(cells))), None)
            if spec is None:
                fail("7-appendix", f"บรรทัด {ln_no}: แถวตารางในภาคผนวกมีช่องไม่ครบ ({len(cells)} ช่อง)")
                continue
            buckets[spec.key].append((ln_no, cells))

        def is_header(cells: list[str], spec: TableSpec, ln_no: int | None = None) -> bool:
            if ln_no is not None and ln_no in head_lines:
                return True
            joined = "".join(cells)
            return all(k in joined for k in spec.header_keys)

        for spec in profile.appendix_tables:
            if spec.required and not buckets[spec.key]:
                fail("7-appendix", f"ไม่พบ{spec.label} ใน §{app_num}")

        for spec in profile.appendix_tables:
            if spec.kind == "calc":
                continue
            for ln_no, cells in buckets[spec.key]:
                if is_header(cells, spec, ln_no):
                    continue
                if any(not c for c in cells[: spec.min_cols]):
                    fail("7-appendix", f"บรรทัด {ln_no}: {spec.short} มีช่องว่าง")

        for spec in profile.appendix_tables:
            if spec.kind != "calc":
                continue
            for ln_no, cells in buckets[spec.key]:
                if is_header(cells, spec, ln_no):
                    continue
                name, formula, numer, denom, result = cells[0], cells[1], cells[2], cells[3], cells[4]
                if any(not c for c in (name, formula, numer, denom, result)):
                    fail("8-recompute", f"บรรทัด {ln_no}: ตารางคำนวณมีช่องว่าง (ต้องครบ ชื่อ/สูตร/ตัวตั้ง/ตัวหาร/ผล)")
                    continue
                if MISSING_FLAG_RE.search(" ".join(cells)):
                    continue
                for cell_label, cell in (("ตัวตั้ง", numer), ("ตัวหาร", denom)):
                    bad = derivation_mismatch(cell)
                    if bad:
                        fail(
                            "8-recompute",
                            f"บรรทัด {ln_no} ({name}): {cell_label} เขียนนำหน้าว่า {bad[1]} "
                            f"แต่ในวงเล็บ (= ...) คำนวณได้ {bad[0]}",
                        )
                n, d, r = first_number(numer), first_number(denom), first_number(result)
                if n is None or d is None or r is None:
                    fail("8-recompute", f"บรรทัด {ln_no} ({name}): ดึงตัวเลขจากช่องไม่ได้ — ตัวตั้ง/ตัวหาร/ผล ต้องขึ้นต้นด้วยตัวเลข")
                    continue
                if d == 0:
                    fail("8-recompute", f"บรรทัด {ln_no} ({name}): ตัวหารเป็นศูนย์")
                    continue
                calc = n / d
                is_pct = "%" in strip_citations(result) or "%" in formula
                if is_pct:
                    calc = calc * Decimal(100)
                # tolerance = ครึ่งหนึ่งของหลักทศนิยมสุดท้ายที่เขียน + เผื่อการปัดชั้นเดียว
                res_txt = NUM_RE.search(strip_citations(result)).group(0).replace(",", "")
                decimals = len(res_txt.split(".")[1]) if "." in res_txt else 0
                tol = Decimal(1).scaleb(-decimals) / 2 + Decimal(1).scaleb(-(decimals + 6))
                if abs(calc - r) > tol:
                    fail(
                        "8-recompute",
                        f"บรรทัด {ln_no} ({name}): คำนวณซ้ำได้ {calc:.6f} แต่ในเมโมเขียน {r} "
                        f"(สูตร: {formula}) — ตารางนี้รองรับเฉพาะ 'ตัวตั้ง ÷ ตัวหาร'; "
                        f"ถ้าเป็นส่วนต่าง (Δ / YoY) ให้ใส่ผลลบที่คำนวณแล้วเป็นตัวตั้ง "
                        f"แล้วกำกับที่มาแบบ  10,000 (=110,000−100,000) [ฟอร์ม งวด Item]",
                    )

        # ---- 10 + 11. การปรับรายการครั้งเดียว ต้องปรับครบทุกปีและถูกปี ------
        if profile.paired_adjustment_check:
            calc_spec = next((s for s in profile.appendix_tables if s.kind == "calc"), None)
            src_spec = next(
                (s for s in profile.appendix_tables if s.kind != "calc" and "งวด" in "".join(s.header_keys)),
                None,
            )
            calc_rows = [
                (n, c[0], c[2], c[3])
                for n, c in buckets[calc_spec.key]
                if calc_spec and not is_header(c, calc_spec, n) and len(c) >= 5 and all(c[:5])
            ] if calc_spec else []
            src_rows = [
                (n, c[0], c[2])
                for n, c in buckets[src_spec.key]
                if src_spec and not is_header(c, src_spec, n) and len(c) >= 3
            ] if src_spec else []
            if calc_rows:
                check_paired_adjustment(calc_rows, src_rows, fail)

        # ---- 9. ทุก [สมมติฐาน: ...] ในเนื้อเมโม ต้องมีแถวในตารางสมมติฐาน --
        if profile.assumption_table_key:
            markers = [i for i, ln in enumerate(body_lines, 1) if ASSUMPTION_RE.search(ln)]
            spec = next(s for s in profile.appendix_tables if s.key == profile.assumption_table_key)
            data_rows = [c for n, c in buckets[spec.key] if not is_header(c, spec, n)]
            if markers and len(data_rows) < len(markers):
                fail(
                    "9-assumption",
                    f"เนื้อเมโมมี [สมมติฐาน: ...] {len(markers)} จุด (บรรทัด "
                    + ", ".join(str(i) for i in markers)
                    + f") แต่ตารางสมมติฐานใน §{app_num} มีแค่ {len(data_rows)} แถว",
                )

    if profile.semantic_check is not None:
        profile.semantic_check(text, meta, lines, heads, fail)
    return (1 if failures else 0), failures


def report(path: str, profile: Profile) -> int:
    code, failures = check_memo(path, profile)
    if code == 2:
        return 2
    if path == STDIN_PATH:
        path = STDIN_LABEL
    if failures:
        print(f"FAIL ({len(failures)} ข้อ) — {path}")
        for f in failures:
            print("  " + f)
        return 1
    print(f"PASS — {path}")
    return 0


# ---------------------------------------------------------------- --rules

def print_rules(profile: Profile) -> int:
    """พิมพ์กฎที่เครื่องตรวจ 'บังคับจริง' — เพื่อให้พรอมต์เอเจนต์อ้างที่นี่
    แทนการก๊อปเช็คลิสต์ไปเก็บไว้อีกชุด (สองชุดจะเถียงกันเองเมื่อแก้ข้างเดียว)"""
    lo, hi = profile.exec_summary_range
    last_section = profile.sections[-1][0]
    print(f"กฎที่ {profile.tool_name} บังคับ (แหล่งความจริงเดียว)")
    print()
    print("1-yaml       ฟิลด์บังคับ: " + ", ".join(profile.required_yaml_fields))
    print("             ห้ามมี:      " + ", ".join(profile.forbidden_yaml_fields))
    print("             ทุกฟิลด์บังคับต้องมีค่าจริง — null / สตริงว่าง / list ว่าง = ขาด")
    for fname, allowed in profile.enum_yaml_fields.items():
        print(f"             {fname} รับเฉพาะ: " + " | ".join(allowed))
    for fname, want in profile.list_len_yaml_fields.items():
        print(f"             {fname} ต้องเป็น list {want} รายการพอดี")
    print(f"             exec_summary ต้องเป็น list {lo}–{hi} รายการ")
    if profile.stance_range_check:
        f_stance, f_price, f_lo, f_hi, v_lo, v_mid, v_hi = profile.stance_range_check
        print(f"1-yaml-stance {f_stance} ถูกคิดซ้ำด้วย Decimal จาก {f_price} เทียบช่วง "
              f"{f_lo}–{f_hi}:")
        print(f"               {f_price} < {f_lo} → {v_lo} · อยู่ในช่วง (รวมขอบ) → {v_mid} · "
              f"{f_price} > {f_hi} → {v_hi}")
        print(f"             {f_price}/{f_lo}/{f_hi} ที่ไม่ใช่ตัวเลข หรือ {f_lo} > {f_hi} → FAIL")
    if profile.threshold_flag_check:
        spec = profile.threshold_flag_check
        bands = " · ".join(
            (f"{'≥' if inc else '>'} {lo} → {v}" if lo is not None else f"ที่เหลือ → {v}")
            for lo, inc, v in spec.bands)
        print(f"1-yaml-flag  {spec.flag_field} ถูกคิดซ้ำด้วย Decimal จาก {spec.number_field}:")
        print(f"               {bands} · คำนวณไม่ได้ → {spec.na_value}")
        print(f"             บรรทัดธงใน §{spec.section} ต้องพูดระดับและตัวเลขเดียวกับ YAML")
    print(f"2-sections   ต้องมี §0–§{last_section} ครบ ชื่อตรง และเรียง 0→{last_section}:")
    for num, title in profile.sections:
        print(f"               §{num} {title}")
    for line in profile.rules_opinion_lines:
        print(line)
    for num, patterns in sorted(profile.section_required_patterns.items()):
        for _, label in patterns:
            print(f"2c-required-line §{num} ต้องมี{label}")
    if profile.skip_verdict_rule:
        print("3-verdict    ปิดไว้สำหรับ profile นี้ — งานคือการประเมินมูลค่า จึงพูดคำว่า")
        print("             intrinsic value / discount / premium / margin of safety ได้ปกติ")
        print("             ⚠️ 'น่าซื้อ' · 'แนะนำถือ' จะผ่านเครื่องตรวจด้วย — กันด้วยพรอมต์")
        print("             กับบรรทัด DISCLAIMER บังคับเท่านั้น ตัวหลักต้องอ่านด้วยตา")
    else:
        print("3-verdict    ห้ามมีคำแนะนำลงทุน — จับ " +
              f"{len(VERDICT_PATTERNS_TH)} รูปแบบไทย / {len(VERDICT_TERMS_EN)} คำอังกฤษ:")
        print("               ไทย:    " + " · ".join(label for _, label in VERDICT_PATTERNS_TH))
        print("               อังกฤษ: " + " · ".join(VERDICT_TERMS_EN))
        print("             (เนื้อหาธุรกิจปกติผ่านได้ เช่น 'เข้าซื้อกิจการ' · 'สินค้าราคาถูก' ·")
        print("              'หุ้นถูกซื้อคืน' — คำกำกวมต้องผูกกับบริบทราคาหุ้นถึงจะ FAIL)")
    if profile.forbidden_body_patterns:
        where = " · ".join(f"§{n}" for n in profile.forbidden_body_exempt_sections) or "ไม่มี"
        print(f"3b-forbidden ห้ามมีคำเหล่านี้ทั้งเมโม (ยกเว้น: {where}):")
        print("               " + " · ".join(label for _, label in profile.forbidden_body_patterns))
    for line in profile.rules_citation_lines:
        print(line)
    print("5-placeholder ห้ามมี [ยังไม่มีข้อมูล] ค้าง")
    print("6-page-cite  ห้ามอ้างเลขหน้า (หน้า N · p.N · page N · pp.N)")
    for line in profile.rules_appendix_lines:
        print(line)
    print("8-recompute  ทุกแถวตารางคำนวณถูกคิดซ้ำด้วย Decimal เป็น 'ตัวตั้ง ÷ ตัวหาร'")
    print("             มี % ในสูตรหรือผล → คูณ 100 ให้เอง")
    print("             ส่วนต่าง (Δ/YoY): ใส่ผลลบที่คำนวณแล้วเป็นตัวตั้ง แล้วกำกับ")
    print("             การลบไว้ในวงเล็บ เช่น  10,000 (=110,000−100,000) [10-K FY2025, Item 8]")
    print("             เครื่องตรวจจะตรวจการลบในวงเล็บนั้นซ้ำด้วย")
    if profile.paired_adjustment_check:
        print("10-adjust-pair ถอดรายการครั้งเดียวออกจากฐานปีหนึ่งแล้ว ทุกแถวที่ยังใช้ฐานเดิม")
        print("             (ตัวหารเดียวกัน) ต้องมีแถวคู่ที่คิดบนฐานที่ปรับแล้วด้วย")
        print("             — กันการเอาสองปีคนละฐานมาเทียบกันในเนื้อเมโม")
        print("11-adjust-period ปีของรายการที่ถอดออก ต้องตรงกับ 'งวด' ในตารางที่มา")
        print("             — คอลัมน์งวด = ปีบัญชีที่ตัวเลขเกิด ไม่ใช่ปีของ filing ที่ไปอ่าน")
    for line in profile.rules_extra_lines:
        print(line)
    return 0
