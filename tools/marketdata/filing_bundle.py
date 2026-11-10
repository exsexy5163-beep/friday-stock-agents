#!/usr/bin/env python3
"""Fail-closed SEC section collection for local artifacts, never an MCP payload."""
from __future__ import annotations

import contextlib
import ctypes
from datetime import date
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import NoReturn

import core

HERE = Path(__file__).resolve().parent
BUNDLE_ROOT = HERE.parents[1] / "scratch" / "filing-bundles"
ALLOWED_ROOT = BUNDLE_ROOT
WORKER_PYTHON = HERE / ".venv" / "bin" / "python"
SOURCE = "SEC EDGAR (edgartools)"
MAX_ATTEMPTS = 2
RETRYABLE = {"PROVIDER_ERROR", "NETWORK_ERROR", "RATE_LIMITED", "PARSER_ERROR",
             "SECTION_DISCOVERY_FAILED", "EMPTY_SECTION", "WORKER_TIMEOUT"}


def run_worker(request: dict, directory: Path) -> dict:
    """Exactly one fresh process per call; full text travels through a local file."""
    try:
        safe_path(directory)
        completed = subprocess.run(
            [str(WORKER_PYTHON), "-B", str(HERE / "filing_bundle.py"), "--worker", str(directory)],
            input=json.dumps(request), capture_output=True, text=True, encoding="utf-8",
            shell=False, timeout=120,
        )
        reply = json.loads(completed.stdout)
        valid = (isinstance(reply, dict) and type(reply.get("ok")) is bool
                 and type(reply.get("pid")) is int
                 and completed.returncode == (0 if reply["ok"] else 1))
        if not valid:
            reject("WORKER_PROTOCOL_ERROR", "Malformed worker result or inconsistent exit status")
        if reply["ok"]:
            if not isinstance(reply.get("metadata"), dict):
                reject("WORKER_PROTOCOL_ERROR", "Worker metadata missing")
        else:
            error = reply.get("error")
            if not isinstance(error, dict) or not isinstance(error.get("code"), str) or type(error.get("recoverable")) is not bool:
                reject("WORKER_PROTOCOL_ERROR", "Worker error contract invalid")
        return reply
    except subprocess.TimeoutExpired:
        return worker_error("WORKER_TIMEOUT", "Worker exceeded 120 seconds and was terminated")
    except (ValueError, TypeError):
        return worker_error("WORKER_PROTOCOL_ERROR", "Worker did not return valid JSON")
    except OSError:
        return worker_error("WORKER_START_FAILED", "Could not start worker interpreter")
    except core.MarketDataError as e:
        return worker_error(e.code, e.message)


def worker_error(code: str, message: str, pid: int | None = None) -> dict:
    return {"ok": False, "pid": pid, "error": {
        "code": code, "message": message, "recoverable": code in RETRYABLE}}


def worker_main(directory: Path) -> int:
    try:
        safe_path(directory / "text.txt")
        request = json.load(sys.stdin)
        with contextlib.redirect_stdout(sys.stderr):
            result = core.fetch_filing_section_full(**request)
        with safe_path(directory / "text.txt").open("xb") as output:
            output.write(result["text"].encode("utf-8"))
        reply = {"ok": True, "pid": os.getpid(), "metadata": result["metadata"]}
    except core.MarketDataError as e:
        reply = {"ok": False, "pid": os.getpid(), "error": {
            "code": e.code, "message": e.message, "recoverable": e.recoverable}}
    except OSError:
        reply = worker_error("FILESYSTEM_ERROR", "Worker artifact write failed", os.getpid())
    except Exception:
        reply = worker_error("WORKER_PROTOCOL_ERROR", "Worker request or internal execution failed", os.getpid())
    print(json.dumps(reply, ensure_ascii=False))
    return 0 if reply["ok"] else 1


def reject(code: str, message: str) -> NoReturn:
    raise core.MarketDataError(code, message, recoverable=code in RETRYABLE)


def safe_path(path: Path) -> Path:
    """Reject traversal and existing symlink components, including scratch itself."""
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(ALLOWED_ROOT):
        reject("UNSAFE_PATH", "Output must remain under scratch/filing-bundles")
    for component in (path, *path.parents):
        if component == HERE.parents[1]:
            break
        if component.is_symlink():
            reject("UNSAFE_PATH", "Symlinks are not allowed in bundle paths")
    if not path.resolve().is_relative_to(ALLOWED_ROOT):
        reject("UNSAFE_PATH", "Resolved output escapes bundle root")
    return path


