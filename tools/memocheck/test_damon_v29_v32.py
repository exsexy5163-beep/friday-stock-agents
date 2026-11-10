"""V29 · V30 · V31 · V32 ของเดมอน (กฎ 2c-v29 … 2c-v32 · เพิ่ม 2026-10-10 — จากเมโม META 2026-09-02)

V29 ตัวคูณขาออกตามทฤษฎี + 'คนละระบอบ' · V30 หน่วยโมเดลเทียบ GDP · V31 'กระทบ X ต่อหุ้น' (แบบแคบ) ·
V32 ลิสต์ที่ประกาศว่าเรียงลำดับ
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_damon_v29_v32
"""
import tempfile
import unittest
from pathlib import Path

from tools.memocheck.core import check_memo
from tools.memocheck.profiles import load

ROOT = Path(__file__).resolve().parents[2]
GOOD = ROOT / 'scratch/damon-check-fixtures/good.md'
V29 = 'ตัวคูณขาออกตามทฤษฎี (V29): 13.78x (=(1−0.025÷0.14)÷(0.0846−0.025))'
V30 = 'หน่วยโมเดล (V30): ตัวเงิน · เทียบ GDP ตัวเงิน 4.80% · เพดาน 4.10% · g_term สูงสุด 2.50%'
S10 = "## §10 DAMON'S VERDICT\n"


def run(text):
    with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8', delete=False) as f:
        f.write(text)
    try:
        return check_memo(f.name, load('damon'))
    finally:
        Path(f.name).unlink()


def rule(failures, rid):
    return [x for x in failures if f'[{rid}]' in x]


class DamonV29toV32(unittest.TestCase):
    def setUp(self):
        self.good = GOOD.read_text(encoding='utf-8')
        for anchor in (V29, V30, S10):
            self.assertIn(anchor, self.good, 'fixture เปลี่ยนรูป — แก้ค่าคงที่ในเทสต์')

    def in10(self, line):
        return self.good.replace(S10, S10 + '\n' + line + '\n', 1)

    def test_good_fixture_passes(self):
        code, failures = run(self.good)
        self.assertEqual(code, 0, failures)

    # ---- V29
    def test_v29_missing_line(self):
        f = rule(run(self.good.replace(V29, 'ตัวคูณขาออก 13.78x'))[1], '2c-v29')
        self.assertEqual(len(f), 1)
        self.assertIn('ไม่มีบรรทัด', f[0])

    def test_v29_wrong_multiple(self):
        """แบบ META: เขียน 9.57 ทั้งที่สูตรของตัวเองให้ค่าอื่น"""
        f = rule(run(self.good.replace('13.78x (=', '9.57x (='))[1], '2c-v29')
        self.assertEqual(len(f), 1)
        self.assertIn('13.78', f[0])

    def test_v29_requires_regime_word(self):
        f = rule(run(self.good.replace('คนละระบอบ', 'ต่างกัน'))[1], '2c-v29')
        self.assertEqual(len(f), 1)
        self.assertIn('คนละระบอบ', f[0])

    # ---- V30
    def test_v30_missing_line(self):
        self.assertEqual(len(rule(run(self.good.replace(V30, ''))[1], '2c-v30')), 1)

    def test_v30_unit_mismatch(self):
        """แบบ META: โมเดลตัวเงินแต่เทียบ GDP แท้จริง"""
        bad = self.good.replace('เทียบ GDP ตัวเงิน 4.80%', 'เทียบ GDP แท้จริง 4.80%')
        f = rule(run(bad)[1], '2c-v30')
        self.assertEqual(len(f), 1)
        self.assertIn('หน่วยต้องตรงกัน', f[0])

    def test_v30_g_over_cap(self):
        bad = self.good.replace('เพดาน 4.10%', 'เพดาน 2.00%')
        self.assertTrue(any('เกินเพดาน' in x for x in rule(run(bad)[1], '2c-v30')))

    def test_v30_g_must_match_table(self):
        bad = self.good.replace('g_term สูงสุด 2.50%', 'g_term สูงสุด 2.00%')
        f = rule(run(bad)[1], '2c-v30')
        self.assertEqual(len(f), 1)
        self.assertIn('ตาราง §2', f[0])

    # ---- V31
    def test_v31_untagged_impact_fails(self):
        """แบบ META: 'กระทบมูลค่าราว 90 USD ต่อหุ้น' ไม่บอกว่าอยู่ในฐานแล้ว และไม่อยู่ในตารางคำนวณ"""
        f = rule(run(self.in10('ขาดทุนต่อเนื่องกระทบมูลค่าราว 90 USD ต่อหุ้น'))[1], '2c-v31')
        self.assertEqual(len(f), 1)
        self.assertIn('อยู่ในฉากฐานแล้ว', f[0])
        self.assertIn('ตารางคำนวณ', f[0])

    def test_v31_tagged_and_registered_passes(self):
        # 165.00 คือผลในตารางคำนวณ §12 ของ fixture
        line = 'ถ้าเรื่องนี้จบลงจะบวกกลับ — กระทบมูลค่า 165.00 USD ต่อหุ้น ซึ่งอยู่ในฉากฐานแล้ว'
        self.assertEqual(rule(run(self.in10(line))[1], '2c-v31'), [])

    def test_v31_other_verbs_not_checked(self):
        """แบบแคบ: 'ลด IV X ต่อหุ้น' ไม่อยู่ในขอบเขต (ตั้งใจ — แบบกว้างจับผิดมาก)"""
        self.assertEqual(rule(run(self.in10('ลด IV ลง 8.03 USD ต่อหุ้น'))[1], '2c-v31'), [])

    # ---- V32
    def test_v32_inline_list_out_of_order(self):
        """แบบ META: 'เรียงตามขนาดผล' แต่อันดับ 2 ใหญ่กว่าอันดับ 1"""
        line = 'ตัวแปรเหวี่ยง IV เรียงตามขนาดผล: (1) อัตราโตรายได้ 39.91 USD (2) ธรรมเนียม g + WACC 106.76 USD'
        f = rule(run(self.in10(line))[1], '2c-v32')
        self.assertEqual(len(f), 1)
        self.assertIn('39.91 → 106.76', f[0])

    def test_v32_inline_list_in_order(self):
        line = 'เรียงตามขนาดผล: (1) ธรรมเนียม g + WACC 106.76 USD (2) อัตราโตรายได้ 39.91 USD'
        self.assertEqual(rule(run(self.in10(line))[1], '2c-v32'), [])

    def test_v32_bullets_next_lines(self):
        block = ('ตัวแปรที่ IV ไวที่สุด (มากไปน้อย):\n\n'
                 '- เบตา 12.00 USD\n- g_term 30.00 USD\n- มาร์จิ้น 5.00 USD')
        f = rule(run(self.in10(block))[1], '2c-v32')
        self.assertEqual(len(f), 1)

    def test_v32_ascending(self):
        line = 'เรียงจากน้อยไปมาก: (1) ก 5.00 USD (2) ข 12.00 USD (3) ค 30.00 USD'
        self.assertEqual(rule(run(self.in10(line))[1], '2c-v32'), [])

    def test_v32_no_comparable_numbers_skipped(self):
        """หน่วยต่างกันจนเทียบไม่ได้ → ไม่ตัดสิน (ไม่ FAIL)"""
        line = 'เรียงตามขนาดผล: (1) เบตา 0.10 (2) g_term 50 จุดพื้นฐาน'
        self.assertEqual(rule(run(self.in10(line))[1], '2c-v32'), [])


if __name__ == '__main__':
    unittest.main()
