#!/usr/bin/env python3
"""memocheck CLI

    python -m memocheck --profile tommun <memo.md>
    python -m memocheck --profile tony --rules
    python -m memocheck --profile damon - < ร่าง.md      (- = อ่านเมโมจาก stdin)

exit 0 = PASS · 1 = FAIL · 2 = ใช้งานผิด (ไฟล์หาย / interpreter ผิด / profile ไม่รู้จัก)
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # ถูกเรียกแบบ  python tools/memocheck/__main__.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "memocheck"

from memocheck.core import print_rules, report  # noqa: E402
from memocheck.profiles import KNOWN, load  # noqa: E402

USAGE = (
    "ใช้: python -m memocheck --profile <" + "|".join(KNOWN) + "> <memo.md | ->\n"
    "     (- = อ่านเมโมจาก stdin)\n"
    "     python -m memocheck --profile <" + "|".join(KNOWN) + "> --rules\n"
)


def run(argv: list[str], profile_slug: str | None = None) -> int:
    """argv = อาร์กิวเมนต์หลังชื่อโปรแกรม; profile_slug ที่ส่งมาคือค่าที่ shim ล็อกไว้"""
    args = list(argv)
    if args and args[0] == "--profile":
        if len(args) < 2:
            sys.stderr.write(USAGE)
            return 2
        profile_slug, args = args[1], args[2:]
    if profile_slug is None:
        sys.stderr.write(USAGE)
        return 2
    try:
        profile = load(profile_slug)
    except KeyError:
        sys.stderr.write(f"ไม่รู้จัก profile '{profile_slug}' — มีให้เลือก: {', '.join(KNOWN)}\n")
        return 2

    if len(args) == 1 and args[0] == "--rules":
        return print_rules(profile)
    if len(args) != 1:
        sys.stderr.write(USAGE)
        return 2
    return report(args[0], profile)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
