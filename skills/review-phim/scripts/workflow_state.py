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
import socket
import subprocess
import tempfile
import uuid
from pathlib import Path

SCHEMA_VERSION = 5
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
        raise ValueError(f"{label} must stay inside VIDEO_ROOT: {p}") from exc
    return p


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
        p = within(Path(raw), video_root, "Evidence file")
        if not p.is_file():
            raise FileNotFoundError(p)
        records.append({"path": str(p), "sha256": sha256(p), "size_bytes": p.stat().st_size})
    return records


def binding_snapshot(data: dict) -> dict:
    keys = (
        "schema_version", "run_id", "server_label", "remote_device_id", "remote_link_id",
        "server_fingerprint", "video_root", "video_root_identity", "logo_root",
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
    expected_state = video_root / ".review-phim" / "runs" / data["run_id"] / "state.json"
    if not same_path(path, expected_state):
        raise ValueError("State file must be this run's VIDEO_ROOT/.review-phim/runs/<RUN_ID>/state.json")
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
    expected_state = video / ".review-phim" / "runs" / a.run_id / "state.json"
    if not same_path(path, expected_state):
        raise ValueError("State file must be this run's VIDEO_ROOT/.review-phim/runs/<RUN_ID>/state.json")
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
            "logo_root": str(logo) if logo else None,
            "logo_root_identity": folder_identity(logo) if logo else None,
            "started_at": now(),
            "updated_at": now(),
            "preflight": {"step": 0, "status": "pending", "installation_plan": {"configured": False, "items": []}, "evidence": [], "history": []},
            "steps": [{"step": i, "status": "pending", "evidence": [], "history": []} for i in range(1, STEP_COUNT + 1)],
            "voice_selection": None,
            "blocker": None,
            "history": [],
        }
        atomic_save(binding_file, binding_snapshot(data))
        atomic_save(path, data)
    print(json.dumps({"run_id": run_id, "state": str(path), "binding_manifest": str(binding_file), "server_label": a.server_label, "remote_device_id": a.remote_device_id, "video_root": str(video), "logo_root": str(logo) if logo else None, "status": "created_and_bound"}, ensure_ascii=False))


def cmd_verify_binding(a):
    path, data = state_path(a)
    print(json.dumps({"binding_ok": True, "run_id": data["run_id"], "server_label": data["server_label"], "remote_device_id": data["remote_device_id"], "video_root": data["video_root"], "logo_root": data["logo_root"], "server_fingerprint": data["server_fingerprint"]}, ensure_ascii=False))


def cmd_set_plan(a):
    path, data0 = state_path(a)
    video = Path(data0["video_root"])
    plan_path = within(Path(a.plan_file), video, "Installation plan")
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("Plan must contain an ordered items array")
    normalized, seen = [], set()
    for i, item in enumerate(items, 1):
        item_id, name = str(item.get("id", "")).strip(), str(item.get("name", "")).strip()
        if not item_id or not name or item_id in seen:
            raise ValueError(f"Invalid or duplicate installation item at position {i}")
        seen.add(item_id)
        target = item.get("target_path")
        if target:
            within(Path(target), video, f"Installation target {item_id}")
        normalized.append({"order": i, "id": item_id, "name": name, "target_path": target, "status": "pending", "evidence": [], "history": []})
    ev = evidence_records([plan_path], video)
    def change(data):
        rec = ensure_current(data, 0)
        if rec["status"] != "running":
            raise ValueError("Preflight must be RUNNING before recording the plan")
        rec["installation_plan"] = {"configured": True, "items": normalized, "evidence": ev, "configured_at": now()}
        rec["plan_displayed"] = True
    saved = mutate_state(path, change)
    print(json.dumps({"installation_items": len(normalized), "plan_displayed": True, "next": normalized[0]["id"] if normalized else "smoke_tests"}, ensure_ascii=False))


