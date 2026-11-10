#!/usr/bin/env python3
"""Fail-closed structural checker for investment-thesis-synthesis reports.

Usage:
    __FRIDAY_ROOT__/.venv/bin/python check_report.py <report.md>

Exit codes: 0 = PASS, 1 = FAIL, 2 = usage error.

Checks structure, metadata, freshness, citation presence and the
current-price rule only. It does NOT validate investment reasoning.
Standard library only (the analysis venv has no PyYAML), so the YAML
header is parsed as flat `key: value` lines.
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path

AGENTS = ("tony", "tommun", "rob", "adam", "damon")
STANCES = ("น่าสนใจ", "ควรรอ", "ควรหลีกเลี่ยง")
CONFIDENCES = ("สูง", "ปานกลาง", "ต่ำ")
LABELS = ("[ข้อเท็จจริง]", "[การตีความ]", "[สมมติฐาน]", "[ข้อสังเคราะห์ใหม่]")
PLACEHOLDER = "[ยังไม่มีข้อมูล]"
TIERS = ("tier1", "tier2", "tier3")
MAX_MEMO_AGE_DAYS = 90
SECTIONS = ("A", "B", "C", "D", "E", "F", "G", "H")
SUBSECTIONS_F = ("F1", "F2", "F3")
SOURCES_HEADING = "## แหล่งอ้างอิง"

REQUIRED_KEYS = (
    "ticker", "company", "generated_at", "run_date",
    *(k for a in AGENTS for k in (f"memo_{a}", f"memo_{a}_as_of")),
    "current_price", "price_date", "price_retrieved_at", "price_source", "price_tier",
    "valuation_price", "valuation_price_date",
    "stance", "confidence", "confidence_limits",
)

# friday/.claude/skills/investment-thesis-synthesis/scripts/check_report.py
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]


def parse_front_matter(text):
    """Return (dict, body) or (None, text) when no header is found."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return None, text
    data = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            continue  # nested/list lines are ignored; required keys are flat
        key, _, value = line.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key.strip()] = value
    return data, text[match.end():]


def parse_date(value):
    try:
        return date.fromisoformat(value.strip()[:10]) if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", value.strip()[:10]) else None
    except ValueError:
        return None


def memo_as_of(path):
    fm, _ = parse_front_matter(path.read_text(encoding="utf-8"))
    return (fm or {}).get("as_of")


def section_spans(body):
    """Map section letter -> (start, end) offsets of its content."""
    heads = [(m.group(1), m.start(), m.end())
             for m in re.finditer(r"^## ([A-H])\. .+$", body, re.MULTILINE)]
    other = [m.start() for m in re.finditer(r"^## (?![A-H]\. ).+$", body, re.MULTILINE)]
    spans = {}
    for i, (letter, _, end) in enumerate(heads):
        stops = [h[1] for h in heads[i + 1:]] + [o for o in other if o > end] + [len(body)]
        spans.setdefault(letter, (end, min(stops)))
    return heads, spans


