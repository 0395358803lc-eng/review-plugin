#!/usr/bin/env python3
"""Run-local workflow gate with immutable server and folder binding.

Run this helper only on the selected Remote Desktop Commander device.
Every command must repeat the exact remote device ID, connection link ID,
VIDEO_ROOT and (when selected) LOGO_ROOT stored at initialization.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import platform
import wave
import shutil
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path

SCHEMA_VERSION = 9
STEP_COUNT = 40
COMPLETE = {"pass", "skipped"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def same_path(left, right) -> bool:
    return os.path.normcase(str(canonical(Path(left)))) == os.path.normcase(str(canonical(Path(right))))


def within(path: Path, root: Path, label: str) -> Path:
    p, r = canonical(path), canonical(root)
    try:
        p.relative_to(r)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside WORKSPACE: {p}") from exc
    return p


def workspace_root(video_root: Path) -> Path:
    video = canonical(video_root)
    candidate = video / "WORKSPACE"
    is_junction = getattr(candidate, "is_junction", lambda: False)
    if candidate.is_symlink() or is_junction():
        raise RuntimeError("WORKSPACE_LINK_FORBIDDEN: cannot write into a symlink or junction")
    work = canonical(candidate)
    if not candidate.is_dir() or work.parent != video or not same_path(work, candidate):
        raise RuntimeError("WORKSPACE_MISSING_OR_MOVED: bind must create a real VIDEO_ROOT/WORKSPACE first")
    return work


def roots_disjoint(video_root: Path, logo_root: Path | None):
    if logo_root is None:
        return
    v, l = canonical(video_root), canonical(logo_root)
    if v == l or v in l.parents or l in v.parents:
        raise ValueError("VIDEO_ROOT and LOGO_ROOT must be separate, non-overlapping folders; LOGO_ROOT is read-only")


def folder_identity(path: Path) -> dict:
    p = canonical(path)
    if not p.is_dir():
        raise NotADirectoryError(f"Selected folder is missing or is not a directory: {p}")
    st = p.stat()
    return {
        "resolved_path": os.path.normcase(str(p)),
        "device": int(getattr(st, "st_dev", 0)),
        "inode": int(getattr(st, "st_ino", 0)),
    }


def machine_fingerprint() -> str:
    """Match server_binding.py fingerprint; fail closed if no stable machine ID."""
    system = platform.system()
    stable_id = None
    if system == "Windows":
        try:
            import winreg  # type: ignore
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                stable_id = winreg.QueryValueEx(key, "MachineGuid")[0]
        except Exception as exc:
            raise RuntimeError("Cannot read Windows MachineGuid; server binding cannot be verified") from exc
    elif system == "Linux":
        for candidate in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
            try:
                stable_id = candidate.read_text(encoding="utf-8").strip()
                if stable_id:
                    break
            except OSError:
                pass
        if not stable_id:
            raise RuntimeError("Cannot read Linux machine-id; server binding cannot be verified")
    elif system == "Darwin":
        result = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True, check=True, timeout=10)
        for line in result.stdout.splitlines():
            if '"IOPlatformUUID"' in line:
                stable_id = line.split("=", 1)[-1].strip().strip('"')
                break
        if not stable_id:
            raise RuntimeError("Cannot read macOS IOPlatformUUID; server binding cannot be verified")
    else:
        raise RuntimeError(f"Unsupported OS for strict server binding: {system}")
    material = "\n".join((system, platform.machine(), str(stable_id)))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def evidence_records(paths, video_root: Path):
    if not paths:
        raise ValueError("At least one evidence file is required")
    records = []
    for raw in paths:
        p = within(Path(raw), workspace_root(video_root), "Evidence file")
        if not p.is_file():
            raise FileNotFoundError(p)
        records.append({"path": str(p), "sha256": sha256(p), "size_bytes": p.stat().st_size})
    return records


PLAN_METADATA_KEYS = (
    "category", "description", "version", "current_version", "estimated_size_bytes",
    "estimated_download_bytes", "estimated_duration_minutes", "risk",
    "reason", "source", "verification", "already_present", "required",
    "action", "license", "notes", "cache_path",
)


def installation_plan_snapshot(items):
    return [
        {key: item[key] for key in ("id", "name", "target_path", *PLAN_METADATA_KEYS) if key in item}
        for item in items
    ]


def canonical_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_plan_file(data):
    """Reject any change to the actual installation plan since it was reviewed."""
    plan = data["preflight"].get("installation_plan", {})
    if not plan.get("configured"):
        raise ValueError("INSTALL_PLAN_NOT_CONFIGURED")
    p = within(Path(plan["plan_file"]), workspace_root(Path(data["video_root"])), "Installation plan")
    if not p.is_file() or sha256(p) != plan.get("plan_file_sha256"):
        raise ValueError("INSTALL_PLAN_FILE_CHANGED: stop and re-present/re-approve the edited plan")
    raw = json.loads(p.read_text(encoding="utf-8"))
    if canonical_hash(installation_plan_snapshot(normalize_plan_items(raw["items"], Path(data["video_root"])))) != plan.get("plan_sha256"):
        raise ValueError("INSTALL_PLAN_SNAPSHOT_MISMATCH: source plan no longer matches the approved snapshot")
    if canonical_hash(plan.get("plan_snapshot", [])) != plan.get("plan_sha256"):
        raise ValueError("INSTALL_PLAN_HASH_MISMATCH")
    return plan


def normalize_plan_items(items, video_root):
    if not isinstance(items, list):
        raise ValueError("Plan must contain an ordered items array")
    seen, normalized = set(), []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Installation item at position {i} must be an object")
        item_id, name = str(item.get("id", "")).strip(), str(item.get("name", "")).strip()
        if not item_id or not name or item_id in seen:
            raise ValueError(f"Invalid or duplicate installation item at position {i}")
        seen.add(item_id)
        target = item.get("target_path")
        if target:
            target_path = Path(target)
            if not target_path.is_absolute():
                raise ValueError(f"Installation target {item_id} must be an absolute path")
            target = str(within(target_path, workspace_root(video_root), f"Installation target {item_id}"))
        entry = {"order": i, "id": item_id, "name": name, "target_path": target}
        for key in PLAN_METADATA_KEYS:
            if key in item:
                entry[key] = item[key]
        already_present = bool(item.get("already_present")) or str(item.get("action", "")).strip().lower() in {"already_present", "already-present", "no_action", "skip"}
        if already_present and not (item.get("current_version") or item.get("version")):
            raise ValueError(f"Already-present item {item_id} must include a verified current version")
        if already_present and not item.get("verification"):
            raise ValueError(f"Already-present item {item_id} must include its verification method")
        entry.update({"status": "pending", "evidence": [], "history": [], "already_present": already_present})
        normalized.append(entry)
    return normalized


QC_GATES = {9: 1, 16: 2, 20: 3, 24: 4, 28: 5, 32: 6, 36: 7, 39: 8}


def _positive_number(value, field, low=0, high=1_000_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low < value <= high:
        raise ValueError(f"SCRIPT_DURATION_INVALID_{field}: expected number in ({low}, {high}]")
    return float(value)


def _read_run_json(data, raw, label):
    base = workspace_root(Path(data["video_root"])) / "runs" / data["run_id"]
    path = within(Path(raw), base, label)
    if not path.is_file():
        raise ValueError(f"{label.upper().replace(' ', '_')}_MISSING: {path}")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("run_id") != data["run_id"]:
        raise ValueError(f"{label.upper().replace(' ', '_')}_WRONG_RUN")
    return path, doc


def _normalize_review_text(text):
    return " ".join(text.casefold().split())


def audit_review_script(data, declaration):
    """Machine-check script length and evidence-linked plot coverage for QC3.

    Does not replace the human semantic review of script or source film.
    """
    if not isinstance(declaration, dict) or set(declaration) != {"dossier", "plan", "script", "coverage"}:
        raise ValueError("QC3_EDITORIAL_AUDIT_REQUIRED: dossier, plan, script and coverage paths must be declared")
    dossier_file, dossier = _read_run_json(data, declaration["dossier"], "Story dossier")
    plan_file, plan = _read_run_json(data, declaration["plan"], "Editorial duration plan")
    coverage_file, coverage = _read_run_json(data, declaration["coverage"], "Script event coverage")
    base = workspace_root(Path(data["video_root"])) / "runs" / data["run_id"]
    script_file = within(Path(declaration["script"]), base, "Review script V2")
    if not script_file.is_file() or script_file.suffix.lower() != ".txt":
        raise ValueError("QC3_SCRIPT_V2_MISSING: require a real UTF-8 TXT script")
    script_text = script_file.read_text(encoding="utf-8-sig").strip()
    word_count = len(script_text.split())  # Vietnamese whitespace-delimited tokens, NOT linguistic word segmentation.
    if word_count < 80:
        raise ValueError("QC3_SCRIPT_TOO_SHORT: script content is insufficient for a review")
    script_norm = _normalize_review_text(script_text)
    source_sec = _positive_number(dossier.get("source_duration_sec"), "SOURCE_DURATION", low=30)
    events = dossier.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("QC3_STORY_EVENTS_MISSING: step 16 must index actual source events")
    by_id = {}
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("QC3_EVENT_INVALID")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in by_id:
            raise ValueError("QC3_EVENT_ID_DUPLICATE_OR_MISSING")
        sec = event.get("source_start_sec")
        if isinstance(sec, bool) or not isinstance(sec, (int, float)) or not 0 <= sec <= source_sec:
            raise ValueError("QC3_EVENT_TIMESTAMP_INVALID")
        if len(str(event.get("summary", "")).strip()) < 18:
            raise ValueError("QC3_EVENT_SUMMARY_MISSING")
        if not str(event.get("phase", "")).strip():
            raise ValueError("QC3_EVENT_PHASE_MISSING")
        if not isinstance(event.get("required"), bool):
            raise ValueError("QC3_EVENT_REQUIRED_FLAG_MISSING")
        by_id[event_id] = event
    required = {key for key, e in by_id.items() if e["required"]}
    if not required:
        raise ValueError("QC3_NO_REQUIRED_EVENTS")
    # Source coverage must be plausible, not just one invented plot point for a feature film.
    min_indexed = max(3, min(12, int(source_sec / 900)))
    if len(events) < min_indexed:
        raise ValueError(f"QC3_DOSSIER_UNDERINDEXED: {len(events)} events; inspect at least {min_indexed} across the source")
    if not isinstance(coverage.get("events"), list):
        raise ValueError("QC3_EVENT_COVERAGE_MISSING")
    seen, proof_quotes = set(), set()
    for entry in coverage["events"]:
        if not isinstance(entry, dict):
            raise ValueError("QC3_EVENT_COVERAGE_INVALID")
        key = entry.get("event_id")
        if key not in by_id or key in seen:
            raise ValueError("QC3_COVERAGE_EVENT_UNKNOWN_OR_DUPLICATE")
        seen.add(key)
        if entry.get("status") == "covered":
            quote = _normalize_review_text(str(entry.get("quote", "")))
            if len(quote) < 18 or quote not in script_norm or quote in proof_quotes:
                raise ValueError("QC3_COVERAGE_QUOTE_UNVERIFIED: quote must be unique and present in actual V2 script")
            proof_quotes.add(quote)
        elif entry.get("status") == "omitted":
            if by_id[key]["required"] or len(str(entry.get("reason", "")).strip()) < 12:
                raise ValueError("QC3_REQUIRED_EVENT_OMITTED_OR_REASON_MISSING")
        else:
            raise ValueError("QC3_COVERAGE_STATUS_INVALID")
    if required - seen or any(entry.get("status") != "covered" for entry in coverage["events"] if entry.get("event_id") in required):
        raise ValueError("QC3_REQUIRED_PLOT_GAP: essential story events missing from V2 script")
    target_sec = _positive_number(plan.get("target_duration_sec"), "TARGET_DURATION", low=30)
    rate_wpm = _positive_number(plan.get("estimated_tts_wpm"), "TTS_RATE", low=60, high=420)
    if plan.get("target_source") not in {"user", "story_derived"}:
        raise ValueError("QC3_TARGET_SOURCE_REQUIRED: user target or story-derived target")
    if len(str(plan.get("rationale", "")).strip()) < 35:
        raise ValueError("QC3_TARGET_RATIONALE_REQUIRED: explain event density, film and pacing")
    if plan.get("dossier_sha256") != sha256(dossier_file):
        raise ValueError("QC3_DOSSIER_PLAN_MISMATCH")
    sections = plan.get("sections")
    if not isinstance(sections, list) or len(sections) < 3:
        raise ValueError("QC3_SECTION_BUDGET_REQUIRED: use at least three justified sections")
    names, section_sum = set(), 0
    for section in sections:
        if not isinstance(section, dict) or not str(section.get("name", "")).strip() or section["name"] in names:
            raise ValueError("QC3_SECTION_INVALID_OR_DUPLICATE")
        names.add(section["name"])
        section_sum += _positive_number(section.get("duration_sec"), "SECTION_DURATION")
    if abs(section_sum - target_sec) > max(2, target_sec * .03):
        raise ValueError("QC3_SECTION_BUDGET_MISMATCH")
    estimate = word_count / rate_wpm * 60
    if estimate < target_sec * .80:
        raise ValueError(f"QC3_SCRIPT_TOO_SHORT_FOR_TARGET: expected {target_sec:.1f}s, estimated {estimate:.1f}s at {rate_wpm:.1f} WPM; review missing scenes before rewriting")
    if estimate > target_sec * 1.20:
        raise ValueError(f"QC3_SCRIPT_TOO_LONG_FOR_TARGET: expected {target_sec:.1f}s, estimated {estimate:.1f}s; revise pacing or justify a new target")
    files = {name: {"path": str(path), "sha256": sha256(path)} for name, path in
             (("dossier", dossier_file), ("plan", plan_file), ("script", script_file), ("coverage", coverage_file))}
    return {"word_count_whitespace": word_count, "estimated_duration_sec": round(estimate, 2),
            "target_duration_sec": target_sec, "estimated_tts_wpm": rate_wpm,
            "target_source": plan["target_source"], "source_duration_sec": source_sec,
            "required_events": len(required), "verified_quotes": len(proof_quotes),
            "files": files}


def verify_editorial_audit(data):
    editorial = data.get("qc_gates", {}).get("3", {}).get("editorial_audit")
    if not isinstance(editorial, dict):
        raise ValueError("QC3_EDITORIAL_AUDIT_MISSING")
    files = editorial.get("files", {})
    if set(files) != {"dossier", "plan", "script", "coverage"}:
        raise ValueError("QC3_EDITORIAL_FILES_MISSING")
    paths = {k: v["path"] for k, v in files.items()}
    for rec in files.values():
        path = within(Path(rec["path"]), workspace_root(Path(data["video_root"])), "Editorial evidence")
        if not path.is_file() or sha256(path) != rec["sha256"]:
            raise ValueError("QC3_EDITORIAL_SOURCE_CHANGED: previously audited script/plan/evidence modified")
    actual = audit_review_script(data, paths)
    if actual != editorial:
        raise ValueError("QC3_EDITORIAL_AUDIT_CHANGED")
    return editorial


def audit_tts_master(data, declaration):
    if not isinstance(declaration, dict) or set(declaration) != {"master_wav"}:
        raise ValueError("QC4_TTS_DURATION_AUDIT_REQUIRED: master_wav must be supplied")
    editorial = verify_editorial_audit(data)
    base = workspace_root(Path(data["video_root"])) / "runs" / data["run_id"]
    master = within(Path(declaration["master_wav"]), base, "TTS master WAV")
    if not master.is_file():
        raise ValueError("QC4_TTS_MASTER_NOT_FOUND")
    try:
        with wave.open(str(master), "rb") as wav:
            audio_sec = wav.getnframes() / wav.getframerate()
            audio_params = {"channels": wav.getnchannels(), "sample_rate": wav.getframerate(),
                            "frames": wav.getnframes()}
    except (wave.Error, ZeroDivisionError, EOFError) as exc:
        raise ValueError("QC4_TTS_WAV_UNREADABLE: require genuine PCM WAV and verify duration") from exc
    if audio_sec <= 0:
        raise ValueError("QC4_TTS_EMPTY")
    target_sec = editorial["target_duration_sec"]
    if audio_sec < target_sec * .80 or audio_sec > target_sec * 1.20:
        raise ValueError(f"QC4_TTS_DURATION_MISMATCH: actual {audio_sec:.1f}s vs planned {target_sec:.1f}s; revise script and obtain renewed step approvals before moving on")
    return {"master_wav": str(master), "master_sha256": sha256(master),
            "actual_duration_sec": round(audio_sec, 3), "target_duration_sec": target_sec,
            "audio_params": audio_params, "qc3_script_sha256": editorial["files"]["script"]["sha256"]}


def verify_tts_master(data):
    saved = data.get("qc_gates", {}).get("4", {}).get("tts_duration_audit")
    if not saved:
        raise ValueError("QC4_TTS_DURATION_AUDIT_MISSING")
    actual = audit_tts_master(data, {"master_wav": saved["master_wav"]})
    if actual != saved:
        raise ValueError("QC4_TTS_AUDIO_CHANGED: narration/master no longer matches approved audit")
    return actual



def ensure_qc_passed(data, step):
    gate = QC_GATES.get(step)
    if gate is None:
        return
    qc = data.get("qc_gates", {}).get(str(gate), {})
    if qc.get("status") != "pass" or qc.get("step") != step:
        raise ValueError(f"QC{gate}_REQUIRED: step {step:02d} cannot PASS without a verified QC report")
    path = within(Path(qc["report"]), workspace_root(Path(data["video_root"])), "QC report")
    if not path.is_file() or sha256(path) != qc["report_sha256"]:
        raise ValueError(f"QC{gate}_REPORT_CHANGED: QC report is missing or modified")
    for item in qc.get("evidence", []):
        f = within(Path(item["path"]), workspace_root(Path(data["video_root"])), "QC evidence")
        if not f.is_file() or sha256(f) != item["sha256"]:
            raise ValueError(f"QC{gate}_EVIDENCE_CHANGED: report evidence was modified")
    if gate == 3:
        verify_editorial_audit(data)
    elif gate == 4:
        verify_tts_master(data)
    elif gate in {5, 8}:
        verify_tts_master(data)


def validate_command_gate(data, phase, step=None, item_id=None):
    """Pure state gate: used by the remote exec wrapper before launching subprocesses."""
    blocker = data.get("blocker") or {}
    if phase == "repair":
        if blocker.get("status") != "open" or blocker.get("step") != step:
            raise ValueError("REPAIR_BLOCKER_REQUIRED: no matching open issue")
        if blocker.get("approval_required") and not blocker.get("repair_approved"):
            raise ValueError("REPAIR_APPROVAL_REQUIRED: risky repair has not been approved")
        return
    if blocker.get("status") == "open":
        raise ValueError("BLOCKED: fix the current issue before running other commands")
    if phase in {"install", "preflight"}:
        if data["preflight"]["status"] != "running":
            raise ValueError("PREFLIGHT_NOT_RUNNING")
        plan = verify_plan_file(data)
        if plan.get("approval", {}).get("status") != "approved" or plan["approval"].get("plan_sha256") != plan["plan_sha256"]:
            raise ValueError("INSTALL_PLAN_NOT_APPROVED")
        if phase == "install":
            current = next((x for x in plan["items"] if x["status"] != "pass"), None)
            if not current or current["id"] != item_id or current["status"] != "running":
                raise ValueError("INSTALL_ITEM_NOT_RUNNING_OR_NOT_CURRENT")
        elif any(x["status"] != "pass" for x in plan["items"]):
            raise ValueError("PREFLIGHT_PENDING_INSTALLATIONS")
        return
    if phase == "step":
        if not isinstance(step, int) or step < 1 or step > STEP_COUNT or current_step(data) != step:
            raise ValueError("WRONG_CURRENT_STEP")
        rec = get_record(data, step)
        approval = data.get("step_approvals", {}).get(str(step), {})
        if rec["status"] != "running" or approval.get("status") != "consumed":
            raise ValueError("STEP_APPROVAL_NOT_CONSUMED_OR_STEP_NOT_RUNNING")
        if step >= 21 and not data.get("voice_selection"):
            raise ValueError("VOICE_SELECTION_REQUIRED")
        return
    raise ValueError("COMMAND_PHASE_REQUIRED: use install/preflight/step/repair")


def step_approval_hash(data, step):
    previous = data["preflight"] if step == 1 else data["steps"][step - 2]
    plan = data["preflight"].get("installation_plan", {})
    return canonical_hash({
        "run_id": data["run_id"],
        "step": step,
        "server_label": data["server_label"],
        "remote_device_id": data["remote_device_id"],
        "remote_link_id": data["remote_link_id"],
        "server_fingerprint": data["server_fingerprint"],
        "video_root": data["video_root"],
        "workspace_root": data["workspace_root"],
        "logo_root": data["logo_root"],
        "installation_plan_sha256": plan.get("plan_sha256"),
        "previous_status": previous.get("status"),
        "previous_evidence": previous.get("evidence", []),
        "voice_selection": data.get("voice_selection") if step >= 21 else None,
    })


def approval_manifest_payload(data):
    plan = data["preflight"].get("installation_plan", {})
    return {
        "schema_version": 1,
        "run_id": data["run_id"],
        "binding": {
            "server_label": data["server_label"],
            "remote_device_id": data["remote_device_id"],
            "remote_link_id": data["remote_link_id"],
            "server_fingerprint": data["server_fingerprint"],
            "video_root": data["video_root"],
            "workspace_root": data["workspace_root"],
            "logo_root": data["logo_root"],
        },
        "installation_plan": {
            "configured": plan.get("configured", False),
            "plan_snapshot": plan.get("plan_snapshot", []),
            "plan_sha256": plan.get("plan_sha256"),
            "plan_file_sha256": plan.get("plan_file_sha256"),
            "approval": plan.get("approval", {"status": "pending"}),
        },
        "step_approvals": data.get("step_approvals", {}),
        "repair_approval": (data.get("blocker") or {}).get("repair_approved", False),
        "qc_gates": data.get("qc_gates", {}),
    }


def write_approval_manifest(state_file: Path, data):
    atomic_save(state_file.with_name("approval_manifest.json"), approval_manifest_payload(data))


def next_action(data):
    blocker = data.get("blocker") or {}
    if blocker.get("status") == "open":
        return "repair_blocked_step"
    step = current_step(data)
    if step is None:
        return "run_complete"
    if step == 0:
        if data["preflight"].get("status") != "running":
            return "start_preflight"
        plan = data["preflight"].get("installation_plan", {})
        if not plan.get("configured"):
            return "prepare_install_plan"
        if plan.get("approval", {}).get("status") != "approved":
            return "approve_install_plan"
        current = next((x for x in plan.get("items", []) if x["status"] not in COMPLETE), None)
        if current:
            return f"install_item_{current['order']:02d}_{current['id']}"
        return "complete_preflight"
    if step == 21 and not data.get("voice_selection"):
        return "select_voice"
    rec = get_record(data, step)
    if rec.get("status") == "running":
        return f"execute_step_{step:02d}"
    approval = data.get("step_approvals", {}).get(str(step), {})
    if approval.get("status") != "approved":
        return f"approve_step_{step:02d}"
    return f"execute_step_{step:02d}"


def binding_snapshot(data: dict) -> dict:
    keys = (
        "schema_version", "run_id", "server_label", "remote_device_id", "remote_link_id",
        "server_fingerprint", "video_root", "video_root_identity", "workspace_root", "workspace_root_identity", "logo_root",
        "logo_root_identity", "bound_at",
    )
    return {key: data.get(key) for key in keys}


@contextlib.contextmanager
def locked(state_path: Path):
    lock = state_path.with_name(state_path.name + ".lock")
    payload = {"pid": os.getpid(), "host_fingerprint": machine_fingerprint(), "created_at": now()}
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("Run state is locked; do not start a second writer or remove the lock without verifying the process") from exc
    try:
        os.write(fd, json.dumps(payload).encode("utf-8"))
        os.fsync(fd)
        yield
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)


def atomic_save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def load_state(path: Path):
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported state schema; expected {SCHEMA_VERSION}; start a new run on the selected server")
    video_root = Path(data["video_root"]).resolve()
    within(path, video_root, "State file")
    work = workspace_root(video_root)
    if data.get("workspace_root") != str(work) or folder_identity(work) != data.get("workspace_root_identity"):
        raise RuntimeError("WORKSPACE_IDENTITY_MISMATCH: this run belongs to a different WORKSPACE")
    expected_state = work / "runs" / data["run_id"] / "state.json"
    if not same_path(path, expected_state):
        raise ValueError("State file must be this run's VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/state.json")
    logo_root = Path(data["logo_root"]).resolve() if data.get("logo_root") else None
    roots_disjoint(video_root, logo_root)
    if machine_fingerprint() != data.get("server_fingerprint"):
        raise RuntimeError("SERVER_BINDING_MISMATCH: this state belongs to a different machine; stop here and do not switch servers")
    if folder_identity(video_root) != data.get("video_root_identity"):
        raise RuntimeError("VIDEO_ROOT_IDENTITY_MISMATCH: selected video folder identity changed; do not substitute another folder")
    if logo_root and folder_identity(logo_root) != data.get("logo_root_identity"):
        raise RuntimeError("LOGO_ROOT_IDENTITY_MISMATCH: selected logo folder identity changed; do not substitute another folder")
    binding_file = path.with_name("binding.json")
    if not binding_file.is_file():
        raise RuntimeError("BINDING_MANIFEST_MISSING: immutable run binding manifest is missing")
    binding = json.loads(binding_file.read_text(encoding="utf-8"))
    if binding != binding_snapshot(data):
        raise RuntimeError("BINDING_MANIFEST_MISMATCH: server or folder binding was changed; stop this run")
    approval_file = path.with_name("approval_manifest.json")
    if not approval_file.is_file():
        raise RuntimeError("APPROVAL_MANIFEST_MISSING: approval audit file is missing; stop this run")
    approval_data = json.loads(approval_file.read_text(encoding="utf-8"))
    if approval_data != approval_manifest_payload(data):
        raise RuntimeError("APPROVAL_MANIFEST_MISMATCH: approval record or approved plan changed; stop this run")
    if [x.get("step") for x in data.get("steps", [])] != list(range(1, STEP_COUNT + 1)):
        raise ValueError("Invalid workflow: expected exactly steps 1..40")
    return data


def validate_cli_binding(args, data):
    if not getattr(args, "remote_device_id", None) or args.remote_device_id != data["remote_device_id"]:
        raise RuntimeError("REMOTE_DEVICE_MISMATCH: every remote action must use the originally selected deviceId")
    if not getattr(args, "remote_link_id", None) or args.remote_link_id != data["remote_link_id"]:
        raise RuntimeError("REMOTE_LINK_MISMATCH: every remote action must use the originally selected link_id")
    if not getattr(args, "video_root", None) or not same_path(args.video_root, data["video_root"]):
        raise RuntimeError("VIDEO_ROOT_MISMATCH: do not change or substitute the selected video folder")
    supplied_logo = canonical(Path(args.logo_root)) if getattr(args, "logo_root", None) else None
    stored_logo = canonical(Path(data["logo_root"])) if data.get("logo_root") else None
    if supplied_logo != stored_logo:
        raise RuntimeError("LOGO_ROOT_MISMATCH: do not change or substitute the selected logo folder")
    expected_fingerprint = getattr(args, "expected_server_fingerprint", None)
    if expected_fingerprint != data.get("server_fingerprint") or machine_fingerprint() != data.get("server_fingerprint"):
        raise RuntimeError("SERVER_FINGERPRINT_MISMATCH: current machine does not match the selected server")


def current_step(data):
    if data["preflight"]["status"] != "pass":
        return 0
    for item in data["steps"]:
        if item["status"] not in COMPLETE:
            return item["step"]
    return None


def get_record(data, step):
    if step == 0:
        return data["preflight"]
    if 1 <= step <= STEP_COUNT:
        return data["steps"][step - 1]
    raise ValueError("step must be 0 or 1..40")


def ensure_current(data, step):
    expected = current_step(data)
    if expected != step:
        raise ValueError(f"Out-of-order operation: current required step is {expected}, not {step}")
    blocker = data.get("blocker")
    if blocker and blocker.get("status") == "open":
        raise ValueError("An unresolved BLOCKED issue prevents all further work")
    return get_record(data, step)


def state_path(args):
    p = canonical(Path(args.state))
    if not p.is_file():
        raise FileNotFoundError(p)
    data = load_state(p)
    validate_cli_binding(args, data)
    return p, data


def mutate_state(path, fn):
    with locked(path):
        data = load_state(path)
        fn(data)
        data["updated_at"] = now()
        atomic_save(path, data)
        write_approval_manifest(path, data)
        return data


def cmd_init(a):
    video = canonical(Path(a.video_root))
    if not video.is_dir():
        raise NotADirectoryError(f"VIDEO_ROOT does not exist or is not a directory: {video}")
    logo = canonical(Path(a.logo_root)) if a.logo_root else None
    if logo and not logo.is_dir():
        raise NotADirectoryError(f"LOGO_ROOT does not exist or is not a directory: {logo}")
    roots_disjoint(video, logo)
    if not a.remote_device_id.strip() or not a.remote_link_id.strip():
        raise ValueError("Exact Remote Desktop Commander deviceId and link_id are required")
    actual_fingerprint = machine_fingerprint()
    if a.expected_server_fingerprint != actual_fingerprint:
        raise RuntimeError("SERVER_FINGERPRINT_MISMATCH: this command is not running on the bound server")
    if not a.run_id:
        raise ValueError("A new RUN_ID is required for every production run")
    path = within(Path(a.state), video, "State file")
    work = workspace_root(video)
    expected_state = work / "runs" / a.run_id / "state.json"
    if not same_path(path, expected_state):
        raise ValueError("State file must be this run's VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/state.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    binding_file = path.with_name("binding.json")
    with locked(path):
        if path.exists() or binding_file.exists():
            raise FileExistsError("Refusing to overwrite an existing run state or binding manifest; create a new run ID")
        run_id = a.run_id or uuid.uuid4().hex
        data = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "server_label": a.server_label,
            "remote_device_id": a.remote_device_id,
            "remote_link_id": a.remote_link_id,
            "server_fingerprint": actual_fingerprint,
            "bound_at": now(),
            "video_root": str(video),
            "video_root_identity": folder_identity(video),
            "workspace_root": str(work),
            "workspace_root_identity": folder_identity(work),
            "logo_root": str(logo) if logo else None,
            "logo_root_identity": folder_identity(logo) if logo else None,
            "started_at": now(),
            "updated_at": now(),
            "preflight": {"step": 0, "status": "pending", "installation_plan": {"configured": False, "items": [], "plan_snapshot": [], "plan_sha256": None, "approval": {"status": "pending"}}, "evidence": [], "history": []},
            "steps": [{"step": i, "status": "pending", "evidence": [], "history": []} for i in range(1, STEP_COUNT + 1)],
            "step_approvals": {},
            "qc_gates": {},
            "voice_selection": None,
            "blocker": None,
            "history": [],
        }
        atomic_save(binding_file, binding_snapshot(data))
        atomic_save(path, data)
        write_approval_manifest(path, data)
    print(json.dumps({"run_id": run_id, "state": str(path), "binding_manifest": str(binding_file), "server_label": a.server_label, "remote_device_id": a.remote_device_id, "video_root": str(video), "logo_root": str(logo) if logo else None, "status": "created_and_bound"}, ensure_ascii=False))


def cmd_verify_binding(a):
    path, data = state_path(a)
    print(json.dumps({"binding_ok": True, "run_id": data["run_id"], "server_label": data["server_label"], "remote_device_id": data["remote_device_id"], "video_root": data["video_root"], "logo_root": data["logo_root"], "server_fingerprint": data["server_fingerprint"]}, ensure_ascii=False))


def cmd_set_plan(a):
    path, data0 = state_path(a)
    video = Path(data0["video_root"])
    plan_path = within(Path(a.plan_file), workspace_root(video), "Installation plan")
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    items = raw.get("items") if isinstance(raw, dict) else None
    normalized = normalize_plan_items(items, video)
    snapshot = installation_plan_snapshot(normalized)
    plan_digest = canonical_hash(snapshot)
    ev = evidence_records([plan_path], video)
    def change(data):
        rec = ensure_current(data, 0)
        if rec["status"] != "running":
            raise ValueError("Preflight must be RUNNING before recording the plan")
        old_items = rec.get("installation_plan", {}).get("items", [])
        if any(x.get("status") in {"running", "blocked"} for x in old_items):
            raise ValueError("Cannot amend a plan with an active or blocked install; repair/finish it first")
        if (data.get("blocker") or {}).get("status") == "open":
            raise ValueError("Resolve BLOCKED before amending plan")
        old_snapshot = installation_plan_snapshot(old_items)
        for idx, old_item in enumerate(old_items):
            if old_item.get("status") == "pass":
                if idx >= len(normalized) or installation_plan_snapshot([normalized[idx]]) != installation_plan_snapshot([old_item]):
                    raise ValueError("Previously completed installation items are immutable; retain them in the same order")
                normalized[idx]["status"] = "pass"
                normalized[idx]["history"] = old_item.get("history", [])
                normalized[idx]["evidence"] = old_item.get("evidence", [])
                normalized[idx]["note"] = old_item.get("note")
        rec.setdefault("plan_history", []).append({"at": now(), "prior_hash": rec.get("installation_plan", {}).get("plan_sha256"), "approval_revoked": True})
        rec["installation_plan"] = {
            "configured": True,
            "items": normalized,
            "plan_snapshot": snapshot,
            "plan_sha256": plan_digest,
            "plan_file": str(plan_path),
            "plan_file_sha256": sha256(plan_path),
            "approval": {"status": "pending"},
            "evidence": ev,
            "configured_at": now(),
        }
        rec["plan_displayed"] = True
    saved = mutate_state(path, change)
    print(json.dumps({"installation_items": len(normalized), "plan_displayed": True, "approval_required": True, "plan_sha256": plan_digest, "items": snapshot, "next_action": next_action(saved)}, ensure_ascii=False))


def cmd_approve_install_plan(a):
    path, data0 = state_path(a)
    if not a.user_approved:
        raise ValueError("Explicit user approval is required for the complete installation plan")
    def change(data):
        rec = ensure_current(data, 0)
        if rec["status"] != "running":
            raise ValueError("Preflight must be RUNNING before approving installation")
        plan = rec.get("installation_plan", {})
        if not plan.get("configured"):
            raise ValueError("Installation plan must be displayed before approval")
        verify_plan_file(data)
        snapshot = plan.get("plan_snapshot", [])
        actual_hash = canonical_hash(snapshot)
        if actual_hash != plan.get("plan_sha256") or a.plan_sha256 != actual_hash:
            raise ValueError("INSTALL_PLAN_HASH_MISMATCH: the displayed installation plan changed; review and approve the new plan")
        if any(x.get("status") not in {"pending", "pass"} for x in plan.get("items", [])):
            raise ValueError("Installation approval cannot occur while an item is running or blocked")
        if any(x.get("status") == "pass" and not x.get("evidence") for x in plan.get("items", [])):
            raise ValueError("Previously completed items require verifiable evidence before re-approval")
        plan["approval"] = {
            "status": "approved",
            "approval_id": uuid.uuid4().hex,
            "approved_by": "user",
            "approved_at": now(),
            "plan_sha256": actual_hash,
        }
    saved = mutate_state(path, change)
    print(json.dumps({"status": "approved", "plan_sha256": saved["preflight"]["installation_plan"]["plan_sha256"], "next_action": next_action(saved)}, ensure_ascii=False))


def cmd_install_mark(a):
    path, data0 = state_path(a)
    ev = evidence_records(a.evidence or [], Path(data0["video_root"])) if a.evidence else []
    def change(data):
        if data["preflight"]["status"] != "running":
            raise ValueError("Preflight must be RUNNING")
        if data.get("blocker") and data["blocker"]["status"] == "open":
            raise ValueError("Resolve BLOCKED before installing another item")
        items = data["preflight"].get("installation_plan", {}).get("items", [])
        plan = data["preflight"].get("installation_plan", {})
        if not plan.get("configured"):
            raise ValueError("Record the ordered plan first")
        if plan.get("approval", {}).get("status") != "approved":
            raise ValueError("INSTALL_PLAN_NOT_APPROVED: user must approve the complete displayed installation list before installing")
        verify_plan_file(data)
        if plan.get("approval", {}).get("plan_sha256") != plan.get("plan_sha256"):
            raise ValueError("INSTALL_PLAN_HASH_MISMATCH: installation plan approval is stale")
        current = next((x for x in items if x["status"] not in COMPLETE), None)
        if current is None or current["id"] != a.item_id:
            raise ValueError(f"Out-of-order install; next item is {current['id'] if current else 'none'}")
        if a.status == "running":
            if current["status"] != "pending":
                raise ValueError("Install item is already RUNNING or blocked; do not launch a duplicate install process")
        elif a.status == "pass":
            if current["status"] != "running" or not ev:
                raise ValueError("PASS requires RUNNING and evidence")
            if current.get("already_present"):
                report_path = getattr(a, "verification_report", None)
                if not report_path:
                    raise ValueError("ALREADY_PRESENT_VERIFICATION_REQUIRED: provide a real version/smoke-test report")
                report = within(Path(report_path), workspace_root(Path(data["video_root"])), "Verification report")
                obj = json.loads(report.read_text(encoding="utf-8"))
                if (obj.get("item_id") != a.item_id or obj.get("status") != "pass"
                    or not str(obj.get("observed_version", "")).strip()
                    or not isinstance(obj.get("checks"), list)
                    or not obj["checks"] or not all(x.get("passed") is True and x.get("method") for x in obj["checks"])):
                    raise ValueError("ALREADY_PRESENT_VERIFICATION_INVALID")
                current["verification_report"] = evidence_records([report], Path(data["video_root"]))
        else:
            raise ValueError("Use BLOCKED for failures; PARTIAL cannot unlock the next item")
        current["history"].append({"at": now(), "status": a.status, "note": a.note})
        current["status"], current["note"] = a.status, a.note
        if ev:
            current["evidence"] = ev
        blocker = data.get("blocker")
        if a.status == "pass" and blocker and blocker.get("status") == "resolved_pending_retest" and blocker.get("install_item_id") == a.item_id:
            blocker["status"] = "closed"
            blocker["closed_at"] = now()
    saved = mutate_state(path, change)
    plan = saved["preflight"].get("installation_plan", {})
    next_item = next((x for x in plan.get("items", []) if x["status"] not in COMPLETE), None)
    print(json.dumps({"item_id": a.item_id, "status": a.status, "next_item": next_item.get("id") if next_item else None, "next_action": next_action(saved)}, ensure_ascii=False))


def cmd_approve_step(a):
    path, data0 = state_path(a)
    if not a.user_approved:
        raise ValueError("Explicit user approval is required before executing this workflow step")
    def change(data):
        if data["preflight"]["status"] != "pass":
            raise ValueError("Preflight must PASS before approving production steps")
        verify_plan_file(data)
        rec = ensure_current(data, a.step)
        if a.step == 0:
            raise ValueError("Use approve-install-plan for preflight installation")
        if a.step >= 21 and not data.get("voice_selection"):
            raise ValueError("User must select a voice before approving step 21")
        if rec.get("status") not in {"pending", "partial", "stale"}:
            raise ValueError(f"Step {a.step:02d} is not waiting for approval")
        if a.step > 1 and data["steps"][a.step - 2]["status"] not in COMPLETE:
            raise ValueError("The immediately preceding step must PASS before this step can be approved")
        digest = step_approval_hash(data, a.step)
        data.setdefault("step_approvals", {})[str(a.step)] = {
            "step": a.step,
            "status": "approved",
            "approval_id": uuid.uuid4().hex,
            "approved_by": "user",
            "approved_at": now(),
            "approval_hash": digest,
        }
    saved = mutate_state(path, change)
    print(json.dumps({"status": "approved", "step": a.step, "next_action": next_action(saved)}, ensure_ascii=False))


def cmd_mark(a):
    path, data0 = state_path(a)
    ev = evidence_records(a.evidence or [], Path(data0["video_root"])) if a.evidence else []
    def change(data):
        rec = ensure_current(data, a.step)
        if a.step == 0 and a.status == "skipped":
            raise ValueError("Preflight cannot be skipped")
        if a.step >= 21 and not data.get("voice_selection"):
            raise ValueError("User must select a voice before step 21")
        if a.status == "running":
            if rec["status"] not in {"pending", "partial", "stale"}:
                raise ValueError(f"Cannot launch this step from {rec['status']}; a RUNNING step must not be launched twice")
            if a.step > 0:
                approval = data.get("step_approvals", {}).get(str(a.step), {})
                if approval.get("status") != "approved":
                    raise ValueError(f"STEP_{a.step:02d}_NOT_APPROVED: display the approval control and wait for explicit user approval")
                if approval.get("approval_hash") != step_approval_hash(data, a.step):
                    raise ValueError("STEP_APPROVAL_STALE: previous-step evidence or run binding changed; request approval again")
                approval["status"] = "consumed"
                approval["consumed_at"] = now()
        elif a.status == "pass":
            if rec["status"] != "running" or not ev:
                raise ValueError("PASS requires RUNNING and evidence")
            if a.step > 0 and data.get("step_approvals", {}).get(str(a.step), {}).get("status") != "consumed":
                raise ValueError("STEP_APPROVAL_REQUIRED: a step must have a consumed user approval before PASS")
            if a.step == 0:
                plan = rec.get("installation_plan", {})
                if not plan.get("configured"):
                    raise ValueError("Preflight plan is not configured")
                if plan.get("approval", {}).get("status") != "approved":
                    raise ValueError("INSTALL_PLAN_NOT_APPROVED: user approval is required before preflight can PASS")
                verify_plan_file(data)
                if plan.get("approval", {}).get("plan_sha256") != plan.get("plan_sha256"):
                    raise ValueError("INSTALL_PLAN_HASH_MISMATCH: approval no longer matches the installation plan")
                if any(x["status"] != "pass" for x in plan.get("items", [])):
                    raise ValueError("Every installation item must PASS before preflight PASS")
            if a.step > 0:
                ensure_qc_passed(data, a.step)
        elif a.status == "partial":
            if rec["status"] != "running" or not ev:
                raise ValueError("PARTIAL requires RUNNING and evidence")
        elif a.status == "skipped":
            if a.step in QC_GATES:
                raise ValueError("QC_STEP_CANNOT_SKIP")
            approval = data.get("step_approvals", {}).get(str(a.step), {})
            if (not a.approved_skip or not a.note.strip() or not ev
                or approval.get("status") != "approved"
                or approval.get("approval_hash") != step_approval_hash(data, a.step)):
                raise ValueError("SKIPPED requires this step's explicit approval, reason and evidence")
            approval["status"] = "consumed"
            approval["consumed_at"] = now()
        else:
            raise ValueError("Unsupported status")
        rec["history"].append({"at": now(), "status": a.status, "note": a.note})
        rec["status"], rec["note"] = a.status, a.note
        if ev:
            rec["evidence"] = ev
        blocker = data.get("blocker")
        if a.status == "pass" and blocker and blocker.get("status") == "resolved_pending_retest" and blocker.get("step") == a.step:
            blocker["status"] = "closed"
            blocker["closed_at"] = now()
    saved = mutate_state(path, change)
    print(json.dumps({"step": a.step, "status": get_record(saved, a.step)["status"], "next_step": current_step(saved), "next_action": next_action(saved)}, ensure_ascii=False))


def cmd_block(a):
    path, data0 = state_path(a)
    ev = evidence_records(a.evidence, Path(data0["video_root"]))
    def change(data):
        rec = ensure_current(data, a.step)
        if rec["status"] not in {"running", "partial"}:
            raise ValueError("BLOCK_REQUIRES_RUNNING_STEP: cannot block or repair an unapproved step")
        if data.get("blocker") and data["blocker"]["status"] == "open":
            raise ValueError("An open blocker already exists")
        item_id = a.install_item_id
        if item_id:
            if a.step != 0:
                raise ValueError("Install blocker must use preflight step 0")
            items = data["preflight"]["installation_plan"]["items"]
            current = next((x for x in items if x["status"] not in COMPLETE), None)
            if not current or current["id"] != item_id or current["status"] != "running":
                raise ValueError("Only the currently RUNNING install item can be blocked")
            current["status"] = "blocked"
        rec["status"] = "blocked"
        data["blocker"] = {"blocker_id": uuid.uuid4().hex, "step": a.step, "install_item_id": item_id,
            "status": "open", "error_code": a.error_code, "symptom": a.symptom, "diagnosis": a.diagnosis,
            "proposal": a.proposal, "alternatives": a.alternatives, "risk": a.risk,
            "approval_required": bool(a.approval_required or a.risk in {"medium", "high", "critical"}), "repair_approved": False, "verification": a.verification,
            "evidence": ev, "repair_attempts": [], "created_at": now()}
    saved = mutate_state(path, change)
    print(json.dumps({"status": "blocked", "step": a.step, "blocker_id": saved["blocker"]["blocker_id"]}, ensure_ascii=False))


def cmd_repair(a):
    path, data0 = state_path(a)
    ev = evidence_records(a.evidence, Path(data0["video_root"]))
    def change(data):
        b = data.get("blocker")
        if not b or b["status"] != "open" or b["step"] != a.step:
            raise ValueError("No matching open blocker")
        if b.get("approval_required") and not b.get("repair_approved"):
            raise ValueError("REPAIR_APPROVAL_REQUIRED: approve the proposed risky repair before recording it")
        b["repair_attempts"].append({"at": now(), "action": a.action, "note": a.note, "evidence": ev})
    mutate_state(path, change)
    print(json.dumps({"status": "still_blocked", "step": a.step}, ensure_ascii=False))


def cmd_resolve(a):
    path, data0 = state_path(a)
    ev = evidence_records([a.verification_evidence], Path(data0["video_root"]))
    def change(data):
        b = data.get("blocker")
        if not b or b["status"] != "open" or b["step"] != a.step:
            raise ValueError("No matching open blocker")
        if b["approval_required"] and not b.get("repair_approved"):
            raise ValueError("User approval is required before resolving this blocker")
        if a.step > 0 and data.get("step_approvals", {}).get(str(a.step), {}).get("status") != "consumed":
            raise ValueError("BLOCKED_STEP_NOT_APPROVED: repair cannot launch a previously unapproved step")
        if b.get("install_item_id"):
            verify_plan_file(data)
            plan = data["preflight"]["installation_plan"]
            if plan.get("approval", {}).get("status") != "approved":
                raise ValueError("INSTALL_PLAN_NOT_APPROVED")
        if not b["repair_attempts"]:
            raise ValueError("Record a repair attempt before resolving")
        if b.get("install_item_id"):
            item = next(x for x in data["preflight"]["installation_plan"]["items"] if x["id"] == b["install_item_id"])
            item["status"] = "running"
        get_record(data, a.step)["status"] = "running"
        b["status"] = "resolved_pending_retest"
        b["verification_evidence"] = ev
        b["resolved_at"] = now()
        b["note"] = a.note
    mutate_state(path, change)
    print(json.dumps({"status": "running_retest_required", "step": a.step}, ensure_ascii=False))


def cmd_approve_repair(a):
    path, _data = state_path(a)
    if not a.user_approved:
        raise ValueError("User must approve the specific repair")
    def change(data):
        b = data.get("blocker") or {}
        if b.get("status") != "open" or b.get("step") != a.step or b.get("blocker_id") != a.blocker_id:
            raise ValueError("Wrong or stale blocker ID")
        b["repair_approved"] = True
        b["repair_approved_at"] = now()
    mutate_state(path, change)
    print(json.dumps({"status":"repair_approved", "step":a.step}, ensure_ascii=False))


def cmd_qc_mark(a):
    path, state = state_path(a)
    required_step = next((k for k, gate in QC_GATES.items() if gate == a.gate), None)
    if required_step is None or current_step(state) != required_step:
        raise ValueError("QC_GATE_NOT_CURRENT")
    report = within(Path(a.report), workspace_root(Path(state["video_root"])), "QC report")
    payload = json.loads(report.read_text(encoding="utf-8"))
    checks = payload.get("checks")
    paths = payload.get("evidence_paths")
    if (payload.get("status") != "pass" or payload.get("run_id") != state["run_id"]
        or payload.get("gate") != a.gate or payload.get("step") != required_step
        or not isinstance(checks, list) or len(checks) < 2
        or not all(x.get("passed") is True and str(x.get("method", "")).strip() and str(x.get("id", "")).strip() for x in checks)
        or not isinstance(paths, list) or not paths):
        raise ValueError("QC_REPORT_INVALID: require gate/step/run, two actual checks and evidence files")
    actual = evidence_records([Path(x) for x in paths], Path(state["video_root"]))
    # QC3/QC4 cannot be self-certified: recompute from real script and PCM master.
    editorial_audit = audit_review_script(state, payload.get("editorial_audit")) if a.gate == 3 else None
    tts_duration_audit = audit_tts_master(state, payload.get("tts_duration_audit")) if a.gate == 4 else None
    if a.gate in {5, 8}:
        verify_tts_master(state)  # Refuse timelines/final delivery based on changed narration.
    def change(data):
        rec = ensure_current(data, required_step)
        if rec["status"] != "running":
            raise ValueError("QC_REQUIRES_RUNNING_STEP")
        record = {
            "gate": a.gate, "step": required_step, "status": "pass",
            "report": str(report), "report_sha256": sha256(report),
            "evidence": actual, "checked_at": now(),
        }
        if editorial_audit is not None:
            record["editorial_audit"] = editorial_audit
        if tts_duration_audit is not None:
            record["tts_duration_audit"] = tts_duration_audit
        data.setdefault("qc_gates", {})[str(a.gate)] = record
    mutate_state(path, change)
    print(json.dumps({"status":"pass", "gate":a.gate}, ensure_ascii=False))



def cmd_reopen_editorial(a):
    """User-approved rewind for short/incorrect reviews; no silent step bypass.

    Keep one run, preserve hashes and copies of earlier editorial evidence, and
    force fresh approvals for every reopened step. This is NOT auto-resume.
    """
    path, current = state_path(a)
    if not a.user_approved or len(a.reason.strip()) < 18:
        raise ValueError("EDITORIAL_REOPEN_APPROVAL_REQUIRED: explicit user consent and a detailed reason are required")
    if a.from_step not in {16, 17}:
        raise ValueError("EDITORIAL_REOPEN_START_INVALID: choose step 16 (dossier) or 17 (script)")
    if current_step(current) is not None and current_step(current) <= a.from_step:
        raise ValueError("EDITORIAL_REOPEN_NOT_NEEDED: current step has not advanced past requested start")
    if current["preflight"]["status"] != "pass":
        raise ValueError("EDITORIAL_REOPEN_PREFLIGHT_REQUIRED")
    ev = evidence_records([a.evidence], Path(current["video_root"]))
    def rewind(data):
        prior = current_step(data)
        saved_editorial = data.get("qc_gates", {}).get("3", {}).get("editorial_audit", {})
        saved_audio = data.get("qc_gates", {}).get("4", {}).get("tts_duration_audit", {})
        revision_id = uuid.uuid4().hex
        revisions_dir = workspace_root(Path(data["video_root"])) / "runs" / data["run_id"] / "revisions" / revision_id
        # A user may have found new facts; archive earlier source evidence before it changes.
        archived = {}
        for key, item in saved_editorial.get("files", {}).items():
            old = within(Path(item["path"]), workspace_root(Path(data["video_root"])), "Prior editorial file")
            if old.is_file() and sha256(old) == item["sha256"]:
                if revisions_dir.is_symlink() or getattr(revisions_dir, "is_junction", lambda: False)():
                    raise RuntimeError("EDITORIAL_ARCHIVE_LINK_FORBIDDEN")
                revisions_dir.mkdir(parents=True, exist_ok=True)
                dest = within(revisions_dir / (key + old.suffix), workspace_root(Path(data["video_root"])), "Editorial archive")
                shutil.copyfile(old, dest)
                archived[key] = {"path": str(dest), "sha256": sha256(dest)}
        data.setdefault("editorial_revision_history", []).append({
            "revision_id": revision_id, "at": now(), "from_step": a.from_step,
            "previous_next_step": prior, "reason": a.reason, "evidence": ev,
            "previous_editorial": saved_editorial,
            "previous_tts": saved_audio, "archive": archived,
            "prior_blocker": data.get("blocker"),
        })
        for rec in data["steps"][a.from_step-1:]:
            rec.setdefault("history", []).append({"at": now(), "status": "reopened", "reason": a.reason,
                "revision_id": revision_id})
            rec["status"] = "pending"
            rec["evidence"] = []
            rec.pop("note", None)
        for i in range(a.from_step, STEP_COUNT+1):
            data.get("step_approvals", {}).pop(str(i), None)
        earliest_qc = 2 if a.from_step <= 16 else 3
        for gate in range(earliest_qc, 9):
            data.get("qc_gates", {}).pop(str(gate), None)
        data["voice_selection"] = None
        data["blocker"] = None
    saved = mutate_state(path, rewind)
    print(json.dumps({"status": "editorial_reopened", "from_step": a.from_step,
                      "next_step": current_step(saved), "next_action": next_action(saved),
                      "reapprovals_required": True}, ensure_ascii=False))


def cmd_select_voice(a):
    path, data0 = state_path(a)
    ev = evidence_records([a.evidence], Path(data0["video_root"]))
    def change(data):
        if data["preflight"]["status"] != "pass":
            raise ValueError("Preflight must PASS before voice selection")
        if data.get("voice_selection"):
            raise ValueError("Voice already selected for this run")
        if not a.user_confirmed:
            raise ValueError("Explicit user voice confirmation required")
        if any(x["status"] not in COMPLETE for x in data["steps"][:20]):
            raise ValueError("Steps 01–20 must be complete before voice selection")
        data["voice_selection"] = {"voice": a.voice, "engine": a.engine, "note": a.note, "evidence": ev, "selected_at": now()}
    saved = mutate_state(path, change)
    print(json.dumps({"voice": a.voice, "next_step": 21, "next_action": next_action(saved)}, ensure_ascii=False))


def cmd_status(a):
    path, data = state_path(a)
    step = current_step(data)
    blocker = data.get("blocker") or {}
    plan = data["preflight"].get("installation_plan", {})
    approval = data.get("step_approvals", {}).get(str(step), {}) if step and step > 0 else {}
    print(json.dumps({
        "run_id": data["run_id"],
        "server_label": data["server_label"],
        "remote_device_id": data["remote_device_id"],
        "server_fingerprint": data["server_fingerprint"],
        "video_root": data["video_root"],
        "workspace_root": data["workspace_root"],
        "logo_root": data["logo_root"],
        "preflight": data["preflight"]["status"],
        "installation_plan": {
            "configured": plan.get("configured", False),
            "item_count": len(plan.get("items", [])),
            "plan_sha256": plan.get("plan_sha256"),
            "plan_file_sha256": plan.get("plan_file_sha256"),
            "approval": plan.get("approval", {"status": "pending"}),
            "items": [{"id": x["id"], "name": x["name"], "status": x["status"], "target_path": x.get("target_path")} for x in plan.get("items", [])],
        },
        "next_step": step,
        "step_approval": approval,
        "editorial_duration": data.get("qc_gates", {}).get("3", {}).get("editorial_audit"),
        "tts_duration": data.get("qc_gates", {}).get("4", {}).get("tts_duration_audit"),
        "next_action": next_action(data),
        "blocker": data.get("blocker"),
    }, ensure_ascii=False, indent=2))


def step_type(value):
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("step must be an integer") from exc
    if n < 0 or n > STEP_COUNT:
        raise argparse.ArgumentTypeError("step must be 0 or 1..40")
    return n


def evidence_args(p, required=False):
    p.add_argument("--evidence", action="append", type=Path, default=[], required=required)


def binding_args(p):
    p.add_argument("--remote-device-id", required=True, help="Exact selected Remote Desktop Commander deviceId")
    p.add_argument("--remote-link-id", required=True, help="Exact selected Remote Desktop Commander link_id")
    p.add_argument("--expected-server-fingerprint", required=True, help="Fingerprint from this run's immutable server_binding.json")
    p.add_argument("--video-root", required=True, type=Path)
    p.add_argument("--logo-root", type=Path, default=None, help="Omit only when the user explicitly selected no logo")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("init")
    q.add_argument("--state", required=True, type=Path)
    q.add_argument("--server-label", required=True)
    binding_args(q)
    q.add_argument("--run-id", required=True)
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("verify-binding")
    q.add_argument("--state", required=True, type=Path); binding_args(q); q.set_defaults(func=cmd_verify_binding)

    q = sub.add_parser("set-install-plan")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--plan-file", required=True, type=Path); q.set_defaults(func=cmd_set_plan)

    q = sub.add_parser("approve-install-plan")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--plan-sha256", required=True); q.add_argument("--user-approved", action="store_true")
    q.set_defaults(func=cmd_approve_install_plan)

    q = sub.add_parser("install-mark")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--item-id", required=True); q.add_argument("--status", required=True, choices=["running", "pass"])
    q.add_argument("--note", required=True); q.add_argument("--verification-report", type=Path); evidence_args(q); q.set_defaults(func=cmd_install_mark)

    q = sub.add_parser("approve-step")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--step", required=True, type=step_type); q.add_argument("--user-approved", action="store_true")
    q.set_defaults(func=cmd_approve_step)

    q = sub.add_parser("mark")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--step", required=True, type=step_type); q.add_argument("--status", required=True, choices=["running", "pass", "partial", "skipped"])
    q.add_argument("--note", required=True); q.add_argument("--approved-skip", action="store_true")
    evidence_args(q); q.set_defaults(func=cmd_mark)

    q = sub.add_parser("block")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--step", required=True, type=step_type); q.add_argument("--install-item-id"); q.add_argument("--error-code", default="UNKNOWN")
    q.add_argument("--symptom", required=True); q.add_argument("--diagnosis", required=True); q.add_argument("--proposal", required=True)
    q.add_argument("--alternatives", action="append", default=[]); q.add_argument("--risk", choices=["low", "medium", "high", "critical"], required=True)
    q.add_argument("--verification", required=True); q.add_argument("--approval-required", action="store_true")
    evidence_args(q, required=True); q.set_defaults(func=cmd_block)

    q = sub.add_parser("repair")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--step", required=True, type=step_type); q.add_argument("--action", required=True); q.add_argument("--note", required=True)
    evidence_args(q, required=True); q.set_defaults(func=cmd_repair)

    q = sub.add_parser("resolve-blocker")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--step", required=True, type=step_type); q.add_argument("--verification-evidence", required=True, type=Path)
    q.add_argument("--note", required=True); q.add_argument("--user-approved", action="store_true"); q.set_defaults(func=cmd_resolve)

    q = sub.add_parser("approve-repair")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--step", required=True, type=step_type); q.add_argument("--blocker-id", required=True)
    q.add_argument("--user-approved", action="store_true"); q.set_defaults(func=cmd_approve_repair)

    q = sub.add_parser("qc-mark")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--gate", required=True, type=int); q.add_argument("--report", required=True, type=Path)
    q.set_defaults(func=cmd_qc_mark)

    q = sub.add_parser("reopen-editorial")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--from-step", required=True, type=int, choices=[16,17]); q.add_argument("--reason", required=True)
    q.add_argument("--evidence", required=True, type=Path); q.add_argument("--user-approved", action="store_true")
    q.set_defaults(func=cmd_reopen_editorial)

    q = sub.add_parser("select-voice")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--voice", required=True); q.add_argument("--engine", required=True); q.add_argument("--evidence", required=True, type=Path)
    q.add_argument("--note", required=True); q.add_argument("--user-confirmed", action="store_true"); q.set_defaults(func=cmd_select_voice)

    q = sub.add_parser("status")
    q.add_argument("--state", required=True, type=Path); binding_args(q); q.set_defaults(func=cmd_status)
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
