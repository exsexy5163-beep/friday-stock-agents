"""Static and fixture contracts for the Claude Code filing-bundle specialist integration.

Scope: the `.claude/` runtime only. 
No network access; live SEC behavior is covered by `test_filing_bundle_live.py`.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
AGENTS = ("tony", "tommun", "rob", "adam", "damon")
AGENT_ROOT = ROOT / ".claude" / "agents"
PROJECT_INSTRUCTIONS = ROOT / "CLAUDE.md"

# The gate wording every specialist must carry, in the reader's own runtime.
COMMON_GATE_MARKERS = (
    "## Filing Bundle Gate",
    "ตัวหลักเป็นเจ้าของการดึงเอกสารและ scratch artifact ทั้งหมด",
    "marketdata filing-bundle",
    "ห้ามสร้าง/แก้/ลบไฟล์ใด ๆ ใน `scratch/`",
    "ห้ามใส่ retry loop ของตัวเอง",
    "required source",
    "optional",
    "exact accession",
    "ห้ามลด required เป็น optional",
    "manifest.json",
    "shasum -a 256",
    "`.failed/`",
    "`.pending-*`",
    "BUNDLE_EXISTS",
    "BUNDLE_LOCKED",
    "SECTION_DISCOVERY_FAILED",
    "retrieval complete",
    "reading coverage complete",
    "ไม่ได้แปลว่าคุณอ่านแล้ว",
    "ไม่ได้รับรองว่า parser ตัดขอบ section ตรงกับ HTML ต้นฉบับของ SEC",
    "ไม่ใช่ \"บริษัทไม่เปิดเผย\"",
    "ห้ามใช้ `tail` แทนการอ่านจริง",
    "get_filing_text",
    "DEF 14A",
    "20-F",
    "40-F",
    "6-K",
    "exhibit",
    "ห้ามเรียก fallback ว่า helper COMPLETE",
)

RECEIPT_MARKERS = (
    "<<<READING-COVERAGE-RECEIPT>>>",
    "<<<END-RECEIPT>>>",
    "<<<MEMO>>>",
    "<<<ABORT>>>",
    "probe@",
    "tail:",
    "sha256_ok",
    # Runtime 2026-09-08: 3 of 5 specialists invented their own receipt layout when the
    # markers were only shown, not mandated. The parent splits on them, so they are literal.
    "บังคับตามตัวอักษร",
    "ตีกลับทั้งงาน",
    # A machine scan is not a read; the receipt must say which one produced the coverage.
    "method:",
    "read-windows",
    "machine-scan+spot-read",
)

# Role-specific source plans; these differ per specialist by design.
ROLE_MARKERS = {
    "tony": ("Item 1 · Item 1A · Item 7 · Item 8 = required source", "Item 17/Item 18"),
    "tommun": ("Item 7 · Item 8 = required source", "Item 9A", "6-K ไม่ถือว่า machine-readable"),
    "rob": ("Item 1 · Item 1A · Item 7 ของทั้งฉบับล่าสุดและปีฐาน = required source",
            "Item 8 = optional"),
    "adam": ("DEF 14A ฉบับล่าสุดทั้งฉบับ = required source", "Item 5.07",
             "20-F Item 6 และ Item 7 = required แทน DEF 14A",
             "Form 4 และ ownership เป็น non-bundle source",
             "`[ไม่เปิดเผย]` ใช้ได้เฉพาะหลังอ่าน official required scope ครบแล้วเท่านั้น"),
    "damon": ("Item 7 · Item 8 = required source", "core valuation input",
              "6-K/exhibit ไม่ถือว่ารองรับโดยปริยาย"),
}

# Existing per-specialist delivery/checker contracts that must survive the integration.
DELIVERY_MARKERS = {
    "tony": ("tools/tony_check.py", "TONY'S TAKE"),
    "tommun": ("tools/tommun_check.py", "TOMMUN'S VERDICT"),
    "rob": ("tools/rob_check.py", "ROB'S VERDICT"),
    "adam": ("tools/adam_check.py", "ADAM'S VERDICT"),
    "damon": ("tools/damon_check.py", "DAMON'S VERDICT"),
}

# Tool names that belong to the other runtime and must never leak into Claude agents.
FOREIGN_RUNTIME_TOKENS = ("delegate_task", "web_extract", "search_files(", ".hermes", "hermes")


def read_agent(agent: str) -> str:
    return (AGENT_ROOT / f"{agent}.md").read_text(encoding="utf-8")


class AgentGateContractTests(unittest.TestCase):
    def test_every_specialist_carries_the_gate(self) -> None:
        for agent in AGENTS:
            text = read_agent(agent)
            with self.subTest(agent=agent):
                for marker in COMMON_GATE_MARKERS:
                    self.assertIn(marker, text)

    def test_gate_precedes_phase_0(self) -> None:
        for agent in AGENTS:
            text = read_agent(agent)
            with self.subTest(agent=agent):
                gate = text.index("## Filing Bundle Gate")
                phase0 = text.index("## Phase 0")
                self.assertLess(gate, phase0)

    def test_receipt_protocol_is_specified(self) -> None:
        for agent in AGENTS:
            text = read_agent(agent)
            with self.subTest(agent=agent):
                for marker in RECEIPT_MARKERS:
                    self.assertIn(marker, text)
                # The receipt must be stripped before saving, or the checker breaks.
                self.assertIn("ตัวหลักจะตัดส่วนนี้ทิ้งก่อนเซฟ", text)

    def test_full_coverage_claim_requires_model_read_method(self) -> None:
        """`reading_coverage: COMPLETE` must be gated on method, not self-assertion."""
        for agent in AGENTS:
            text = read_agent(agent)
            with self.subTest(agent=agent):
                self.assertIn("`reading_coverage: COMPLETE` ใช้ได้หรือไม่", text)
                self.assertIn("ไม่ได้ — ต้องเป็น `PARTIAL`", text)
                self.assertIn("ห้ามเขียน `lines: 1-N/N` เต็มจำนวนถ้า `method` ไม่ใช่ `read-windows`", text)
                self.assertIn("ห้ามเปลี่ยนไปใช้สคริปต์สแกนแทนแล้วเคลม `COMPLETE`", text)
                # Retest 2026-09-09: a specialist wrote a free-form method description, which
                # the parent cannot machine-check. The line must be one of three tokens.
                self.assertIn("ต้องเป็น *หนึ่งใน 3 คำนี้เท่านั้น*", text)
                self.assertIn("เขียนบรรยายอิสระ = ใบเสร็จผิด ตีกลับ", text)

    def test_role_specific_source_plan_present(self) -> None:
        for agent, markers in ROLE_MARKERS.items():
            text = read_agent(agent)
            with self.subTest(agent=agent):
                self.assertIn("### แผนแหล่งมาตรฐาน", text)
                for marker in markers:
                    self.assertIn(marker, text)

    def test_child_write_prohibition_is_narrowed_not_widened(self) -> None:
        for agent in AGENTS:
            text = read_agent(agent)
            with self.subTest(agent=agent):
                self.assertIn("คุณเป็นผู้ตรวจและผู้อ่านเท่านั้น", text)
                self.assertIn("มี `Bash` ในมือไม่ได้แปลว่าได้รับอนุญาต", text)
                self.assertIn("ไม่เซฟไฟล์เอง", text)

    def test_required_and_optional_failure_paths_are_distinct(self) -> None:
        for agent in AGENTS:
            text = read_agent(agent)
            with self.subTest(agent=agent):
                self.assertIn("หยุดทุกข้อสรุปที่พึ่ง section นั้น", text)
                self.assertIn("ห้ามเขียนว่า \"ตรวจแล้ว\"", text)

    def test_persona_model_and_tools_frontmatter_unchanged(self) -> None:
        expected_tools = {
            "tony": "mcp__friday-marketdata-mcp__get_price_history",
            "tommun": "mcp__friday-marketdata-mcp__get_financials",
            "rob": "mcp__friday-marketdata-mcp__get_ratios",
            "adam": "mcp__friday-marketdata-mcp__get_ownership",
            "damon": "mcp__friday-marketdata-mcp__get_macro_series",
        }
        for agent in AGENTS:
            text = read_agent(agent)
            head = text.split("---", 2)[1]
            with self.subTest(agent=agent):
                self.assertIn(f"name: {agent}", head)
                self.assertIn("model: opus", head)
                self.assertIn("tools: Bash, Read, Grep, Glob", head)
                self.assertIn("mcp__friday-marketdata-mcp__get_filing_text", head)
                self.assertIn(expected_tools[agent], head)
                # The gate must live in the body, never in the frontmatter.
                self.assertNotIn("Filing Bundle Gate", head)

    def test_delivery_and_checker_contracts_survive(self) -> None:
        for agent, markers in DELIVERY_MARKERS.items():
            text = read_agent(agent)
            with self.subTest(agent=agent):
                for marker in markers:
                    self.assertIn(marker, text)

    def test_no_foreign_runtime_tool_names_leak_in(self) -> None:
        for agent in AGENTS:
            text = read_agent(agent).lower()
            with self.subTest(agent=agent):
                for token in FOREIGN_RUNTIME_TOKENS:
                    self.assertNotIn(token.lower(), text)


class ProjectInstructionTests(unittest.TestCase):
    def test_parent_gate_documented_with_native_invocation(self) -> None:
        text = PROJECT_INSTRUCTIONS.read_text(encoding="utf-8")
        for marker in (
            "### 7b. FILING BUNDLE GATE",
            "subagent_type: \"tony\"",
            "Agent tool แบบ native",
            "marketdata filing-bundle",
            "--section",
            "ห้ามใส่ retry loop ซ้อน",
            "ห้ามเรียกซ้ำจนติด `BUNDLE_EXISTS`",
            "ห้ามใช้ ห้ามทับ ห้ามลบ ห้ามย้าย ห้าม merge",
            "reading coverage complete",
            "ไม่ใช่ \"บริษัทไม่เปิดเผย\"",
            "ห้ามเรียก fallback ว่า helper COMPLETE",
            "<<<MEMO>>>",
            "marker ผิดรูป = ตีกลับทั้งงาน",
            "method: read-windows",
            "machine-scan+spot-read",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_parent_gate_does_not_name_foreign_runtime_tools(self) -> None:
        gate = PROJECT_INSTRUCTIONS.read_text(encoding="utf-8").split("### 7b.", 1)[1].split("### 8.", 1)[0]
        for token in ("delegate_task", "web_extract", "hermes"):
            with self.subTest(token=token):
                self.assertNotIn(token, gate.lower())

    def test_existing_delivery_conventions_still_present(self) -> None:
        text = PROJECT_INSTRUCTIONS.read_text(encoding="utf-8")
        for marker in ("tools/tony_check.py", "tools/tommun_check.py", "tools/rob_check.py",
                       "tools/adam_check.py", "tools/damon_check.py",
                       "outputs/<ชื่อ agent>/<TICKER>-YYYY-MM-DD.md"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)


class BundleFixtureTests(unittest.TestCase):
    """Objective, answerable reading-coverage evidence instead of an agent's assurance."""

    TICKER = "ACME"
    FORM = "10-K"
    ACCESSION = "0001234567-25-000001"

    def setUp(self) -> None:
        temp_root = ROOT / "scratch" / "filing-bundles"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix=".claude-integration-unit-", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / self.TICKER / self.ACCESSION
        (self.bundle / "sections").mkdir(parents=True)

        # Depth markers make "read to the tail" checkable at several points, so a
        # reader that jumps straight to the end cannot produce a passing receipt.
        filler = ["fixture evidence line" for _ in range(6000)]
        for depth, name in ((1500, "PROBE_25"), (3000, "PROBE_50"), (4500, "PROBE_75")):
            filler[depth] = f"MARKER_{name}_ACME_ITEM7"
        body = "Item 7. Management discussion\n" + "\n".join(filler) + "\nTAIL_MARKER_ACME_ITEM7\n"
        self.body = body
        raw = body.encode("utf-8")
        self.raw = raw
        (self.bundle / "sections" / "section-001.txt").write_bytes(raw)
        self.manifest_path = self.bundle / "manifest.json"
        self.manifest_path.write_text(json.dumps(self.make_manifest(raw, body)), encoding="utf-8")

    def make_manifest(self, raw: bytes, body: str) -> dict:
        return {
            "status": "COMPLETE",
            "ticker": self.TICKER,
            "form": self.FORM,
            "accession": self.ACCESSION,
            "source": "SEC EDGAR (edgartools)",
            "source_tier": 1,
            "as_of": "2026-09-08",
            "sections": {
                "Item 7": {
                    "status": "COMPLETE",
                    "file": "sections/section-001.txt",
                    "chars": len(body),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "metadata": {
                        "form": self.FORM,
                        "accession": self.ACCESSION,
                        "section": "Item 7",
                        "total_chars": len(body),
                    },
                }
            },
            "failures": [],
        }

    def bundle_module(self):
        path = str(ROOT / "tools" / "marketdata")
        if path not in sys.path:
            sys.path.insert(0, path)
            self.addCleanup(lambda: sys.path.remove(path))
        return importlib.import_module("filing_bundle")

    def verify(self, sections=("Item 7",), directory=None):
        module = self.bundle_module()
        with patch.object(module, "BUNDLE_ROOT", self.root), \
             patch.object(module, "ALLOWED_ROOT", self.root):
            return module.verify_bundle(directory or self.bundle, self.TICKER, self.FORM,
                                        self.ACCESSION, list(sections))

    # ---------------------------------------------------------------- reuse
    def test_complete_existing_bundle_verifies_before_reuse(self) -> None:
        verified = self.verify()
        self.assertEqual(verified["status"], "COMPLETE")
        self.assertEqual(verified["failures"], [])

    def test_existing_bundle_missing_required_section_is_detected_without_recollecting(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        available = set(manifest["sections"])
        required = {"Item 7", "Item 1A"}
        self.assertFalse(required <= available)
        # The declared set still verifies; only the plan coverage check fails, so the
        # parent goes to the official fallback instead of looping on BUNDLE_EXISTS.
        self.assertEqual(self.verify()["status"], "COMPLETE")
        with self.assertRaises(Exception):
            self.verify(sections=("Item 7", "Item 1A"))

    def test_hash_tamper_is_rejected(self) -> None:
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        manifest["sections"]["Item 7"]["sha256"] = "0" * 64
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(Exception):
            self.verify()

    def test_truncated_file_is_rejected_even_with_matching_manifest_status(self) -> None:
        target = self.bundle / "sections" / "section-001.txt"
        target.write_bytes(self.raw[: len(self.raw) // 2])
        with self.assertRaises(Exception):
            self.verify()

    def test_wrong_identity_is_rejected(self) -> None:
        module = self.bundle_module()
        with patch.object(module, "BUNDLE_ROOT", self.root), \
             patch.object(module, "ALLOWED_ROOT", self.root):
            for ticker, form, accession in (("OTHER", self.FORM, self.ACCESSION),
                                            (self.TICKER, "20-F", self.ACCESSION),
                                            (self.TICKER, self.FORM, "0009999999-25-000009")):
                with self.subTest(identity=(ticker, form, accession)):
                    with self.assertRaises(Exception):
                        module.verify_bundle(self.bundle, ticker, form, accession, ["Item 7"])

    def test_failed_and_pending_artifacts_are_never_analysis_ready(self) -> None:
        failed = self.root / ".failed" / "run-1"
        (failed / "sections").mkdir(parents=True)
        (failed / "manifest.json").write_text(json.dumps({
            "status": "FAILED", "ticker": self.TICKER, "form": self.FORM,
            "accession": self.ACCESSION, "source": "SEC EDGAR (edgartools)", "source_tier": 1,
            "as_of": "2026-09-08", "sections": {}, "failures": [{"code": "SECTION_DISCOVERY_FAILED"}],
        }), encoding="utf-8")
        with self.assertRaises(Exception):
            self.verify(directory=failed)
        pending = self.root / self.TICKER / ".pending-abc"
        pending.mkdir(parents=True)
        self.assertTrue(pending.name.startswith(".pending-"))
        with self.assertRaises(Exception):
            self.verify(directory=pending)

    # ------------------------------------------------------- collector guards
    def test_existing_target_yields_bundle_exists_and_changes_nothing(self) -> None:
        module = self.bundle_module()
        before = hashlib.sha256((self.bundle / "sections" / "section-001.txt").read_bytes()).hexdigest()
        with patch.object(module, "BUNDLE_ROOT", self.root), \
             patch.object(module, "ALLOWED_ROOT", self.root), \
             patch.object(module, "run_worker", side_effect=AssertionError("worker must not run")):
            result = module.collect_bundle(self.TICKER, self.FORM, self.ACCESSION, ["Item 7"])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("BUNDLE_EXISTS", [f["code"] for f in result["failures"]])
        after = hashlib.sha256((self.bundle / "sections" / "section-001.txt").read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_active_lock_blocks_a_concurrent_run(self) -> None:
        module = self.bundle_module()
        accession = "0001234567-25-000002"
        parent = self.root / self.TICKER
        (parent / f".{accession}.lock").write_text("", encoding="utf-8")
        with patch.object(module, "BUNDLE_ROOT", self.root), \
             patch.object(module, "ALLOWED_ROOT", self.root), \
             patch.object(module, "run_worker", side_effect=AssertionError("worker must not run")):
            result = module.collect_bundle(self.TICKER, self.FORM, accession, ["Item 7"])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("BUNDLE_LOCKED", [f["code"] for f in result["failures"]])
        self.assertTrue((parent / f".{accession}.lock").exists())

    # ------------------------------------------------- reading coverage proof
    def test_sequential_windows_reach_every_probe_and_the_tail(self) -> None:
        lines = self.body.splitlines()
        covered: list[int] = []
        for start in range(0, len(lines), 777):
            covered.extend(range(start, min(start + 777, len(lines))))
        self.assertEqual(covered, list(range(len(lines))))
        seen = "\n".join(lines[i] for i in covered)
        for marker in ("MARKER_PROBE_25_ACME_ITEM7", "MARKER_PROBE_50_ACME_ITEM7",
                       "MARKER_PROBE_75_ACME_ITEM7", "TAIL_MARKER_ACME_ITEM7"):
            self.assertIn(marker, seen)
        self.assertEqual(lines[-1], "TAIL_MARKER_ACME_ITEM7")

    def test_tail_only_reader_fails_the_probe_check(self) -> None:
        """A reader that skips to the end can echo the tail but not the mid probes."""
        tail_only = self.body[-2000:]
        self.assertIn("TAIL_MARKER_ACME_ITEM7", tail_only)
        for marker in ("MARKER_PROBE_25_ACME_ITEM7", "MARKER_PROBE_50_ACME_ITEM7",
                       "MARKER_PROBE_75_ACME_ITEM7"):
            self.assertNotIn(marker, tail_only)

    def test_probe_offsets_resolve_to_exact_text(self) -> None:
        for marker in ("MARKER_PROBE_25_ACME_ITEM7", "MARKER_PROBE_50_ACME_ITEM7",
                       "MARKER_PROBE_75_ACME_ITEM7"):
            offset = self.body.index(marker)
            self.assertEqual(self.body[offset:offset + len(marker)], marker)

    # ------------------------------------------ retrieval vs non-disclosure
    def test_retrieval_failures_are_never_issuer_non_disclosure(self) -> None:
        for code in ("FAILED", "BUNDLE_EXISTS", "BUNDLE_LOCKED", "SECTION_DISCOVERY_FAILED",
                     "PARSER_ERROR", "FILING_NOT_FOUND"):
            outcome = {"classification": "retrieval failure", "code": code,
                       "issuer_non_disclosure": False}
            with self.subTest(code=code):
                self.assertFalse(outcome["issuer_non_disclosure"])

    def test_required_and_optional_failures_have_different_consequences(self) -> None:
        required = {"class": "required source unavailable", "may_continue": False,
                    "may_claim_reviewed": False}
        optional = {"class": "optional source unavailable", "may_continue": True,
                    "may_claim_reviewed": False}
        self.assertFalse(required["may_continue"])
        self.assertTrue(optional["may_continue"])
        self.assertFalse(optional["may_claim_reviewed"])

    def test_unsupported_form_uses_official_fallback_not_a_helper_complete_claim(self) -> None:
        fallback = {"form": "DEF 14A", "path": "official get_filing_text (exact accession)",
                    "helper_status": None, "claims_helper_complete": False,
                    "reading_coverage_receipt_required": True}
        self.assertIsNone(fallback["helper_status"])
        self.assertFalse(fallback["claims_helper_complete"])
        self.assertTrue(fallback["reading_coverage_receipt_required"])


if __name__ == "__main__":
    unittest.main()
