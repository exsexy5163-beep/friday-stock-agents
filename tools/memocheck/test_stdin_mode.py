"""โหมด stdin ของเครื่องตรวจ — path '-' = อ่านเมโมจาก stdin (เพิ่ม 2026-10-10)

เหตุผล: เดมอนไม่มีสิทธิเขียนไฟล์ จึงตรวจร่างตัวเองไม่ได้ถ้าเครื่องตรวจรับแค่ path
ข้อบังคับ: ผลจาก stdin ต้องเท่ากับผลจากไฟล์ทุกข้อ (ต่างแค่ชื่อที่พิมพ์ '<stdin>')
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_stdin_mode
"""
import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.memocheck.core import check_memo
from tools.memocheck.profiles import KNOWN, load

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))  # __main__ import แบบ 'memocheck.core' เหมือนตอนเรียกผ่าน shim
from memocheck.__main__ import run  # noqa: E402
PY = ROOT / '.venv-utils/bin/python'
FIXTURES = {slug: ROOT / f'scratch/{slug}-check-fixtures' for slug in KNOWN}


class FakeStdin(io.TextIOWrapper):
    """stdin ปลอมที่มี .buffer เป็นไบต์ และไม่ใช่ TTY — เหมือน pipe จริง"""

    def __init__(self, data: bytes):
        super().__init__(io.BytesIO(data), encoding='utf-8')

    def isatty(self):
        return False


def run_stdin(slug: str, data: bytes) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, 'stdin', FakeStdin(data)), redirect_stdout(out), redirect_stderr(err):
        code = run(['-'], profile_slug=slug)
    return code, out.getvalue(), err.getvalue()


def run_path(slug: str, path: Path) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = run([str(path)], profile_slug=slug)
    return code, out.getvalue()


def sample_memos():
    for slug in KNOWN:
        for p in sorted(FIXTURES[slug].glob('*.md'))[:4]:
            yield slug, p


class StdinMode(unittest.TestCase):
    def test_parity_with_path(self):
        """ทุก profile: exit code และรายการ FAIL จาก stdin = จากไฟล์ (ต่างแค่ป้ายชื่อ)"""
        n = 0
        for slug, p in sample_memos():
            with self.subTest(slug=slug, path=p.name):
                code_p, out_p = run_path(slug, p)
                code_s, out_s, _ = run_stdin(slug, p.read_bytes())
                self.assertEqual(code_s, code_p)
                self.assertEqual(out_s, out_p.replace(str(p), '<stdin>'))
                n += 1
        self.assertGreater(n, 0, 'ไม่เจอ fixture ให้เทียบ')

    def test_crlf_same_as_file(self):
        """ไฟล์เปิดด้วย universal newline → stdin ต้องแปลง CRLF เหมือนกัน"""
        p = FIXTURES['damon'] / 'good.md'
        want = check_memo(str(p), load('damon'))
        code, out, _ = run_stdin('damon', p.read_bytes().replace(b'\n', b'\r\n'))
        self.assertEqual(code, want[0])
        self.assertEqual(out.count('\n  ['), len(want[1]))

    def test_empty_stdin_is_usage_error(self):
        code, out, err = run_stdin('damon', b'  \n')
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('stdin ว่าง', err)

    def test_bad_utf8_is_usage_error(self):
        code, _, err = run_stdin('damon', b'---\n\xff\xfe\n')
        self.assertEqual(code, 2)
        self.assertIn('อ่าน stdin ไม่ได้', err)

    def test_tty_is_usage_error(self):
        tty = FakeStdin(b'')
        tty.isatty = lambda: True
        err = io.StringIO()
        with mock.patch.object(sys, 'stdin', tty), redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(run(['-'], profile_slug='damon'), 2)
        self.assertIn('ไม่มีเมโมส่งเข้า stdin', err.getvalue())

    def test_shim_subprocess(self):
        """เรียกผ่าน shim จริงแบบที่เดมอนจะใช้ — heredoc/pipe เข้า damon_check.py -"""
        p = FIXTURES['damon'] / 'good.md'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        via_path = subprocess.run([str(PY), 'tools/damon_check.py', str(p)], cwd=ROOT, env=env,
                                  capture_output=True, text=True)
        via_stdin = subprocess.run([str(PY), 'tools/damon_check.py', '-'], cwd=ROOT, env=env,
                                   input=p.read_bytes(), capture_output=True)
        self.assertEqual(via_stdin.returncode, via_path.returncode)
        self.assertEqual(via_stdin.stdout.decode('utf-8'),
                         via_path.stdout.replace(str(p), '<stdin>'))


if __name__ == '__main__':
    unittest.main()
