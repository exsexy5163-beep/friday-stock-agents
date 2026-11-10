"""คำสั่งซื้อขายในเมโมเดมอน (กฎ 3b-forbidden · เพิ่ม 2026-10-18 — จาก /scrutinize สเปคเดมอน)

เดมอนปิด 3-verdict ทั้งข้อ จึงใช้ ADVICE_PATTERNS เป็นตาข่ายแทน: จับคำสั่งล้วน
แต่ต้องไม่จับภาษาประเมินมูลค่าปกติ (มูลค่าเหมาะสม · upside · ราคาหุ้นถูกกว่ามูลค่า · ซื้อกิจการ)
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_damon_advice
"""
import tempfile
import unittest
from pathlib import Path

from tools.memocheck.core import check_memo
from tools.memocheck.profiles import load

ROOT = Path(__file__).resolve().parents[2]
GOOD = ROOT / 'scratch/damon-check-fixtures/good.md'
S11 = '## §11 PLAIN-LANGUAGE SUMMARY\n'


def run(text):
    with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8', delete=False) as f:
        f.write(text)
    try:
        return check_memo(f.name, load('damon'))
    finally:
        Path(f.name).unlink()


def rule(failures, rid):
    return [x for x in failures if f'[{rid}]' in x]


class DamonAdvice(unittest.TestCase):
    def setUp(self):
        self.good = GOOD.read_text(encoding='utf-8')
        self.assertIn(S11, self.good, 'fixture เปลี่ยนรูป — แก้ค่าคงที่ในเทสต์')

    def in11(self, line):
        return self.good.replace(S11, S11 + '\n' + line + '\n', 1)

    def test_good_fixture_passes(self):
        code, failures = run(self.good)
        self.assertEqual(code, 0, failures)

    def test_imperatives_fail(self):
        for line in ('- ที่ราคานี้น่าซื้อ', '- ผู้อ่านควรซื้อ', '- แนะนำถือ',
                     '- เป็นจังหวะเข้าซื้อ', '- เหมาะกับการทยอยซื้อ', '- analysts say Strong Buy'):
            with self.subTest(line=line):
                self.assertTrue(rule(run(self.in11(line))[1], '3b-forbidden'))

    def test_valuation_language_passes(self):
        for line in ('- ราคาหุ้นถูกกว่ามูลค่าฐานอยู่ 10%', '- มูลค่าเหมาะสมฉาก Base',
                     '- upside ไปหา IV ฐาน 8%', '- บริษัทเข้าซื้อกิจการ Crinetics',
                     '- ผู้ใช้ถามว่าซื้อดีไหม — ไม่มีเอเจนต์ในเวิร์กสเปซนี้ตอบ'):
            with self.subTest(line=line):
                self.assertFalse(rule(run(self.in11(line))[1], '3b-forbidden'))


if __name__ == '__main__':
    unittest.main()
