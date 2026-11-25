#!/usr/bin/env python3
"""Fail-closed Windows Sandbox executor for Review-Phim.

The Windows Sandbox VM is the OS isolation boundary, NOT path validation,
process flags, a normal Job Object, or a restricted Python environment.
Only three host folders are mapped: VIDEO_ROOT read-only; LOGO_ROOT read-only;
VIDEO_ROOT/WORKSPACE read-write. Guest files outside mappings are disposable.
No host system settings are changed. A real guest acceptance probe is required.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import ntpath
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

VERSION = "1.3.1"
GUEST_WORK = r"C:\ReviewWorkspace"
GUEST_SOURCE = r"C:\ReviewSourceReadOnly"
GUEST_LOGO = r"C:\ReviewLogoReadOnly"
GUEST_PROBE = "windows_sandbox_guest.ps1"
MAX_RESULT_BYTES = 512_000

class SandboxBlocked(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def canonical_win(value: str) -> str:
    if not value or not ntpath.isabs(value) or value.startswith("\\\\"):
        raise SandboxBlocked("INVALID_HOST_PATH", "Require a local absolute Windows drive path")
    return ntpath.normcase(ntpath.normpath(value))


def under(candidate: str, root: str) -> bool:
    c, r = canonical_win(candidate), canonical_win(root)
    try:
        return ntpath.commonpath([c, r]) == r
    except ValueError:
        return False


def map_path(raw: str, video_root: str, logo_root: str | None, workspace: str) -> str:
    """Translate an *entire* host path into the guest mapping; reject others."""
    pairs = [(workspace, GUEST_WORK)]
    if logo_root:
        pairs.append((logo_root, GUEST_LOGO))
    pairs.append((video_root, GUEST_SOURCE))
    for host, guest in pairs:
        if under(raw, host):
            rel = ntpath.relpath(canonical_win(raw), canonical_win(host))
            return guest if rel == "." else ntpath.join(guest, rel)
    raise SandboxBlocked("HOST_PATH_OUTSIDE_BINDING", f"Host path is outside locked roots: {raw}")


def remap_token(token: str, video_root: str, logo_root: str | None, workspace: str) -> str:
    """No shell interpolation. Supports absolute path args and --flag=PATH args."""
    if re.match(r"^[A-Za-z]:[\\/]", token):
        return map_path(token, video_root, logo_root, workspace)
    key, sep, value = token.partition("=")
    if sep and re.match(r"^[A-Za-z]:[\\/]", value):
        return key + sep + map_path(value, video_root, logo_root, workspace)
    # Reject embedded host drive paths which cannot be translated safely.
    if re.search(r"(?i)[a-z]:[\\/]", token):
        raise SandboxBlocked("EMBEDDED_HOST_PATH", f"Cannot safely translate token: {token[:100]}")
    return token


def quote_windows_arguments(arguments: list[str]) -> str:
    return subprocess.list2cmdline(arguments)


def classify_command(command: list[str], video_root: str, logo_root: str | None, workspace: str) -> tuple[str, str]:
    if not command:
        raise SandboxBlocked("EMPTY_COMMAND", "Empty command")
    exe = command[0]
    # Host exe paths inside VIDEO_ROOT but outside WORKSPACE are disallowed;
    # the guest must use a portable runtime packaged under WORKSPACE.
    if re.match(r"^[A-Za-z]:[\\/]", exe):
        if not under(exe, workspace):
            raise SandboxBlocked("NONPORTABLE_EXECUTABLE", "Executable must reside inside WORKSPACE")
        guest_exe = map_path(exe, video_root, logo_root, workspace)
    else:
        if exe.lower() not in ("powershell.exe", "cmd.exe"):
            raise SandboxBlocked("EXECUTABLE_NOT_ALLOWLISTED", "Use a portable exe in WORKSPACE or the guest built-in PowerShell/cmd")
        guest_exe = exe
    guest_args = [remap_token(x, video_root, logo_root, workspace) for x in command[1:]]
    return guest_exe, quote_windows_arguments(guest_args)


def windows_edition() -> dict[str, str]:
    if platform.system() != "Windows":
        raise SandboxBlocked("NOT_WINDOWS_HOST", "This executor only works on Windows")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            edition = str(winreg.QueryValueEx(key, "EditionID")[0])
            build = str(winreg.QueryValueEx(key, "CurrentBuild")[0])
            product = str(winreg.QueryValueEx(key, "ProductName")[0])
    except Exception as exc:
        raise SandboxBlocked("EDITION_QUERY_FAILED", str(exc)) from exc
    # Registry ProductName can still say "Windows 10" on upgraded Windows 11.
    # The NT build is authoritative for the Windows 11 product-family label.
    display_product = product
    if build.isdecimal() and int(build) >= 22000 and display_product.startswith("Windows 10"):
        display_product = "Windows 11" + display_product[len("Windows 10"):]
    return {"edition": edition, "build": build, "product": display_product,
            "registry_product_name": product}


def find_windows_sandbox_exe() -> str:
    info = windows_edition()
    if "home" in info["edition"].lower() or "core" in info["edition"].lower():
        raise SandboxBlocked("UNSUPPORTED_WINDOWS_EDITION", f"Windows Sandbox is not supported on {info['edition']}; Windows Pro/Enterprise/Education is required")
    if platform.machine().lower() not in {"amd64", "x86_64", "arm64"}:
        raise SandboxBlocked("UNSUPPORTED_WINDOWS_ARCH", platform.machine())
    candidate = shutil.which("WindowsSandbox.exe")
    if not candidate:
        windir = os.environ.get("WINDIR", r"C:\Windows")
        default = os.path.join(windir, "System32", "WindowsSandbox.exe")
        if os.path.isfile(default):
            candidate = default
    if not candidate or not os.path.isfile(candidate):
        raise SandboxBlocked("OS_WRITE_SANDBOX_UNAVAILABLE", "Windows Sandbox executable not installed/enabled; no unisolated fallback")
    # Never execute a workspace/user-path lookalike instead of the system binary.
    exe = os.path.realpath(candidate)
    system = os.path.realpath(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32"))
    if os.path.normcase(os.path.dirname(exe)) != os.path.normcase(system):
        raise SandboxBlocked("UNTRUSTED_SANDBOX_BINARY", f"Refusing unexpected executable path: {exe}")
    return exe


def doctor() -> dict[str, Any]:
    result: dict[str, Any] = {"engine": "windows_sandbox_vm", "version": VERSION,
                                  "platform": platform.system(), "status": "BLOCKED"}
    try:
        result.update(windows_edition())
        result["windows_sandbox_executable"] = find_windows_sandbox_exe()
        result["status"] = "ELIGIBLE_NOT_ACCEPTED"
        result["message"] = "Host checks passed; a real guest isolation acceptance run is still mandatory"
    except SandboxBlocked as e:
        result["error_code"] = e.code
        result["message"] = e.message
    return result


def sandbox_xml(video_root: str, logo_root: str | None, work: str, guest_script: str, guest_job: str) -> str:
    top = ET.Element("Configuration")
    for key, val in (("VGpu", "Disable"), ("Networking", "Disable"),
                     ("AudioInput", "Disable"), ("VideoInput", "Disable"),
                     ("PrinterRedirection", "Disable"),
                     ("ClipboardRedirection", "Disable"), ("ProtectedClient", "Enable")):
        ET.SubElement(top, key).text = val
    mappings = ET.SubElement(top, "MappedFolders")
    for src, dest, readonly in ((video_root, GUEST_SOURCE, True),
                                 (logo_root, GUEST_LOGO, True),
                                 (work, GUEST_WORK, False)):
        if src is None:
            continue
        folder = ET.SubElement(mappings, "MappedFolder")
        ET.SubElement(folder, "HostFolder").text = src
        ET.SubElement(folder, "SandboxFolder").text = dest
        ET.SubElement(folder, "ReadOnly").text = "true" if readonly else "false"
    command = ET.SubElement(top, "LogonCommand")
    ET.SubElement(command, "Command").text = (
        'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass '
        f'-File "{guest_script}" -JobPath "{guest_job}"'
    )
    return ET.tostring(top, encoding="unicode", xml_declaration=False)


def _write_new(path: Path, data: str) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(data)


def _verify_guest_runner(work: Path) -> Path:
    runner = work / "tools" / GUEST_PROBE
    if not runner.is_file():
        raise SandboxBlocked("GUEST_RUNNER_MISSING", str(runner))
    return runner


def _run_job(*, video_root: str, logo_root: str | None, workspace: str,
             run_id: str, job: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    exe = find_windows_sandbox_exe()
    # Do not attach to or disturb an unrelated Sandbox session.
    active = subprocess.run(["tasklist.exe", "/FI", "IMAGENAME eq WindowsSandbox.exe", "/FO", "CSV", "/NH"],
                            capture_output=True, text=True, timeout=15)
    if active.returncode != 0:
        raise SandboxBlocked("SANDBOX_PROCESS_CHECK_FAILED", "Cannot verify that the host has no existing Sandbox VM")
    if '"WindowsSandbox.exe"' in active.stdout:
        raise SandboxBlocked("SANDBOX_BUSY", "An existing Windows Sandbox process is running")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", run_id):
        raise SandboxBlocked("INVALID_RUN_ID", "Unsafe run ID")
    work = Path(workspace)
    if not work.is_dir():
        raise SandboxBlocked("WORKSPACE_MISSING", str(work))
    runner = _verify_guest_runner(work)
    job_dir = work / "runs" / run_id / "sandbox_jobs"
    job_dir.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(24)
    job_id = "sandbox_" + uuid.uuid4().hex
    job_path = job_dir / f"{job_id}.json"
    result_path = job_dir / f"{job_id}.result.json"
    config_path = job_dir / f"{job_id}.wsb"
    request = dict(job)
    request.update({"nonce": nonce, "result_path": map_path(str(result_path), video_root, logo_root, workspace),
                    "run_id": run_id, "job_id": job_id, "guest_work": GUEST_WORK,
                    "guest_source": GUEST_SOURCE, "guest_logo": GUEST_LOGO if logo_root else None})
    _write_new(job_path, json.dumps(request, ensure_ascii=False, indent=2))
    guest_runner = map_path(str(runner), video_root, logo_root, workspace)
    guest_job = map_path(str(job_path), video_root, logo_root, workspace)
    # Guest runner receives path in environment, avoiding command-quote injection.
    guest_script = guest_runner
    config = sandbox_xml(video_root, logo_root, workspace, guest_script, guest_job)
    # Runner reads the most recently generated job id from a dedicated file.
    # Only one sandbox job may exist per run; lock across process instances.
    lock = job_dir / ".sandbox.lock"
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SandboxBlocked("SANDBOX_BUSY", "Another sandbox job is active; never share a VM") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"job_id": job_id, "nonce": nonce, "created": time.time()}))
        _write_new(config_path, config)
        proc = subprocess.Popen([exe, str(config_path)], cwd=str(work), shell=False,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if result_path.is_file():
                raw = result_path.read_bytes()
                if len(raw) > MAX_RESULT_BYTES:
                    raise SandboxBlocked("SANDBOX_RESULT_TOO_LARGE", "Result report exceeds size limit")
                output = json.loads(raw.decode("utf-8-sig"))
                if output.get("nonce") != nonce or output.get("job_id") != job_id:
                    raise SandboxBlocked("SANDBOX_RESULT_MISMATCH", "Guest result nonce/job ID differs")
                return {**output, "host_config": str(config_path), "host_job": str(job_path)}
            if proc.poll() is not None:
                # Some Windows releases use a small launcher process; wait for
                # guest result rather than trusting launcher exit as success.
                pass
            time.sleep(0.5)
        raise SandboxBlocked("SANDBOX_JOB_TIMEOUT", f"No guest completion result within {timeout_s}s")
    finally:
        lock.unlink(missing_ok=True)


def acceptance(*, binding: dict[str, Any], timeout_s: int = 240) -> dict[str, Any]:
    video, logo, work, run_id = (binding["video_root"], binding.get("logo_root"),
                                 binding["workspace_root"], binding["run_id"])
    job = {"mode": "acceptance", "cwd": GUEST_WORK, "executable": "powershell.exe",
           "args_quoted": "", "acceptance_requirements": ["workspace_rw", "video_root_ro", "logo_root_ro", "network_disabled"]}
    res = _run_job(video_root=video, logo_root=logo, workspace=work, run_id=run_id,
                   job=job, timeout_s=timeout_s)
    checks = res.get("acceptance_checks", {})
    required = ["workspace_rw", "video_root_ro", "network_disabled"] + (["logo_root_ro"] if logo else [])
    if res.get("exit_code") != 0 or any(checks.get(x) is not True for x in required):
        raise SandboxBlocked("SANDBOX_ACCEPTANCE_FAILED", f"Real guest checks did not pass: {checks}")
    record = {"status": "PASS", "engine": "windows_sandbox_vm", "version": VERSION,
              "binding_id": binding["binding_id"], "run_id": run_id,
              "machine_fingerprint": binding["machine_fingerprint"], "video_root": video,
              "logo_root": logo, "workspace_root": work, "guest_checks": checks,
              "proof_job": res["job_id"], "validated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "guest_runner_sha256": hashlib.sha256(_verify_guest_runner(Path(work)).read_bytes()).hexdigest()}
    stamp = Path(work) / "runs" / run_id / "sandbox_acceptance.json"
    stamp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def require_acceptance(binding: dict[str, Any]) -> None:
    stamp = Path(binding["workspace_root"]) / "runs" / binding["run_id"] / "sandbox_acceptance.json"
    if not stamp.is_file():
        raise SandboxBlocked("SANDBOX_NOT_ACCEPTED", "Real Windows Sandbox guest checks have not passed")
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SandboxBlocked("SANDBOX_ACCEPTANCE_INVALID", str(exc)) from exc
    fields = ("binding_id", "run_id", "machine_fingerprint", "video_root", "logo_root", "workspace_root")
    if data.get("guest_runner_sha256") != hashlib.sha256(_verify_guest_runner(Path(binding["workspace_root"])).read_bytes()).hexdigest():
        raise SandboxBlocked("SANDBOX_ACCEPTANCE_STALE", "Guest runner changed since acceptance")
    if data.get("status") != "PASS" or data.get("engine") != "windows_sandbox_vm" or data.get("version") != VERSION or any(data.get(f) != binding.get(f) for f in fields):
        raise SandboxBlocked("SANDBOX_ACCEPTANCE_STALE", "Acceptance stamp does not match current binding/version")
    if any(data.get("guest_checks", {}).get(f) is not True for f in ("workspace_rw", "video_root_ro", "network_disabled")):
        raise SandboxBlocked("SANDBOX_ACCEPTANCE_INCOMPLETE", "Mandatory guest tests missing")
    if binding.get("logo_root") and data.get("guest_checks", {}).get("logo_root_ro") is not True:
        raise SandboxBlocked("SANDBOX_ACCEPTANCE_INCOMPLETE", "Logo read-only test missing")


def execute(*, binding: dict[str, Any], cwd: str, command: list[str], timeout_s: int = 3600) -> dict[str, Any]:
    # Re-evaluate system capability, then require fresh acceptance for same binding.
    find_windows_sandbox_exe()
    require_acceptance(binding)
    work, video, logo = binding["workspace_root"], binding["video_root"], binding.get("logo_root")
    guest_exe, args = classify_command(command, video, logo, work)
    guest_cwd = map_path(cwd, video, logo, work)
    if not under(cwd, work):
        raise SandboxBlocked("CWD_OUTSIDE_WORKSPACE", cwd)
    job = {"mode": "execute", "cwd": guest_cwd, "executable": guest_exe, "args_quoted": args}
    return _run_job(video_root=video, logo_root=logo, workspace=work,
                    run_id=binding["run_id"], job=job, timeout_s=timeout_s)
