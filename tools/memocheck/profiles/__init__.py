"""profiles — สเปกรายเอเจนต์ (ชื่อโมดูล = slug ที่ใช้กับ --profile)"""

from __future__ import annotations

import importlib

from ..core import Profile

KNOWN = ("tony", "tommun", "rob", "adam", "damon")


def load(slug: str) -> Profile:
    if slug not in KNOWN:
        raise KeyError(slug)
    mod = importlib.import_module(f"{__name__}.{slug}")
    return mod.PROFILE