def rename_exclusive(source: Path, target: Path) -> None:
    """macOS atomic no-replace rename, including protection from late targets.

    Flags/signature verified in the SDK's sys/stdio.h. No unsafe fallback.
    """
    safe_path(source)
    safe_path(target)
    try:
        rename = ctypes.CDLL(None, use_errno=True).renamex_np
    except AttributeError:
        reject("ATOMIC_RENAME_UNAVAILABLE", "Exclusive directory rename is required (macOS)")
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    # RENAME_EXCL | RENAME_NOFOLLOW_ANY
    if rename(os.fsencode(source), os.fsencode(target), 0x00000004 | 0x00000010) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            reject("BUNDLE_EXISTS", "Rename target already exists; nothing was overwritten")
        raise OSError(code, os.strerror(code))


def checked_worker_text(result: dict, request: dict, work: Path) -> bytes:
    m = result["metadata"]
    try:
        valid_date = date.fromisoformat(m["as_of"]).isoformat() == m["as_of"]
    except (KeyError, TypeError, ValueError):
        valid_date = False
    if m.get("source") != SOURCE or type(m.get("source_tier")) is not int or m["source_tier"] != 1 or not valid_date:
        reject("WORKER_PROTOCOL_ERROR", "Worker provenance missing or invalid")
    for field in ("accession", "form", "section"):
        if m.get(field) != request[field]:
            reject(f"{field.upper()}_MISMATCH", "Worker identity differs from request")
    raw = safe_path(work / "text.txt").read_bytes()
    text = raw.decode("utf-8")
    if not text.strip():
        reject("EMPTY_SECTION", "Worker section is empty")
    if type(m.get("total_chars")) is not int or len(text) != m["total_chars"]:
        reject("CHAR_COUNT_MISMATCH", "File character count differs from worker metadata")
    return raw


def collect_sections(stage: Path, manifest: dict) -> None:
    for index, (section, info) in enumerate(manifest["sections"].items(), 1):
        request = {key: manifest[key] for key in ("ticker", "form", "accession")}
        request["section"] = section
        for attempt in range(1, MAX_ATTEMPTS + 1):
            work = stage / f".work-{index}-{attempt}"
            work.mkdir()
            info["attempts"] = attempt
            history = {"attempt": attempt, "pid": None}
            info["attempt_history"].append(history)
            try:
                result = run_worker(request, work)
                history["pid"] = result.get("pid")
                if result["ok"]:
                    raw = checked_worker_text(result, request, work)
                    relative = f"sections/section-{index:03d}.txt"
                    dest = safe_path(stage / relative)
                    with dest.open("xb") as output:
                        output.write(raw)
                    written = dest.read_bytes()
                    info.update(status="COMPLETE", file=relative, chars=len(written.decode("utf-8")),
                                sha256=hashlib.sha256(written).hexdigest(), metadata=result["metadata"])
                    history["status"] = "COMPLETE"
                    break
                error = result["error"]
            except core.MarketDataError as e:
                error = {"code": e.code, "message": e.message, "recoverable": e.recoverable}
            except (KeyError, TypeError, ValueError, AttributeError):
                error = worker_error("WORKER_PROTOCOL_ERROR", "Invalid worker metadata or text encoding")["error"]
            except OSError:
                error = worker_error("FILESYSTEM_ERROR", "Section artifact read/write failed")["error"]
            except Exception:
                error = worker_error("INTERNAL_ERROR", "Unexpected section collection failure")["error"]
            history.update(status="FAILED", error=error)
            if error["code"] not in RETRYABLE or not error.get("recoverable"):
                break
        if info["status"] == "FAILED":
            error = info["attempt_history"][-1]["error"]
            manifest["failures"].append({"section": section, "code": error["code"], "attempts": info["attempts"]})


