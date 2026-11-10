"""Cross-file drift guard: prose that describes tommun's book WACC k_e must match tommun.md (CAPM only).

Scans agent/skill/docs markdown (not outputs/ or *-workspace/ snapshots, which are historical records).
Run: __FRIDAY_ROOT__/.venv-utils/bin/python -m unittest -v tools.memocheck.test_shared_definitions
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# a line talks about tommun's cost of equity / book WACC
CONTEXT = re.compile(r'(?<![A-Za-z0-9_])k_?e(?![A-Za-z0-9_])|book WACC|cost of equity', re.I)
# ...and describes it as multi-method (the pre-2026-10-04 definition)
MULTI = re.compile(r'เฉลี่ย|averag|Gordon|debt[ -]?plus|หนี้บวก|[23]\s*วิธี|สองวิธี|สามวิธี|three methods', re.I)
# ...unless the line is explicitly negating or recording history
NEGATION = re.compile(r'ไม่ใช้|ห้าม|เดิม|ไม่มี|ตัด|เลิก|no longer|\bnot\b', re.I)
# history notes in the source of truth that name the old methods without negation words
ALLOW = {
    ('.claude/agents/tommun.md', 'สองวิธีหลังดึง k_e ต่ำกว่า CAPM'),
}


def scanned_files():
    files = [ROOT / 'CLAUDE.md']
    for base in ['.claude/agents', '.claude/skills', 'tools', 'docs']:
        files += sorted((ROOT / base).rglob('*.md'))
    return [f for f in files if f.is_file() and '-workspace' not in str(f) and '.venv' not in str(f)
            and 'outputs' not in f.relative_to(ROOT).parts]


def drift_lines(text, rel):
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        if not (CONTEXT.search(line) and MULTI.search(line)) or NEGATION.search(line):
            continue
        if any(rel == f and s in line for f, s in ALLOW):
            continue
        hits.append(f'{rel}:{n}: {line.strip()}')
    return hits


class SharedDefinitionsTest(unittest.TestCase):
    def test_pattern_catches_known_drift(self):
        for bad in ['(น้ำหนักตามบัญชี · k_e เฉลี่ย 3 วิธี) ของเขาเอง',
                    'น้ำหนักบัญชี + k_e เฉลี่ย 3 วิธี vs น้ำหนักตลาด',
                    'book WACC ใช้น้ำหนักตามบัญชีและ k_e เฉลี่ยสามวิธี',
                    'k_e = (CAPM + Gordon) / 2']:
            self.assertTrue(drift_lines(bad, 'x.md'), bad)

    def test_pattern_allows_current_definition(self):
        for ok in ['k_e = CAPM = Rf + β × ERP          ← วิธีเดียว (เปลี่ยน 2026-10-04 · เดิมเฉลี่ย 3 วิธี)',
                   '- `k_e = Rf + β อุตสาหกรรม × ERP` เป็น CAPM วิธีหลักและวิธีเดียว ไม่ใช้ Gordon, debt-plus หรือการเฉลี่ยหลายวิธี',
                   '(น้ำหนักตามบัญชี · k_e = CAPM วิธีเดียวด้วยเบตาอุตสาหกรรมของ Damodaran)']:
            self.assertFalse(drift_lines(ok, 'x.md'), ok)

    def test_no_multi_method_k_e_in_workspace(self):
        hits = []
        for f in scanned_files():
            rel = str(f.relative_to(ROOT))
            hits += drift_lines(f.read_text(encoding='utf-8'), rel)
        self.assertEqual(hits, [], 'k_e ของ book WACC ต้องเป็น CAPM วิธีเดียวตาม tommun.md:\n' + '\n'.join(hits))


if __name__ == '__main__':
    unittest.main()
