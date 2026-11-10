"""V26 — เลขในวงเล็บ (= ...) ของตารางคำนวณ §12 ต้องไม่ใช่ "เลขลอย" (กฎ 2c-v26 ของเดมอน · เพิ่ม 2026-10-10)

บทเรียน: META 2026-09-02 — FCFF FY2025 (=83,276×0.84+18,616-72,215-841) · 841 ไม่ปรากฏที่อื่นในเมโมเลย
แบบหลวม (ผู้ใช้เลือก): เลขต้องปรากฏที่อื่นในเมโมสักที่ (ปัดเศษ · ×/÷100 · 1−x · x−1 นับว่าเลขเดียวกัน)
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_damon_v26
"""
import tempfile
import unittest
from pathlib import Path

from tools.memocheck.core import check_memo
from tools.memocheck.profiles import load

ROOT = Path(__file__).resolve().parents[2]
GOOD = ROOT / 'scratch/damon-check-fixtures/good.md'
ROW = '| 420 (=9120-8700) [10-K FY2025, Item 8] |'


def run(text):
    with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8', delete=False) as f:
        f.write(text)
    try:
        return check_memo(f.name, load('damon'))
    finally:
        Path(f.name).unlink()


def v26(failures):
    return [x for x in failures if '[2c-v26]' in x]


class DamonV26(unittest.TestCase):
    def setUp(self):
        self.good = GOOD.read_text(encoding='utf-8')
        self.assertIn(ROW, self.good, 'fixture เปลี่ยนรูป — แก้ ROW ในเทสต์')

    def swap(self, expr):
        return self.good.replace(ROW, f'| 420 (={expr}) [10-K FY2025, Item 8] |')

    def test_good_fixture_passes(self):
        code, failures = run(self.good)
        self.assertEqual(v26(failures), [])
        self.assertEqual(code, 0, failures)

    def test_orphan_number_fails(self):
        """แบบ META: เลขที่ไม่มีที่อื่นในเมโม ต่อให้ผลคิดถูก"""
        _, failures = run(self.swap('9120-8700+841-841'))
        self.assertEqual(len(v26(failures)), 1)
        self.assertIn('841', v26(failures)[0])

    def test_number_only_in_own_row_still_fails(self):
        """เลขที่โผล่แค่ในแถวตัวเอง (เช่นซ้ำในช่องอื่นของแถวเดียวกัน) ไม่นับเป็นที่มา"""
        text = self.swap('9120-8700+777-777').replace(
            '| NWC ปลายงวด − NWC ต้นงวด |', '| NWC ปลายงวด − NWC ต้นงวด (777) |')
        self.assertEqual(len(v26(run(text)[1])), 1)

    def test_constants_allowed(self):
        _, failures = run(self.swap('(9120-8700)×100÷100×1'))
        self.assertEqual(v26(failures), [])

    def test_complement_and_growth_factor_allowed(self):
        """0.8 = 1 − 20% และ 1.14 = 1 + 14% นับว่าเป็นเลขเดียวกับที่ประกาศไว้ที่อื่น"""
        base = self.good + '\nภาษี 20% · อัตราโต 14%\n'
        _, f1 = run(base.replace(ROW, '| 420 (=9120-8700+0.8-0.8) [10-K FY2025, Item 8] |'))
        _, f2 = run(base.replace(ROW, '| 420 (=9120-8700+1.14-1.14) [10-K FY2025, Item 8] |'))
        self.assertEqual(v26(f1), [])
        self.assertEqual(v26(f2), [])

    def test_rounded_elsewhere_allowed(self):
        """สูตรใช้ 0.0740712605 ส่วนเนื้อเมโมเขียน 7.41% — ปัดแล้วตรงกัน"""
        text = (self.good + '\nWACC 7.41%\n').replace(
            ROW, '| 420 (=9120-8700+0.0740712605-0.0740712605) [10-K FY2025, Item 8] |')
        self.assertEqual(v26(run(text)[1]), [])

    def test_coarse_integer_does_not_absorb(self):
        """ห้ามให้เลขจำนวนเต็มหยาบ ๆ ที่อื่น (เช่น 8) ดูดเลข 841 (841÷100 = 8.41) ไป"""
        text = (self.good + '\nมี 8 โรงงาน\n').replace(
            ROW, '| 420 (=9120-8700+841-841) [10-K FY2025, Item 8] |')
        self.assertEqual(len(v26(run(text)[1])), 1)


if __name__ == '__main__':
    unittest.main()
