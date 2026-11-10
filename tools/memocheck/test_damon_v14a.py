"""V14(ก) — ผลตอบแทนส่วนเพิ่มโดยนัยของฉาก Base เทียบ ROIC อดีต (กฎ 2c-v14a ของเดมอน · เพิ่ม 2026-10-10)

บทเรียน: BWXT 2026-10-08 — §0 เล่าว่า "มาร์จิ้นไม่น่าขยายมาก" แต่ฉาก Base ใส่ผลตอบแทนส่วนเพิ่ม
19.02–30.76% เทียบ ROIC อดีต 11.35–15.08% แล้วผ่านไปด้วยย่อหน้าเดียว
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_damon_v14a
"""
import re
import tempfile
import unittest
from pathlib import Path

from tools.memocheck.core import check_memo
from tools.memocheck.profiles import load

ROOT = Path(__file__).resolve().parents[2]
GOOD = ROOT / 'scratch/damon-check-fixtures/good.md'
LINE_RX = re.compile(r'^ตรวจผลตอบแทนส่วนเพิ่ม \(V14ก\):.*$', re.M)
OLD_HEAD = '| ปี | Revenue (ล้าน USD) | Rev growth % | EBIT margin % | NOPAT | D&A | Capex | ΔNWC | Net reinvestment | FCFF | ที่มา |'


def line(x, y, choice):
    return (f'ตรวจผลตอบแทนส่วนเพิ่ม (V14ก): ROIC อดีตสูงสุด {x}% · '
            f'ผลตอบแทนส่วนเพิ่มโดยนัยสูงสุดฉาก Base {y} · ทางที่เลือก: {choice}')


def run(text):
    with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8', delete=False) as f:
        f.write(text)
    try:
        return check_memo(f.name, load('damon'))
    finally:
        Path(f.name).unlink()


def v14a(failures):
    return [x for x in failures if '[2c-v14a]' in x]


def with_column(text, values):
    """เติมคอลัมน์ 'ผลตอบแทนส่วนเพิ่มโดยนัย %' ให้ตาราง Base ของ fixture (สามปี + ปลายทาง)"""
    out, rows = [], iter(values + ['—'])
    for ln in text.split('\n'):
        if ln == OLD_HEAD:
            ln = ln[:-len('| ที่มา |')] + '| ผลตอบแทนส่วนเพิ่มโดยนัย % | ที่มา |'
        elif ln == '|---|---|---|---|---|---|---|---|---|---|---|':
            ln += '---|'
        elif re.match(r'\| (FY2026|FY2027|FY2028|ปลายทาง) \| [\d,]+\.\d\d \| [\d.]+ \| [\d.]+ \| [\d,.]+ \| \d', ln):
            cells = ln.split(' | ')
            cells.insert(len(cells) - 1, next(rows))
            ln = ' | '.join(cells)
        out.append(ln)
    return '\n'.join(out)


class DamonV14a(unittest.TestCase):
    def setUp(self):
        self.text = GOOD.read_text(encoding='utf-8')
        self.assertEqual(len(LINE_RX.findall(self.text)), 1)

    def swap(self, new):
        return LINE_RX.sub(new, self.text)

    def test_good_fixture_passes(self):
        self.assertEqual(check_memo(str(GOOD), load('damon')), (0, []))

    def test_missing_line_fails(self):
        code, failures = run(LINE_RX.sub('', self.text))
        self.assertEqual(code, 1)
        self.assertTrue(v14a(failures), failures)

    def test_above_history_requires_section0_choice(self):
        _, failures = run(self.swap(line('15.08', '30.76%', 'ไม่เกิน')))
        self.assertTrue(any("ต้องเป็น '§0 รองรับ'" in x for x in v14a(failures)), failures)
        _, failures = run(self.swap(line('15.08', '30.76%', 'ลด Base')))
        self.assertTrue(v14a(failures), failures)

    def test_section0_choice_needs_section0_sentence(self):
        _, failures = run(self.swap(line('15.08', '30.76%', '§0 รองรับ')))
        self.assertTrue(any('§0 ไม่มีประโยค' in x for x in v14a(failures)), failures)
        text = self.swap(line('15.08', '30.76%', '§0 รองรับ')).replace(
            'อีกสามปี แล้วค่อยเข้าสู่สภาวะคงตัว',
            'อีกสามปี แล้วค่อยเข้าสู่สภาวะคงตัว ผลตอบแทนส่วนเพิ่มสูงกว่าอดีตเพราะศูนย์ข้อมูลลงทุนครบแล้ว', 1)
        self.assertEqual(v14a(run(text)[1]), [])

    def test_section0_choice_rejected_when_not_above(self):
        _, failures = run(self.swap(line('24.00', '20.00%', '§0 รองรับ')))
        self.assertTrue(v14a(failures), failures)

    def test_equal_is_not_above(self):
        self.assertEqual(v14a(run(self.swap(line('20.00', '20.00%', 'ลด Base')))[1]), [])

    def test_undefined_pairs_only_with_reinvestment_flag(self):
        self.assertEqual(v14a(run(self.swap(line('24.00', 'ไม่นิยาม', 'ลงทุนซ้ำ ≤ 0')))[1]), [])
        self.assertTrue(v14a(run(self.swap(line('24.00', 'ไม่นิยาม', 'ไม่เกิน')))[1]))
        self.assertTrue(v14a(run(self.swap(line('24.00', '20.00%', 'ลงทุนซ้ำ ≤ 0')))[1]))

    def test_bold_markdown_tolerated(self):
        bold = line('24.00', '20.00%', 'ไม่เกิน').replace('ตรวจผลตอบแทนส่วนเพิ่ม (V14ก):', '**ตรวจผลตอบแทนส่วนเพิ่ม (V14ก):**')
        self.assertEqual(v14a(run(self.swap(bold))[1]), [])

    def test_declared_max_must_match_base_table_column(self):
        text = with_column(self.text, ['19.02', '30.76', '22.00'])
        self.assertIn('ผลตอบแทนส่วนเพิ่มโดยนัย % | ที่มา |', text)
        lied = LINE_RX.sub(line('35.00', '20.00%', 'ไม่เกิน'), text)
        self.assertTrue(any('สูงสุด 30.76%' in x for x in v14a(run(lied)[1])), run(lied)[1])
        honest = LINE_RX.sub(line('35.00', '30.76%', 'ไม่เกิน'), text)
        self.assertEqual(v14a(run(honest)[1]), [])


if __name__ == '__main__':
    unittest.main()
