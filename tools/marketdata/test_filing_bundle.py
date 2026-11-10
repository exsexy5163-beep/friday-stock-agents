"""Offline bundle contracts. Run with toolkit Python -m unittest discover."""
import contextlib
import hashlib
import io
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

os.environ.setdefault("EDGAR_IDENTITY", "test@example.com")
import core

TICKER = "ACME"
ACCESSION = "0001234567-25-000001"
FORM = "10-K"
TEXT = "Item 1A. Risk Factors\n" + "Full section body.\n" * 8000


class Filing:
    accession_no = ACCESSION
    form = FORM
    filing_date = "2025-02-01"
    url = "https://www.sec.gov/Archives/example.htm"

    def obj(self):
        return types.SimpleNamespace()

    def text(self):
        return TEXT


class Items:
    items = ["Item 1A", "Item 7", "Part I, Item 2"]

    def __getitem__(self, key):
        return TEXT


@contextlib.contextmanager
def provider(filing=None):
    filing = filing or Filing()
    company = types.SimpleNamespace(get_filings=lambda **kw: [filing])
    edgar = types.SimpleNamespace(Company=lambda ticker: company, set_identity=lambda value: None)
    with patch.dict(sys.modules, {"edgar": edgar}), patch.object(Filing, "obj", return_value=Items()):
        yield filing


class FullSectionTests(unittest.TestCase):
    def test_invalid_input_before_provider(self):
        for ticker, form, accession, section in [
            (TICKER, FORM, "000123456725000001", "Item 1A"),
            (TICKER, FORM, ACCESSION, " "),
            ("../ACME", FORM, ACCESSION, "Item 1A"),
            (TICKER, "", ACCESSION, "Item 1A"),
        ]:
            with self.subTest(section=section, accession=accession), provider(), patch.object(core, "_pick_filing") as pick:
                with self.assertRaises(core.MarketDataError) as cm:
                    core.fetch_filing_section_full(ticker, form, accession, section)
                self.assertEqual(cm.exception.code, "INVALID_INPUT")
                self.assertFalse(cm.exception.recoverable)
                pick.assert_not_called()

    def test_identity_mismatch(self):
        for field, value, code in [("accession_no", "0001234567-24-000009", "ACCESSION_MISMATCH"),
                                   ("form", "10-Q", "FORM_MISMATCH")]:
            f = Filing()
            setattr(f, field, value)
            with self.subTest(field=field), provider(), patch.object(core, "_pick_filing", return_value=f):
                with self.assertRaises(core.MarketDataError) as cm:
                    core.fetch_filing_section_full(TICKER, FORM, ACCESSION, "Item 1A")
                self.assertEqual(cm.exception.code, code)
                self.assertFalse(cm.exception.recoverable)

    def test_missing_standard_section_is_retrieval_failure(self):
        with provider(), patch.object(Filing, "obj", return_value=types.SimpleNamespace(items=[])):
            with self.assertRaises(core.MarketDataError) as cm:
                core.fetch_filing_section_full(TICKER, FORM, ACCESSION, "Item 7")
        self.assertEqual(cm.exception.code, "SECTION_DISCOVERY_FAILED")
        self.assertTrue(cm.exception.recoverable)

    def test_parser_and_empty_section_failures(self):
        for error in (RuntimeError("parser failure"), None):
            with self.subTest(error=error), provider(), patch.object(Filing, "obj", side_effect=error, return_value=Items()), patch.object(Items, "__getitem__", return_value=" \n"):
                with self.assertRaises(core.MarketDataError) as cm:
                    core.fetch_filing_section_full(TICKER, FORM, ACCESSION, "Item 1A")
                self.assertEqual(cm.exception.code, "PARSER_ERROR" if error else "EMPTY_SECTION")
                self.assertTrue(cm.exception.recoverable)

    def test_non_string_parser_output_is_rejected(self):
        for value in ({"text": "not a section"}, ["not a section"], b"bytes", object(), 7, None):
            with self.subTest(kind=type(value).__name__), provider(), patch.object(Items, "__getitem__", return_value=value):
                with self.assertRaises(core.MarketDataError) as cm:
                    core.fetch_filing_section_full(TICKER, FORM, ACCESSION, "Item 1A")
                self.assertEqual(cm.exception.code, "PARSER_ERROR")
                self.assertTrue(cm.exception.recoverable)

    def test_full_section_without_pagination(self):
        fn = getattr(core, "fetch_filing_section_full", None)
        self.assertTrue(callable(fn), "new public full-section function is missing")
        assert callable(fn)
        with provider():
            result = core.fetch_filing_section_full(TICKER, FORM, ACCESSION, "Item 1A")
        self.assertEqual(result["text"], TEXT)
        self.assertGreater(len(result["text"]), core.FILING_TEXT_MAX_CHARS)
        m = result["metadata"]
        self.assertEqual((m["accession"], m["form"], m["total_chars"]), (ACCESSION, FORM, len(TEXT)))
        self.assertEqual(m["source_tier"], 1)

    def test_existing_filing_text_pagination_contract(self):
        with provider():
            r = core.fetch_filing_text(TICKER, FORM, ACCESSION, "Item 1A", max_chars=500, offset=500)
        self.assertEqual(r["text"], TEXT[500:1000])
        self.assertEqual(set(r), {"ticker", "text", "metadata"})
        self.assertEqual(r["metadata"], {
            "source": "SEC EDGAR (edgartools)", "source_tier": 1, "as_of": core.today_iso(),
            "form": FORM, "filing_date": "2025-02-01", "accession": ACCESSION,
            "url": Filing.url, "scope": "section Item 1A", "total_chars": len(TEXT),
            "returned_chars": 500, "offset": 500, "has_more": True, "next_offset": 1000,
        })