def write_manifest(stage: Path, manifest: dict) -> None:
    safe_path(stage / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_bundle(directory: Path, ticker: str, form: str, accession: str, sections: list[str]) -> dict:
    """Read back the exact manifest/files. Raises on incomplete or damaged artifacts."""
    try:
        m = json.loads(safe_path(directory / "manifest.json").read_text(encoding="utf-8"))
        if (m["status"] != "COMPLETE" or m["failures"] or not sections
                or (m["ticker"], m["form"], m["accession"]) != (ticker, form, accession)
                or set(m["sections"]) != set(sections) or m["source"] != SOURCE or m["source_tier"] != 1
                or date.fromisoformat(m["as_of"]).isoformat() != m["as_of"]):
            reject("BUNDLE_INTEGRITY_FAILED", "Manifest identity, status or provenance invalid")
        files = set()
        for section in sections:
            info = m["sections"][section]
            relative = Path(info["file"])
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "sections":
                reject("UNSAFE_PATH", "Manifest file must be relative inside sections/")
            file = safe_path(directory / relative)
            if not file.is_relative_to(directory) or file in files:
                reject("BUNDLE_INTEGRITY_FAILED", "Duplicate or escaping section file")
            files.add(file)
            raw = file.read_bytes()
            text = raw.decode("utf-8")
            metadata = info["metadata"]
            if (info["status"] != "COMPLETE" or not text.strip()
                    or info["chars"] != len(text) or metadata["total_chars"] != len(text)
                    or info["sha256"] != hashlib.sha256(raw).hexdigest()
                    or (metadata["accession"], metadata["form"], metadata["section"]) != (accession, form, section)):
                reject("BUNDLE_INTEGRITY_FAILED", "Section status, identity, length or hash invalid")
        return m
    except (KeyError, IndexError, TypeError, ValueError, OSError) as e:
        raise core.MarketDataError("BUNDLE_INTEGRITY_FAILED", "Cannot verify bundle manifest and section files",
                                  recoverable=False) from e


def collect_bundle(ticker: str, form: str, accession: str, sections: list[str]) -> dict:
    manifest = {"status": "FAILED", "ticker": ticker, "form": form, "accession": accession,
                "source": SOURCE, "source_tier": 1, "as_of": core.today_iso(),
                "collection_method": "full-section", "existing_bundle_policy": "fail-no-overwrite",
                "max_attempts": MAX_ATTEMPTS, "sections": {}, "failures": []}
    stage = None
    lock = None
    success = None
    try:
        if not isinstance(sections, list) or not sections:
            reject("INVALID_INPUT", "At least one --section is required")
        for section in sections:
            core.validate_filing_section_request(ticker, form, accession, section)
        if len({s.strip().casefold() for s in sections}) != len(sections):
            reject("INVALID_INPUT", "Duplicate sections are not allowed")
        manifest["sections"] = {s: {"status": "FAILED", "attempts": 0, "attempt_history": []} for s in sections}
        parent = safe_path(BUNDLE_ROOT / ticker)
        target = safe_path(parent / accession)
        failed_root = safe_path(BUNDLE_ROOT / ".failed")
        if target.exists():
            reject("BUNDLE_EXISTS", "Target already exists; v1 never overwrites or reuses it")
        parent.mkdir(parents=True, exist_ok=True)
        lock_path = safe_path(parent / f".{accession}.lock")
        try:
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            reject("BUNDLE_LOCKED", "Another run or stale lock exists; do not remove an active lock")
        else:
            os.close(fd)
            lock = lock_path
        if target.exists():
            reject("BUNDLE_EXISTS", "Target appeared while acquiring lock")
        stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=parent))
        (stage / "sections").mkdir()
        collect_sections(stage, manifest)
        if not manifest["failures"] and all(s["status"] == "COMPLETE" for s in manifest["sections"].values()):
            for work in stage.glob(".work-*"):
                shutil.rmtree(safe_path(work))
            manifest["status"] = "COMPLETE"
            write_manifest(stage, manifest)
            verify_bundle(stage, ticker, form, accession, sections)
            if safe_path(target).exists():
                reject("BUNDLE_EXISTS", "Target appeared before publication")
            rename_exclusive(stage, target)
            success = {"status": "COMPLETE", "bundle_path": str(target), "failures": []}
            return success
    except core.MarketDataError as e:
        manifest["failures"].append({"code": e.code, "message": e.message, "attempts": 0})
    except OSError:
        manifest["failures"].append({"code": "FILESYSTEM_ERROR", "message": "Local artifact operation failed", "attempts": 0})
    finally:
        if lock is not None:
            try:
                safe_path(lock).unlink()
            except (OSError, core.MarketDataError):
                if success is not None:
                    success["warnings"] = ["LOCK_CLEANUP_FAILED"]
                else:
                    manifest["failures"].append({"code": "LOCK_CLEANUP_FAILED", "attempts": 0})
    manifest["status"] = "FAILED"
    result = {"status": "FAILED", "failures": manifest["failures"]}
    if stage is not None:
        try:
            write_manifest(stage, manifest)
            failed_root = safe_path(BUNDLE_ROOT / ".failed")
            failed_root.mkdir(exist_ok=True)
            failed = safe_path(failed_root / stage.name.removeprefix(".pending-"))
            rename_exclusive(stage, failed)
            result["failed_path"] = str(failed)
        except (OSError, core.MarketDataError):
            result["failures"].append({"code": "FAILED_ARTIFACT_WRITE", "attempts": 0,
                                       "message": "Could not persist failed manifest; pending directory is not a bundle"})
    return result


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(worker_main(Path(sys.argv[2])))
    sys.exit("Use marketdata filing-bundle; worker is internal")
