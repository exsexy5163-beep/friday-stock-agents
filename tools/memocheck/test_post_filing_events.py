"""Post-filing events line (POST_FILING_LINE) — required in every profile's appendix since 2026-10-09.

Lesson: BWXT 2026-10-08 — five memos stood on a 10-K filed 7 months earlier; none saw the 8-K
(Item 2.02, EX-99.1) that announced a divestiture. The checker cannot know whether the agent read it
(the receipt probe does that); it forces the memo to declare the result.
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_post_filing_events
"""
import re
import tempfile
import unittest
from pathlib import Path

from tools.memocheck.core import POST_FILING_LINE, check_memo
from tools.memocheck.profiles import load

ROOT = Path(__file__).resolve().parents[2]
APPENDIX = {'tony': 9, 'tommun': 10, 'rob': 9, 'adam': 9, 'damon': 12}
# fixtures that PASS today — each carries the line at the end of its appendix
GOOD = {'tony': 'good.md', 'tommun': 'good.md', 'rob': 'good.md', 'damon': 'good.md'}
LINE_RX = re.compile(r'^เหตุการณ์หลัง filing:.*\n(?:·.*\n)*', re.M)


class PostFilingLine(unittest.TestCase):
    def test_every_profile_requires_it_in_appendix(self):
        for slug, num in APPENDIX.items():
            with self.subTest(slug=slug):
                self.assertIn(POST_FILING_LINE, load(slug).section_required_patterns.get(num, []))

    def test_regex_accepts_status_words_on_head_line(self):
        rx = re.compile(POST_FILING_LINE[0])
        for line in ('เหตุการณ์หลัง filing: กระทบ · 8-K 2026-02-24→2026-10-09 (3 ฉบับ)',
                     'เหตุการณ์หลัง filing: ไม่กระทบ · อ่าน EX-99.1 แล้ว เป็นผลไตรมาสปกติ',
                     'เหตุการณ์หลัง filing: ไม่มี 8-K ในช่วง 2026-02-24→2026-10-09',
                     'เหตุการณ์หลัง filing: ไม่มี 6-K',
                     '**เหตุการณ์หลัง filing:** กระทบ',
                     '**เหตุการณ์หลัง filing**: กระทบ',
                     'เหตุการณ์หลัง filing: ไม่กระทบ · ไม่มีฉบับติดป้าย (5.07)'):
            with self.subTest(line=line):
                self.assertTrue(rx.search(line))

    def test_regex_rejects_vague_or_split_status(self):
        rx = re.compile(POST_FILING_LINE[0])
        for text in ('เหตุการณ์หลัง filing: ตรวจแล้ว',
                     'เหตุการณ์หลัง filing:\nกระทบ',
                     'เหตุการณ์หลัง filing: 8-K 3 ฉบับ\n· กระทบ: ขายธุรกิจ',
                     'ตรวจ 8-K หลัง filing แล้ว กระทบ'):
            with self.subTest(text=text):
                self.assertIsNone(rx.search(text))

    def test_good_fixture_fails_without_line(self):
        for slug, name in GOOD.items():
            path = ROOT / f'scratch/{slug}-check-fixtures/{name}'
            text = path.read_text(encoding='utf-8')
            with self.subTest(slug=slug):
                self.assertEqual(check_memo(str(path), load(slug)), (0, []))
                stripped, n = LINE_RX.subn('', text)
                self.assertEqual(n, 1)
                with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8', delete=False) as f:
                    f.write(stripped)
                try:
                    code, failures = check_memo(f.name, load(slug))
                finally:
                    Path(f.name).unlink()
                self.assertEqual(code, 1)
                self.assertTrue(any('[2c-required-line]' in x and 'เหตุการณ์หลัง filing' in x
                                    for x in failures), failures)


if __name__ == '__main__':
    unittest.main()
