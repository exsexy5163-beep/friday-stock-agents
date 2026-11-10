"""Opt-in SEC regression. No Keychain/API-key endpoints are called.

MARKETDATA_SEC_LIVE=1 toolkit-python -m unittest discover -s tools/marketdata -p test_filing_bundle_live.py -v
For an already published bundle, explicitly add MARKETDATA_BUNDLE_VERIFY_EXISTING=1.
That mode verifies the existing artifact (not a fresh bundle fetch); legacy SEC probes still run live.
"""
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import unittest

import filing_bundle

TICKER = "ISRG"
FORM = "10-K"
ACCESSION = "0001035267-25-000017"
SECTIONS = ["Item 1A", "Item 7"]


@unittest.skipUnless(os.environ.get("MARKETDATA_SEC_LIVE") == "1", "opt-in: MARKETDATA_SEC_LIVE=1")
class SecLiveTests(unittest.TestCase):
    def test_bundle_live_regression(self):
        target = filing_bundle.BUNDLE_ROOT / TICKER / ACCESSION
        command = [str(filing_bundle.HERE / "marketdata"), "filing-bundle", TICKER,
                   "--form", FORM, "--accession", ACCESSION]
        for section in SECTIONS:
            command.extend(["--section", section])
        if os.environ.get("MARKETDATA_BUNDLE_VERIFY_EXISTING") == "1":
            print("Explicit existing-artifact verification; bundle fetch not repeated")
        else:
            self.assertFalse(target.exists(), "Bundle exists; no overwrite. Explicit verification mode is available.")
            completed = subprocess.run(command, capture_output=True, text=True, shell=False, timeout=520)
            print("COMMAND:", command)
            print(completed.stdout)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            result = json.loads(completed.stdout.split("\n", 1)[1])
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(Path(result["bundle_path"]), target)
        manifest = filing_bundle.verify_bundle(target, TICKER, FORM, ACCESSION, SECTIONS)
        receipt = {"status": manifest["status"], "accession": manifest["accession"], "form": manifest["form"],
                   "source": manifest["source"], "source_tier": manifest["source_tier"],
                   "as_of": manifest["as_of"], "sections": {}}
        for section in SECTIONS:
            info = manifest["sections"][section]
            text = (target / info["file"]).read_bytes().decode("utf-8")
            heading = text[:1500].lower()
            self.assertIn(section.lower(), heading)
            if section == "Item 1A":
                self.assertIn("risk factors", heading)
            else:
                self.assertIn("discussion", heading)
                self.assertIn("analysis", heading)
            receipt["sections"][section] = {"chars": info["chars"], "sha256": info["sha256"],
                                             "attempts": info["attempts"], "opening": text[:240]}
        print("LIVE RECEIPT:", json.dumps(receipt, ensure_ascii=False, indent=2))

    def test_existing_sec_smoke_cases(self):
        # Execute the original SEC-only statements, not a rewritten weaker copy.
        # mcp_smoke_test is top-level and runs Keychain endpoints on import, so
        # select its helpers + SEC filing test block through the Python AST.
        path = filing_bundle.HERE / "mcp_smoke_test.py"
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        import mcp_server as srv
        scope = {"srv": srv}
        nodes: list[ast.stmt] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"classify", "show"}]
        # These anchors are existing source statements, not provider output.
        start = source.index('# --- 11) filings 8-K')
        end = source.index('print("=" * 60)', start)
        start_line = source[:start].count("\n") + 1
        end_line = source[:end].count("\n") + 1
        nodes.extend(n for n in tree.body if start_line <= n.lineno < end_line)
        # The original smoke assumes the latest AAPL 8-K has EX-99.1. On
        # 2026-09-07 both prechange and current core fail that assumption:
        # latest is a management 8-K/A, not an earnings release. Fix the input
        # fixture here, not production selection semantics or the assertions.
        filings = srv.get_filings("AAPL", form="8-K", limit=10, detail=True)
        self.assertIsNot(filings.get("ok"), False, filings.get("error"))
        candidates = [r for r in filings["data"] if r["form"] == "8-K"
                      and any(e["exhibit"] == "EX-99.1" for e in r.get("exhibits") or [])]
        self.assertTrue(candidates, "No verified EX-99.1 fixture in the inspected filings")
        exhibit_accession = candidates[0]["accession"]
        pinned_calls = 0
        for node in nodes:
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and any(k.arg == "exhibit" for k in call.keywords):
                    call.keywords.append(ast.keyword(arg="accession", value=ast.Constant(exhibit_accession)))
                    pinned_calls += 1
        self.assertEqual(pinned_calls, 1)
        print("Legacy exhibit smoke uses verified filing accession:", exhibit_accession)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"), scope)
            import smoke_test
            smoke_test.test_edgartools()
        print(output.getvalue())
        self.assertNotIn("[FAIL", output.getvalue())
        self.assertNotIn("[SKIP", output.getvalue())
        self.assertEqual(output.getvalue().count("[PASS]"), 5)
        self.assertTrue(scope["bad_section"])
        pinned = srv.get_filing_text("AAPL", form="8-K", accession=exhibit_accession,
                                     exhibit="EX-99.1", max_chars=500)
        self.assertIsNot(pinned.get("ok"), False, pinned.get("error"))
        self.assertEqual(pinned["metadata"]["accession"], exhibit_accession)
        self.assertEqual(pinned["metadata"]["form"], "8-K")
        self.assertTrue(pinned["text"].strip())

    def test_existing_get_filing_text_pinned_first_and_last_pages(self):
        import mcp_server as srv
        for section in SECTIONS:
            first = srv.get_filing_text(TICKER, form=FORM, accession=ACCESSION,
                                        section=section, max_chars=500, offset=0)
            self.assertIsNot(first.get("ok"), False, first.get("error"))
            m = first["metadata"]
            self.assertEqual((m["accession"], m["form"]), (ACCESSION, FORM))
            self.assertEqual(m["returned_chars"], len(first["text"]))
            self.assertEqual(m["offset"], 0)
            self.assertTrue(m["has_more"])
            self.assertEqual(m["next_offset"], len(first["text"]))
            offset = max(0, m["total_chars"] - 500)
            last = srv.get_filing_text(TICKER, form=FORM, accession=ACCESSION,
                                       section=section, max_chars=500, offset=offset)
            self.assertIsNot(last.get("ok"), False, last.get("error"))
            lm = last["metadata"]
            self.assertEqual((lm["accession"], lm["form"]), (ACCESSION, FORM))
            self.assertEqual(lm["offset"], offset)
            self.assertEqual(lm["total_chars"], m["total_chars"])
            self.assertEqual(offset + len(last["text"]), m["total_chars"])
            self.assertFalse(lm["has_more"])
            self.assertIsNone(lm["next_offset"])
            print(f"Legacy get_filing_text: {section}, total_chars={m['total_chars']}, first+last pages PASS")


if __name__ == "__main__":
    unittest.main()