def check(report_path):
    errors = []
    fail = errors.append

    text = report_path.read_text(encoding="utf-8")
    fm, body = parse_front_matter(text)
    if fm is None:
        return ["ไม่พบ YAML header (--- ... ---) บรรทัดแรกของไฟล์"]

    # --- metadata presence ---
    for key in REQUIRED_KEYS:
        if not fm.get(key, "").strip():
            fail(f"YAML: ขาดหรือว่าง `{key}`")

    ticker = fm.get("ticker", "").strip()
    run_date = parse_date(fm.get("run_date", ""))
    if fm.get("run_date") and run_date is None:
        fail("YAML: `run_date` ต้องเป็น YYYY-MM-DD")
    if fm.get("generated_at"):
        try:
            datetime.fromisoformat(fm["generated_at"])
        except ValueError:
            fail("YAML: `generated_at` ต้องเป็น ISO datetime")

    # --- filename ---
    name_match = re.fullmatch(r"([A-Z0-9.\-]+?)-(\d{4}-\d{2}-\d{2})(?:-(\d{4}))?\.md", report_path.name)
    if not name_match:
        fail("ชื่อไฟล์ต้องเป็น <TICKER>-YYYY-MM-DD.md หรือ <TICKER>-YYYY-MM-DD-HHMM.md")
    else:
        if ticker and name_match.group(1) != ticker:
            fail(f"ticker ในชื่อไฟล์ ({name_match.group(1)}) ไม่ตรง YAML ({ticker})")
        if run_date and name_match.group(2) != run_date.isoformat():
            fail("วันที่ในชื่อไฟล์ไม่ตรง `run_date`")

    # --- memos ---
    for agent in AGENTS:
        rel = fm.get(f"memo_{agent}", "").strip()
        declared = fm.get(f"memo_{agent}_as_of", "").strip()
        if not rel:
            continue
        if not re.fullmatch(rf"outputs/{agent}/{re.escape(ticker)}-\d{{4}}-\d{{2}}-\d{{2}}(?:-\d{{4}})?\.md", rel):
            fail(f"memo_{agent}: path ต้องเป็น outputs/{agent}/{ticker}-YYYY-MM-DD[-HHMM].md (ได้ `{rel}`)")
        memo_path = Path(rel) if Path(rel).is_absolute() else WORKSPACE_ROOT / rel
        if not memo_path.is_file():
            fail(f"memo_{agent}: ไม่พบไฟล์ `{rel}`")
            continue
        actual = memo_as_of(memo_path)
        if not actual:
            fail(f"memo_{agent}: ไฟล์มีโม่ไม่มี `as_of` ใน YAML")
        elif declared != actual.strip():
            fail(f"memo_{agent}_as_of ({declared}) ไม่ตรงกับ as_of ในมีโม่ ({actual.strip()})")
        as_of = parse_date(declared)
        if declared and as_of is None:
            fail(f"memo_{agent}_as_of ต้องเป็น YYYY-MM-DD")
        elif as_of and run_date:
            age = (run_date - as_of).days
            if age < 0:
                fail(f"memo_{agent}: as_of อยู่หลัง run_date")
            elif age > MAX_MEMO_AGE_DAYS:
                fail(f"memo_{agent}: อายุ {age} วัน เกิน {MAX_MEMO_AGE_DAYS} วัน — ต้องหยุด ไม่ใช่ออกรายงาน")

    # --- price ---
    price = fm.get("current_price", "").strip()
    price_date = fm.get("price_date", "").strip()
    tier = fm.get("price_tier", "").strip()
    retrieved = parse_date(fm.get("price_retrieved_at", ""))
    price_missing = price == PLACEHOLDER
    if fm.get("price_retrieved_at") and retrieved is None:
        fail("YAML: `price_retrieved_at` ต้องเป็น YYYY-MM-DD")
    elif retrieved and run_date and retrieved != run_date:
        fail("`price_retrieved_at` ต้องเท่ากับ `run_date` (ต้องดึงหรือพยายามดึงราคาในรอบนี้)")
    if price_missing:
        if price_date != PLACEHOLDER or tier != PLACEHOLDER:
            fail(f"ไม่มีราคาปัจจุบัน → `price_date` และ `price_tier` ต้องเป็น {PLACEHOLDER} ด้วย")
        if fm.get("stance", "").strip() == "น่าสนใจ":
            fail("ไม่มีราคาปัจจุบันที่ตรวจได้ → stance ห้ามเป็น `น่าสนใจ`")
    elif price:
        if not re.fullmatch(r"\d[\d,]*(?:\.\d+)?\s*USD", price):
            fail(f"`current_price` ต้องเป็นตัวเลข + USD หรือ {PLACEHOLDER} (ได้ `{price}`)")
        pd = parse_date(price_date)
        if pd is None:
            fail("`price_date` ต้องเป็น YYYY-MM-DD เมื่อมีราคา")
        elif run_date and pd > run_date:
            fail("`price_date` อยู่หลัง run_date")
        if tier not in TIERS:
            fail(f"`price_tier` ต้องเป็น {'/'.join(TIERS)} เมื่อมีราคา")

    stance = fm.get("stance", "").strip()
    if stance and stance not in STANCES:
        fail(f"`stance` ต้องเป็น {' / '.join(STANCES)} (ได้ `{stance}`)")
    confidence = fm.get("confidence", "").strip()
    if confidence and confidence not in CONFIDENCES:
        fail(f"`confidence` ต้องเป็น {' / '.join(CONFIDENCES)} (ได้ `{confidence}`)")
    if fm.get("confidence_limits", "").strip() == PLACEHOLDER:
        fail("`confidence_limits` ต้องระบุข้อจำกัดจริง")

    # --- headings A–H ---
    heads, spans = section_spans(body)
    letters = [h[0] for h in heads]
    for letter in SECTIONS:
        if letters.count(letter) != 1:
            fail(f"หัวข้อ `## {letter}. ...` ต้องมีครั้งเดียว (พบ {letters.count(letter)})")
    if [l for l in letters if l in SECTIONS] != list(SECTIONS) and all(letters.count(l) == 1 for l in SECTIONS):
        fail("หัวข้อ A–H เรียงลำดับไม่ถูก")

    if "F" in spans:
        f_text = body[spans["F"][0]:spans["F"][1]]
        subs = re.findall(r"^### (F[1-3])\. ", f_text, re.MULTILINE)
        if subs != list(SUBSECTIONS_F):
            fail(f"หัวข้อ F ต้องมี `### F1.` `### F2.` `### F3.` ครบและเรียง (พบ {subs})")

    if "A" in spans:
        a_text = body[spans["A"][0]:spans["A"][1]]
        for needle in ("บริษัทดีหรือไม่", "หุ้นคุ้มราคาหรือไม่", "ความสดของข้อมูล"):
            if needle not in a_text:
                fail(f"หัวข้อ A ต้องมี `{needle}`")
        if stance and stance not in a_text:
            fail("หัวข้อ A ต้องระบุ stance เดียวกับ YAML")
        if confidence and confidence not in a_text:
            fail("หัวข้อ A ต้องระบุความเชื่อมั่นเดียวกับ YAML")
        for agent in AGENTS:
            d = fm.get(f"memo_{agent}_as_of", "").strip()
            if d and d not in a_text:
                fail(f"ความสดของข้อมูลในหัวข้อ A ไม่ได้ระบุ as_of ของ {agent} ({d})")
        if price_missing and PLACEHOLDER not in a_text:
            fail(f"ไม่มีราคาปัจจุบัน → หัวข้อ A ต้องเขียน {PLACEHOLDER} ให้ผู้อ่านเห็น")

    # --- sources section ---
    src = re.search(rf"^{re.escape(SOURCES_HEADING)}\s*$", body, re.MULTILINE)
    if not src:
        fail(f"ไม่มีหัวข้อ `{SOURCES_HEADING}`")
    else:
        if "H" in spans and src.start() < spans["H"][0]:
            fail(f"`{SOURCES_HEADING}` ต้องอยู่หลังหัวข้อ H")
        if not re.search(r"https?://\S+", body[src.end():]):
            fail(f"`{SOURCES_HEADING}` ต้องมี URL อย่างน้อยหนึ่งรายการ")

    # --- inline memo citations ---
    main_body = body[:src.start()] if src else body
    for agent in AGENTS:
        rel = fm.get(f"memo_{agent}", "").strip()
        if rel and not re.search(re.escape(rel) + r"(?::\d+(?:[–-]\d+)?)?\s*§\s*\d", main_body):
            fail(f"ไม่มีการอ้าง `{rel} §N` ในเนื้อหา")

    # --- provenance labels ---
    for label in LABELS:
        if label not in main_body:
            fail(f"ไม่พบป้าย `{label}` ในเนื้อหา")

    # --- leftovers ---
    if re.search(r"<TICKER>|\{\{|\bTODO\b", text):
        fail("มี placeholder ค้าง (<TICKER> / {{ }} / TODO)")

    return errors


def main(argv):
    if len(argv) != 2:
        print("usage: check_report.py <report.md>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"usage error: ไม่พบไฟล์ {path}", file=sys.stderr)
        return 2
    errors = check(path)
    if errors:
        print(f"FAIL — {path} ({len(errors)} ข้อ)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"PASS — {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
