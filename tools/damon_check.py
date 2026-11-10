#!/usr/bin/env python3
"""damon_check.py — shim: เครื่องตรวจเมโมของ 'damon'

รันด้วย:  __FRIDAY_ROOT__/.venv-utils/bin/python tools/damon_check.py <memo.md>
          __FRIDAY_ROOT__/.venv-utils/bin/python tools/damon_check.py --rules
          ... tools/damon_check.py - <<'EOF'   (- = อ่านเมโมจาก stdin · ตรวจร่างโดยไม่ต้องเขียนไฟล์)

ตรวจ "โครงสร้าง" ไม่ตรวจ "น้ำเสียง" — ออก PASS หรือ FAIL พร้อมเหตุผลรายข้อ
exit 0 = PASS, exit 1 = FAIL, exit 2 = ใช้งานผิด (ไฟล์หาย / interpreter ผิด)

logic จริงอยู่ที่ tools/memocheck/ (core.py + profiles/damon.py) — ไฟล์นี้แค่ล็อก profile
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memocheck.__main__ import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], profile_slug="damon"))