def cmd_install_mark(a):
    path, data0 = state_path(a)
    ev = evidence_records(a.evidence or [], Path(data0["video_root"])) if a.evidence else []
    def change(data):
        if data["preflight"]["status"] != "running":
            raise ValueError("Preflight must be RUNNING")
        if data.get("blocker") and data["blocker"]["status"] == "open":
            raise ValueError("Resolve BLOCKED before installing another item")
        items = data["preflight"].get("installation_plan", {}).get("items", [])
        if not data["preflight"].get("installation_plan", {}).get("configured"):
            raise ValueError("Record the ordered plan first")
        current = next((x for x in items if x["status"] not in COMPLETE), None)
        if current is None or current["id"] != a.item_id:
            raise ValueError(f"Out-of-order install; next item is {current['id'] if current else 'none'}")
        if a.status == "running":
            if current["status"] not in {"pending", "running"}:
                raise ValueError("Only pending/running item can enter RUNNING")
        elif a.status == "pass":
            if current["status"] != "running" or not ev:
                raise ValueError("PASS requires RUNNING and evidence")
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
    mutate_state(path, change)
    print(json.dumps({"item_id": a.item_id, "status": a.status}, ensure_ascii=False))


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
            if rec["status"] not in {"pending", "running", "partial", "stale"}:
                raise ValueError(f"Cannot enter RUNNING from {rec['status']}")
        elif a.status == "pass":
            if rec["status"] != "running" or not ev:
                raise ValueError("PASS requires RUNNING and evidence")
            if a.step == 0:
                plan = rec.get("installation_plan", {})
                if not plan.get("configured"):
                    raise ValueError("Preflight plan is not configured")
                if any(x["status"] != "pass" for x in plan.get("items", [])):
                    raise ValueError("Every installation item must PASS before preflight PASS")
        elif a.status == "partial":
            if rec["status"] != "running" or not ev:
                raise ValueError("PARTIAL requires RUNNING and evidence")
        elif a.status == "skipped":
            if not a.approved_skip or not a.note.strip() or not ev:
                raise ValueError("SKIPPED requires explicit approval, reason and evidence")
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
    print(json.dumps({"step": a.step, "status": get_record(saved, a.step)["status"], "next_step": current_step(saved)}, ensure_ascii=False))


def cmd_block(a):
    path, data0 = state_path(a)
    ev = evidence_records(a.evidence, Path(data0["video_root"]))
    def change(data):
        rec = ensure_current(data, a.step)
        if rec["status"] == "pass":
            raise ValueError("Invalidate current step before blocking a passed step")
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
            "approval_required": a.approval_required, "verification": a.verification,
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
        if b["approval_required"] and not a.user_approved:
            raise ValueError("User approval is required before resolving this blocker")
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
    mutate_state(path, change)
    print(json.dumps({"voice": a.voice, "next_step": 21}, ensure_ascii=False))


def cmd_status(a):
    path, data = state_path(a)
    step = current_step(data)
    blocker = data.get("blocker") or {}
    action = "repair_blocked_step" if blocker.get("status") == "open" else ("complete_preflight" if step == 0 else ("run_complete" if step is None else ("select_voice" if step == 21 and not data.get("voice_selection") else f"execute_step_{step:02d}")))
    print(json.dumps({"run_id": data["run_id"], "server_label": data["server_label"], "remote_device_id": data["remote_device_id"], "server_fingerprint": data["server_fingerprint"], "video_root": data["video_root"], "logo_root": data["logo_root"], "preflight": data["preflight"]["status"], "next_step": step, "next_action": action, "blocker": data.get("blocker")}, ensure_ascii=False, indent=2))


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

    q = sub.add_parser("install-mark")
    q.add_argument("--state", required=True, type=Path); binding_args(q)
    q.add_argument("--item-id", required=True); q.add_argument("--status", required=True, choices=["running", "pass"])
    q.add_argument("--note", required=True); evidence_args(q); q.set_defaults(func=cmd_install_mark)

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