# 10-K whose table of contents interleaves "Note N" rows with "Item N" rows: the parser
# labels NOTE 7 as Item 7. Body headings are inline ("ITEM 7. MD&A. text...").
MIXED_TOC_DOC = (
    "TABLE OF CONTENTS\nItem 1. Business 4\nItem 1A. Risk Factors 10\n"
    "Item 7. Management's Discussion 23\nItem 7A. Market Risk 35\nItem 8. Financial Statements 36\n"
    "Note 7 Leases 50\nItem 9A. Controls 73\n"
    "ITEM 1. BUSINESS. We make turbines.\n" + "Business body.\n" * 50 +
    "ITEM 1A. RISK FACTORS. Risks.\n" + "Risk body.\n" * 50 +
    "ITEM 7. MANAGEMENT'S DISCUSSION. Results.\n" + "MD&A body.\n" * 80 +
    "ITEM 7A. MARKET RISK. Rates.\n"
    "Item 8. Financial Statements\n" + "Statements.\n" * 20 +
    "NOTE 7. LEASES\nLease body.\n" +
    "ITEM 9A. CONTROLS AND PROCEDURES. Effective.\n"
)


class MislabelledItems:
    items = ["Item 7", "Item 8", "Item 1A"]

    def __getitem__(self, key):
        return {"Item 7": "NOTE 7. LEASES\nLease body.\n", "Item 8": "NOTE 8. GOODWILL\nGoodwill.\n",
                "Item 1A": "RISK FACTORS. Cross-reference-index style body without an Item label.\n"}[key]


