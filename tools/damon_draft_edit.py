"""แก้ไฟล์ร่างของเดมอนแบบแทนข้อความตรงตัว (ไม่ใช่ regex) — แทน `sed -i` (เพิ่ม 2026-10-18)

ทำไมไม่ใช้ sed: ป้ายที่มา `[10-K FY2025, Item 8]` มีวงเล็บเหลี่ยมเกือบทุกแถว sed อ่านเป็น
"ตัวอักษรตัวใดก็ได้ในวงเล็บ" แล้วแทนผิดที่โดยยัง exit 0 · `&` ในข้อความใหม่ก็ถูกขยายเป็นข้อความเดิม

ใช้: ข้อความเดิม · บรรทัด <<<WITH>>> · ข้อความใหม่ ผ่าน stdin
  __FRIDAY_ROOT__/.venv/bin/python __FRIDAY_ROOT__/tools/damon_draft_edit.py NVDA <<'EOF'
  ข้อความเดิม
  <<<WITH>>>
  ข้อความใหม่
  EOF
ข้อความเดิมต้องเจอ "ครั้งเดียวพอดี" ไม่งั้นไม่แตะไฟล์ (exit 1) · สำเร็จพิมพ์ sha256 ของร่างใหม่
แตะได้แค่ scratch/damon-drafts/<TICKER>.md ที่มีอยู่แล้วเท่านั้น
"""
import hashlib
import re
import sys
from pathlib import Path

DRAFTS = Path(__file__).resolve().parents[1] / "scratch" / "damon-drafts"
SEP = "\n<<<WITH>>>\n"


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", sys.argv[1]):
        print("usage: damon_draft_edit.py <TICKER>  (ข้อความเดิม / <<<WITH>>> / ข้อความใหม่ ผ่าน stdin)")
        return 2
    path = DRAFTS / f"{sys.argv[1]}.md"
    if not path.is_file():
        print(f"ไม่มีไฟล์ร่าง {path} — เขียนทั้งใบด้วย cat > ก่อน")
        return 1
    raw = sys.stdin.read()
    if raw.count(SEP) != 1:
        print("stdin ต้องมีบรรทัด <<<WITH>>> หนึ่งบรรทัดพอดี")
        return 2
    old, new = raw.split(SEP)
    new = new[:-1] if new.endswith("\n") else new  # heredoc เติม \n ท้ายเสมอ
    text = path.read_text(encoding="utf-8")
    n = text.count(old)
    if n != 1:
        print(f"ข้อความเดิมเจอ {n} ครั้ง (ต้องเจอ 1 ครั้งพอดี) — ไม่ได้แก้ไฟล์ · ขยายข้อความเดิมให้เจาะจงขึ้น")
        return 1
    out = text.replace(old, new)
    path.write_text(out, encoding="utf-8")
    print(f"OK แก้ 1 จุด · sha256 {hashlib.sha256(out.encode('utf-8')).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