class HeadingGuardTests(unittest.TestCase):
    def fetch(self, section, items=None, doc=MIXED_TOC_DOC):
        with provider(), patch.object(Filing, "obj", return_value=items or MislabelledItems()), patch.object(Filing, "text", return_value=doc):
            return core.fetch_filing_section_full(TICKER, FORM, ACCESSION, section)

    def test_note_labelled_as_item_is_replaced_by_body_heading_split(self):
        r = self.fetch("Item 7")
        self.assertTrue(r["text"].startswith("ITEM 7. MANAGEMENT'S DISCUSSION"))
        self.assertNotIn("NOTE 7", r["text"])
        self.assertNotIn("ITEM 7A", r["text"])
        self.assertIn("MD&A body.", r["text"])
        self.assertEqual(r["metadata"]["section_method"], "heading-split")
        self.assertEqual(r["metadata"]["total_chars"], len(r["text"]))

    def test_item_missing_from_parser_uses_body_not_toc_line(self):
        r = self.fetch("Item 1")
        self.assertTrue(r["text"].startswith("ITEM 1. BUSINESS."))
        self.assertIn("Business body.", r["text"])
        self.assertNotIn("RISK FACTORS", r["text"])
        self.assertEqual(r["metadata"]["section_method"], "heading-split")

    def test_item8_runs_until_next_later_item_not_embedded_note(self):
        r = self.fetch("Item 8")
        self.assertTrue(r["text"].startswith("Item 8. Financial Statements"))
        self.assertIn("NOTE 7. LEASES", r["text"])  # notes belong inside Item 8
        self.assertNotIn("ITEM 9A", r["text"])

    def test_in_sentence_cross_references_are_not_headings(self):
        doc = ("ITEM 1A. RISK FACTORS.\nRisk body.\nsubject to oversight at that project. See\n\n"
               "Item 7. \"Management's Discussion\" for more.\nMore risk body.\n"
               "ITEM 1B. UNRESOLVED STAFF COMMENTS. None.\n"
               "ITEM 7. MANAGEMENT'S DISCUSSION. Results.\nincluding those discussed below and in\n\n"
               "Item 1A. \"Risk Factors.\"\nMD&A body.\nITEM 7A. MARKET RISK. Rates.\n")
        items = types.SimpleNamespace(items=[])
        r1a = self.fetch("Item 1A", items=items, doc=doc)["text"]
        r7 = self.fetch("Item 7", items=items, doc=doc)["text"]
        self.assertTrue(r1a.startswith("ITEM 1A. RISK FACTORS.") and r1a.endswith("More risk body."))
        self.assertTrue(r7.startswith("ITEM 7. MANAGEMENT'S DISCUSSION.") and r7.endswith("MD&A body."))

    def test_short_body_item_beats_longer_toc_row(self):
        doc = ("   Item 1B. Unresolved Staff Comments                          20\n"
               "   Item 1C. Cybersecurity                                      20\n"
               "ITEM 1B. UNRESOLVED STAFF COMMENTS. None.\n\nITEM 1C. CYBERSECURITY. Program.\n"
               "Item 5.02 of Form 8-K was used.\nITEM 2. PROPERTIES. Cambridge.\n")
        items = types.SimpleNamespace(items=[])
        self.assertEqual(self.fetch("Item 1B", items=items, doc=doc)["text"], "ITEM 1B. UNRESOLVED STAFF COMMENTS. None.")
        self.assertIn("Item 5.02 of Form 8-K", self.fetch("Item 1C", items=items, doc=doc)["text"])
        with self.assertRaises(core.MarketDataError):
            self.fetch("Item 5", items=items, doc=doc)

    def test_cross_reference_index_rows_are_never_returned(self):
        doc = ("FORM 10-K CROSS REFERENCE INDEX            Page(s)\n"
               "  Item 1.            Business                       4-7, 9-10, 71-73  \n"
               "  Item 1B.           Unresolved Staff Comments      Not applicable    \n"
               "  Item 1C.           Cybersecurity                  23                \n")
        for section in ("Item 1", "Item 1B", "Item 1C"):
            with self.subTest(section=section), self.assertRaises(core.MarketDataError) as cm:
                self.fetch(section, items=types.SimpleNamespace(items=[]), doc=doc)
            self.assertEqual(cm.exception.code, "SECTION_DISCOVERY_FAILED")

    def test_text_without_any_label_is_not_a_conflict(self):
        r = self.fetch("Item 1A")
        self.assertTrue(r["text"].startswith("RISK FACTORS."))
        self.assertEqual(r["metadata"]["section_method"], "parser")

    def test_matching_label_after_table_of_contents_line_stays_parser(self):
        with provider(), patch.object(Items, "__getitem__", return_value="Table of Contents\n\nITEM 7.\xa0\xa0MD&A\nbody\n"):
            r = core.fetch_filing_section_full(TICKER, FORM, ACCESSION, "Item 7")
        self.assertEqual(r["metadata"]["section_method"], "parser")

    def test_conflict_without_body_heading_fails_closed(self):
        with self.assertRaises(core.MarketDataError) as cm:
            self.fetch("Item 7", doc="no item headings anywhere\n")
        self.assertEqual(cm.exception.code, "PARSER_ERROR")
        self.assertTrue(cm.exception.recoverable)

    def test_mcp_section_path_uses_same_guard(self):
        with provider(), patch.object(Filing, "obj", return_value=MislabelledItems()), patch.object(Filing, "text", return_value=MIXED_TOC_DOC):
            r = core.fetch_filing_text(TICKER, FORM, ACCESSION, "Item 7", max_chars=100000)
        self.assertTrue(r["text"].startswith("ITEM 7. MANAGEMENT'S DISCUSSION"))
        self.assertNotIn("NOTE 7", r["text"])

    def test_non_10k_forms_are_untouched(self):
        self.assertIsNone(core._tenk_item_key("10-Q", "Item 2"))
        self.assertIsNone(core._tenk_item_key("10-K", "Part I, Item 2"))
        self.assertEqual(core._tenk_item_key("10-K/A", "item 9a"), (9, "a"))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("filing_bundle"), "bundle helper missing")
        self.bundle = importlib.import_module("filing_bundle")
        root = Path(__file__).resolve().parents[2] / "scratch" / "filing-bundles"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix=".unit-", dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch.object(self.bundle, "BUNDLE_ROOT", self.root)
        p.start()
        self.addCleanup(p.stop)

    def worker(self, request, directory):
        (directory / "text.txt").write_bytes(TEXT.encode("utf-8"))
        return {"ok": True, "pid": 123, "metadata": {
            "accession": request["accession"], "form": request["form"],
            "section": request["section"], "total_chars": len(TEXT),
            "source": "SEC EDGAR (edgartools)", "source_tier": 1,
            "as_of": core.today_iso(), "filing_date": Filing.filing_date, "url": Filing.url,
        }}

    def collect(self, sections=None, **kwargs):
        return self.bundle.collect_bundle(TICKER, FORM, ACCESSION,
                                          sections if sections is not None else ["Item 1A", "Item 7"], **kwargs)

    def test_retry_then_success(self):
        seen = []

        def transient(request, directory):
            seen.append(directory)
            if len(seen) == 1:
                return {"ok": False, "pid": 1, "error": {"code": "PARSER_ERROR", "recoverable": True}}
            return self.worker(request, directory)

        with patch.object(self.bundle, "run_worker", side_effect=transient):
            result = self.collect(["Item 7"])
        self.assertEqual(result["status"], "COMPLETE")
        m = json.loads((Path(result["bundle_path"]) / "manifest.json").read_text())
        self.assertEqual(m["sections"]["Item 7"]["attempts"], 2)
        self.assertEqual(m["sections"]["Item 7"]["attempt_history"][0]["error"]["code"], "PARSER_ERROR")
        self.assertEqual(len(set(seen)), 2)

    def test_invalid_input_no_worker_no_files(self):
        cases = [(TICKER, FORM, "bad-accession", ["Item 1A"]),
                 (TICKER, FORM, ACCESSION, [" "]), (TICKER, FORM, ACCESSION, []),
                 (TICKER, FORM, ACCESSION, ["Item 1A", "item 1a"])]
        with patch.object(self.bundle, "run_worker", side_effect=self.worker) as run:
            for args in cases:
                with self.subTest(args=args):
                    result = self.bundle.collect_bundle(*args)
                    self.assertEqual(result["status"], "FAILED")
                    self.assertEqual(result["failures"][0]["code"], "INVALID_INPUT")
                    self.assertEqual(result["failures"][0]["attempts"], 0)
            run.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_worker_identity_mismatch_fails_without_retry(self):
        for field, wrong, code in [("accession", "0001234567-24-000001", "ACCESSION_MISMATCH"),
                                   ("form", "10-Q", "FORM_MISMATCH"),
                                   ("section", "Item 8", "SECTION_MISMATCH")]:
            def mismatch(request, directory):
                result = self.worker(request, directory)
                result["metadata"][field] = wrong
                return result
            with self.subTest(field=field), patch.object(self.bundle, "run_worker", side_effect=mismatch) as run:
                result = self.collect(["Item 1A"])
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["failures"][0]["code"], code)
                self.assertEqual(run.call_count, 1)
                self.assertFalse((self.root / TICKER / ACCESSION).exists())

    def test_worker_empty_or_truncated_output_not_complete(self):
        for content, code, attempts in [(" \n", "EMPTY_SECTION", 2), ("partial", "CHAR_COUNT_MISMATCH", 1)]:
            def partial(request, directory):
                result = self.worker(request, directory)
                (directory / "text.txt").write_text(content)
                return result
            with self.subTest(code=code), patch.object(self.bundle, "run_worker", side_effect=partial) as run:
                result = self.collect(["Item 7"])
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(result["failures"][0]["code"], code)
                self.assertEqual(run.call_count, attempts)
                self.assertFalse((self.root / TICKER / ACCESSION).exists())

    def test_existing_bundle_even_empty_directory_not_overwritten(self):
        target = self.root / TICKER / ACCESSION
        target.mkdir(parents=True)
        with patch.object(self.bundle, "run_worker", side_effect=self.worker) as run:
            result = self.collect()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "BUNDLE_EXISTS")
        run.assert_not_called()
        self.assertEqual(list(target.iterdir()), [])

    def test_symlink_parent_rejected_without_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / TICKER).symlink_to(outside, target_is_directory=True)
        with patch.object(self.bundle, "run_worker", side_effect=self.worker) as run:
            result = self.collect()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "UNSAFE_PATH")
        run.assert_not_called()
        self.assertEqual(list(outside.iterdir()), [])

    def test_worker_output_symlink_rejected(self):
        def symlink(request, directory):
            result = self.worker(request, directory)
            (directory / "text.txt").unlink()
            (directory / "text.txt").symlink_to(Path(__file__).resolve())
            return result
        with patch.object(self.bundle, "run_worker", side_effect=symlink):
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "UNSAFE_PATH")

    def test_lock_blocks_concurrent_publication(self):
        parent = self.root / TICKER
        parent.mkdir()
        lock = parent / f".{ACCESSION}.lock"
        lock.write_text("another run")
        with patch.object(self.bundle, "run_worker", side_effect=self.worker) as run:
            result = self.collect()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "BUNDLE_LOCKED")
        run.assert_not_called()
        self.assertEqual(lock.read_text(), "another run")

    def test_publish_failure_never_returns_complete(self):
        real_rename = self.bundle.rename_exclusive
        target = self.root / TICKER / ACCESSION

        def rename(path, destination):
            if destination == target:
                raise OSError("simulated publish failure")
            return real_rename(path, destination)

        with patch.object(self.bundle, "run_worker", side_effect=self.worker), patch.object(self.bundle, "rename_exclusive", rename):
            result = self.collect()
        self.assertEqual(result["status"], "FAILED")
        self.assertFalse(target.exists())
        self.assertEqual(result["failures"][0]["code"], "FILESYSTEM_ERROR")
        m = json.loads((Path(result["failed_path"]) / "manifest.json").read_text())
        self.assertEqual(m["status"], "FAILED")

    def test_exclusive_rename_never_replaces_empty_target(self):
        self.assertTrue(callable(getattr(self.bundle, "rename_exclusive", None)), "exclusive rename missing")
        source = self.root / "source"
        target = self.root / "target"
        source.mkdir()
        (source / "marker").write_text("new")
        target.mkdir()
        with self.assertRaises(core.MarketDataError) as cm:
            self.bundle.rename_exclusive(source, target)
        self.assertEqual(cm.exception.code, "BUNDLE_EXISTS")
        self.assertTrue(source.exists())
        self.assertEqual(list(target.iterdir()), [])

    def test_unexpected_worker_exception_fails_closed_without_retry(self):
        with patch.object(self.bundle, "run_worker", side_effect=RuntimeError("unexpected")) as run:
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "INTERNAL_ERROR")
        self.assertEqual(run.call_count, 1)

    def test_late_target_is_not_overwritten_by_publication(self):
        original = self.bundle.rename_exclusive
        target = self.root / TICKER / ACCESSION
        def collide(source, destination):
            if destination == target:
                target.mkdir()
            return original(source, destination)
        with patch.object(self.bundle, "run_worker", side_effect=self.worker), patch.object(self.bundle, "rename_exclusive", side_effect=collide):
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "BUNDLE_EXISTS")
        self.assertEqual(list(target.iterdir()), [])

    def test_lock_cleanup_failure_reports_warning_not_exception(self):
        unlink = Path.unlink
        def fail_lock(path, *args, **kwargs):
            if path.name.endswith(".lock"):
                raise OSError("lock cleanup failed")
            return unlink(path, *args, **kwargs)
        with patch.object(self.bundle, "run_worker", side_effect=self.worker), patch.object(Path, "unlink", fail_lock):
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "COMPLETE")
        self.assertIn("LOCK_CLEANUP_FAILED", result["warnings"])
        self.bundle.verify_bundle(Path(result["bundle_path"]), TICKER, FORM, ACCESSION, ["Item 1A"])

    def test_failed_collection_keeps_manifest_despite_lock_cleanup_error(self):
        unlink = Path.unlink
        def fail_lock(path, *args, **kwargs):
            if path.name.endswith(".lock"):
                raise OSError("lock cleanup failed")
            return unlink(path, *args, **kwargs)
        error = {"ok": False, "pid": 1, "error": {"code": "PARSER_ERROR", "recoverable": True}}
        with patch.object(self.bundle, "run_worker", return_value=error), patch.object(Path, "unlink", fail_lock):
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "FAILED")
        manifest = json.loads((Path(result["failed_path"]) / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "FAILED")
        self.assertEqual(manifest["sections"]["Item 1A"]["attempts"], 2)
        self.assertEqual([e["code"] for e in manifest["failures"]], ["PARSER_ERROR", "LOCK_CLEANUP_FAILED"])
        self.assertFalse((self.root / TICKER / ACCESSION).exists())

    def test_transport_timeout_and_bad_protocol_fail_closed(self):
        request = {"ticker": TICKER, "form": FORM, "accession": ACCESSION, "section": "Item 1A"}
        for response, code in [
            (subprocess.TimeoutExpired("worker", 120), "WORKER_TIMEOUT"),
            (subprocess.CompletedProcess([], 1, "not json", "ignored"), "WORKER_PROTOCOL_ERROR"),
            (subprocess.CompletedProcess([], 0, '{"ok": "yes"}', ""), "WORKER_PROTOCOL_ERROR"),
            (subprocess.CompletedProcess([], 2, '{"ok":true,"metadata":{}}', ""), "WORKER_PROTOCOL_ERROR"),
            (FileNotFoundError("no interpreter"), "WORKER_START_FAILED"),
        ]:
            with self.subTest(code=code), patch.object(self.bundle.subprocess, "run") as run:
                if isinstance(response, Exception):
                    run.side_effect = response
                else:
                    run.return_value = response
                result = self.bundle.run_worker(request, self.root)
                self.assertIs(result["ok"], False)
                self.assertEqual(result["error"]["code"], code)

    def test_bad_provenance_or_protocol_never_complete(self):
        for field, value in [("source", "unknown"), ("source_tier", 3), ("as_of", "not-date")]:
            def bad(request, directory):
                result = self.worker(request, directory)
                result["metadata"][field] = value
                return result
            with self.subTest(field=field), patch.object(self.bundle, "run_worker", side_effect=bad) as run:
                result = self.collect(["Item 7"])
                self.assertEqual(result["status"], "FAILED")
                self.assertEqual(run.call_count, 1)
                self.assertEqual(result["failures"][0]["code"], "WORKER_PROTOCOL_ERROR")

    def test_worker_entry_rejects_external_output_before_provider(self):
        request = {"ticker": TICKER, "form": FORM, "accession": ACCESSION, "section": "Item 1A"}
        output = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(json.dumps(request))), contextlib.redirect_stdout(output), patch.object(core, "fetch_filing_section_full", side_effect=AssertionError("provider must not run")) as fetch:
            code = self.bundle.worker_main(Path("/tmp/not-a-bundle"))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], "UNSAFE_PATH")
        fetch.assert_not_called()

    def test_cli_repeatable_comma_section_and_exit_status(self):
        import cli
        self.assertIn("filing-bundle", cli.build_parser().format_help(), "CLI command missing")
        argv = ["marketdata", "filing-bundle", TICKER, "--form", "10-Q", "--accession", ACCESSION,
                "--section", "Part I, Item 2", "--section", "Part II, Item 1A"]
        with patch.object(sys, "argv", argv), patch.object(self.bundle, "run_worker", side_effect=self.worker), contextlib.redirect_stdout(io.StringIO()) as out:
            cli.main()
        result = json.loads(out.getvalue().split("\n", 1)[1])
        self.assertEqual(result["status"], "COMPLETE")
        m = json.loads((Path(result["bundle_path"]) / "manifest.json").read_text())
        self.assertEqual(set(m["sections"]), {"Part I, Item 2", "Part II, Item 1A"})
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as cm:
            cli.main()
        self.assertNotEqual(cm.exception.code, 0)

    def test_no_company_specific_production_logic(self):
        for name in ("core.py", "cli.py", "filing_bundle.py"):
            text = (Path(__file__).parent / name).read_text()
            self.assertNotIn("ISRG", text)
            self.assertNotIn("0001035267-25-000017", text)

    def test_manifest_readback_verifier_rejects_tampering_and_escaping_paths(self):
        self.assertTrue(callable(getattr(self.bundle, "verify_bundle", None)), "readback verifier missing")
        with patch.object(self.bundle, "run_worker", side_effect=self.worker):
            result = self.collect(["Item 1A"])
        path = Path(result["bundle_path"])
        m = self.bundle.verify_bundle(path, TICKER, FORM, ACCESSION, ["Item 1A"])
        original = json.dumps(m)
        for field, value in [("file", "../../outside.txt"), ("file", str(path / "sections/section-001.txt")),
                              ("sha256", "0" * 64), ("chars", 1), ("status", "FAILED")]:
            with self.subTest(field=field, value=value):
                damaged = json.loads(original)
                damaged["sections"]["Item 1A"][field] = value
                (path / "manifest.json").write_text(json.dumps(damaged))
                with self.assertRaises(core.MarketDataError):
                    self.bundle.verify_bundle(path, TICKER, FORM, ACCESSION, ["Item 1A"])

    def test_corrupted_staging_file_never_published(self):
        original = self.bundle.write_manifest

        def corrupt(stage, manifest):
            original(stage, manifest)
            if manifest["status"] == "COMPLETE":
                (stage / "sections" / "section-001.txt").write_bytes(b"tampered")

        with patch.object(self.bundle, "run_worker", side_effect=self.worker), patch.object(self.bundle, "write_manifest", side_effect=corrupt):
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "FAILED")
        self.assertFalse((self.root / TICKER / ACCESSION).exists())

    def test_invalid_utf8_worker_file_returns_failed_manifest(self):
        def corrupt(request, directory):
            result = self.worker(request, directory)
            (directory / "text.txt").write_bytes(b"\xff")
            return result
        with patch.object(self.bundle, "run_worker", side_effect=corrupt) as run:
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failures"][0]["code"], "WORKER_PROTOCOL_ERROR")
        self.assertEqual(run.call_count, 1)

    def test_one_section_fails_twice_no_completed_publish(self):
        def failed(request, directory):
            if request["section"] == "Item 1A":
                return self.worker(request, directory)
            (directory / "text.txt").write_text("partial output")
            return {"ok": False, "pid": 1, "error": {"code": "SECTION_DISCOVERY_FAILED", "recoverable": True}}

        with patch.object(self.bundle, "run_worker", side_effect=failed) as run:
            result = self.collect()
        self.assertEqual(result["status"], "FAILED")
        self.assertNotIn("bundle_path", result)
        self.assertFalse((self.root / TICKER / ACCESSION).exists())
        self.assertEqual(run.call_count, 3)
        failed_path = Path(result["failed_path"])
        self.assertTrue(failed_path.is_relative_to(self.root / ".failed"))
        m = json.loads((failed_path / "manifest.json").read_text())
        self.assertEqual(m["status"], "FAILED")
        self.assertEqual(m["sections"]["Item 1A"]["status"], "COMPLETE")
        self.assertEqual(m["sections"]["Item 7"]["status"], "FAILED")
        self.assertEqual(m["sections"]["Item 7"]["attempts"], 2)
        self.assertEqual(m["failures"][0]["code"], "SECTION_DISCOVERY_FAILED")

    def test_all_sections_complete_files_and_hashes(self):
        with patch.object(self.bundle, "run_worker", side_effect=self.worker) as run:
            result = self.collect()
        self.assertEqual(result["status"], "COMPLETE")
        path = self.root / TICKER / ACCESSION
        self.assertEqual(Path(result["bundle_path"]), path)
        m = json.loads((path / "manifest.json").read_text())
        self.assertEqual(m["status"], "COMPLETE")
        self.assertEqual(m["accession"], ACCESSION)
        self.assertEqual(m["form"], FORM)
        self.assertEqual(m["failures"], [])
        self.assertEqual(set(m["sections"]), {"Item 1A", "Item 7"})
        self.assertEqual(run.call_count, 2)
        for info in m["sections"].values():
            self.assertEqual(info["status"], "COMPLETE")
            self.assertEqual(info["attempts"], 1)
            relative = Path(info["file"])
            self.assertFalse(relative.is_absolute())
            self.assertTrue((path / relative).resolve().is_relative_to(path))
            raw = (path / relative).read_bytes()
            self.assertEqual(info["chars"], len(raw.decode("utf-8")))
            self.assertEqual(info["sha256"], hashlib.sha256(raw).hexdigest())

    def test_real_worker_processes_use_exact_interpreter_without_shell(self):
        self.assertTrue(hasattr(self.bundle, "subprocess"), "subprocess transport missing")
        fake = self.root / "fake-provider"
        fake.mkdir()
        (fake / "edgar.py").write_text('''import os
from pathlib import Path
def set_identity(value): pass
class Items:
    items = ["Item 1A"]
    def __getitem__(self, key): return "Item 1A. Risk Factors\\nComplete fake body."
class Filing:
    accession_no = "0001234567-25-000001"
    form = "10-K"
    filing_date = "2025-02-01"
    url = "https://www.sec.gov/Archives/example.htm"
    def obj(self):
        log = Path(os.environ["BUNDLE_FAKE_LOG"])
        first = not log.exists()
        with log.open("a") as f: f.write(str(os.getpid()) + "\\n")
        if first: raise RuntimeError("fresh-process fixture")
        return Items()
class Company:
    def __init__(self, ticker): pass
    def get_filings(self, **kwargs): return [Filing()]
''', encoding="utf-8")
        log = self.root / "pids.txt"
        real_run = subprocess.run
        calls = []

        def launch(args, **kwargs):
            calls.append((args, kwargs.copy()))
            kwargs["env"] = {**os.environ, "PYTHONPATH": str(fake), "BUNDLE_FAKE_LOG": str(log)}
            return real_run(args, **kwargs)

        with patch.object(self.bundle.subprocess, "run", side_effect=launch):
            result = self.collect(["Item 1A"])
        self.assertEqual(result["status"], "COMPLETE")
        m = json.loads((Path(result["bundle_path"]) / "manifest.json").read_text())
        info = m["sections"]["Item 1A"]
        results = info["attempt_history"]
        self.assertEqual(info["attempts"], 2)
        self.assertEqual(results[0]["error"]["code"], "PARSER_ERROR")
        pids = log.read_text().splitlines()
        self.assertEqual(len(pids), 2)
        self.assertNotEqual(pids[0], pids[1])
        self.assertEqual([r["pid"] for r in results], [int(pid) for pid in pids])
        for args, kwargs in calls:
            self.assertIsInstance(args, list)
            self.assertEqual(args[0], "__FRIDAY_ROOT__/tools/marketdata/.venv/bin/python")
            self.assertIs(kwargs["shell"], False)
        self.assertTrue((Path(result["bundle_path"]) / info["file"]).read_text().startswith("Item 1A"))


if __name__ == "__main__":
    unittest.main()
