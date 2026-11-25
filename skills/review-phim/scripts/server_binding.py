#!/usr/bin/env python3
"""Immutable server + folder binding guard for Review-Phim.

Run this helper on the selected remote server. It fails closed when the
Desktop Commander device/account, machine fingerprint, or canonical folders
do not match the binding created at the beginning of the run.
"""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import stat
import datetime as dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path

SCHEMA_VERSION = 3


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def canonical(path: str | Path) -> Path:
    return Path(os.path.realpath(os.path.abspath(os.path.expanduser(str(path)))))


def normalized(path: Path) -> str:
    # normcase makes path comparison case-insensitive on Windows.
    return os.path.normcase(str(canonical(path)))


def is_within(path: Path, root: Path) -> bool:
    p, r = normalized(path), normalized(root)
    try:
        return os.path.commonpath([p, r]) == r
    except (ValueError, OSError):
        return False


def require_within(path: str | Path, root: Path, label: str) -> Path:
    p, r = canonical(path), canonical(root)
    if not is_within(p, r):
        raise ValueError(f"{label} is outside the selected folder: {p}")
    return p


def ensure_disjoint(video_root: Path, logo_root: Path | None) -> None:
    if logo_root is None:
        return
    if is_within(video_root, logo_root) or is_within(logo_root, video_root):
        raise ValueError("VIDEO_ROOT and LOGO_ROOT overlap; choose two separate folders")


def workspace_root(video_root: Path, *, create: bool = False) -> Path:
    """Return the one writable WORKSPACE directly inside the selected film folder.

    A link/junction at WORKSPACE is forbidden even if it resolves inside VIDEO_ROOT.
    Creating WORKSPACE never writes elsewhere. Existing contents are never reset.
    """
    video = canonical(video_root)
    raw = video / "WORKSPACE"
    is_junction = getattr(raw, "is_junction", lambda: False)
    if raw.is_symlink() or is_junction():
        raise ValueError("WORKSPACE_LINK_FORBIDDEN: WORKSPACE must be a real folder, not a link or junction")
    if create:
        raw.mkdir(mode=0o700, exist_ok=True)
    if not raw.is_dir():
        raise NotADirectoryError(f"WORKSPACE is missing: {raw}")
    root = canonical(raw)
    if not is_within(root, video) or normalized(root) != normalized(raw):
        raise ValueError("WORKSPACE_ESCAPE: WORKSPACE does not resolve to the selected film folder")
    return root


def stable_machine_id() -> str:
    system = platform.system()
    if system == "Windows":
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            if value:
                return str(value).strip()
        except Exception as exc:
            raise RuntimeError("Cannot read Windows MachineGuid; refusing an unverified server binding") from exc
    elif system == "Linux":
        for candidate in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
            try:
                value = candidate.read_text(encoding="utf-8").strip()
                if value:
                    return value
            except OSError:
                pass
        raise RuntimeError("Cannot read Linux machine-id; refusing an unverified server binding")
    elif system == "Darwin":
        try:
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True, text=True, check=True, timeout=10,
            )
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
            if match:
                return match.group(1)
        except Exception as exc:
            raise RuntimeError("Cannot read macOS IOPlatformUUID; refusing an unverified server binding") from exc
        raise RuntimeError("macOS IOPlatformUUID was not available; refusing an unverified server binding")
    raise RuntimeError(f"Unsupported OS for stable server binding: {system}")


def machine_identity() -> dict:
    stable_id = stable_machine_id()
    material = "\n".join([
        platform.system(),
        platform.machine(),
        stable_id,
    ])
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "fingerprint": hashlib.sha256(material.encode("utf-8")).hexdigest(),
    }


def path_id(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved = canonical(path)
    stat = resolved.stat()
    # Bind both the canonical path and the underlying directory identity.
    # This detects a folder that was deleted/recreated at the same path.
    material = "|".join((
        normalized(resolved),
        str(getattr(stat, "st_dev", 0)),
        str(getattr(stat, "st_ino", 0)),
    ))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_binding(binding_file: Path, video_root: Path, logo_root: Path | None,
                 device_id: str, link_id: str, run_id: str | None = None) -> dict:
    video = canonical(video_root)
    logo = canonical(logo_root) if logo_root else None
    ensure_disjoint(video, logo)
    binding_path = require_within(binding_file, workspace_root(video), "Binding manifest")
    if not binding_path.is_file():
        raise FileNotFoundError(f"Binding manifest not found: {binding_path}")
    data = json.loads(binding_path.read_text(encoding="utf-8"))
    work = workspace_root(video)
    if normalized(binding_path) != normalized(work / "runs" / data.get("run_id", "") / "server_binding.json"):
        raise ValueError("BINDING_SCOPE_MISMATCH: binding file must stay in WORKSPACE/runs/<RUN_ID>")
    if data.get("workspace_root") != str(work) or data.get("workspace_root_id") != path_id(work):
        raise ValueError("WORKSPACE_IDENTITY_MISMATCH: the WORKSPACE folder changed")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported server binding schema; create a new run binding")
    if normalized(Path(data["video_root"])) != normalized(video):
        raise ValueError("VIDEO_ROOT does not match the immutable selected folder")
    saved_logo = canonical(data["logo_root"]) if data.get("logo_root") else None
    if (normalized(saved_logo) if saved_logo else None) != (normalized(logo) if logo else None):
        raise ValueError("LOGO_ROOT does not match the immutable selected folder")
    if data.get("video_root_id") != path_id(video) or data.get("logo_root_id") != path_id(logo):
        raise ValueError("Selected folder identity fingerprint changed")
    if data.get("device_id") != device_id:
        raise ValueError("Desktop Commander deviceId mismatch; refusing to use another server")
    if data.get("link_id") != link_id:
        raise ValueError("Desktop Commander account link_id mismatch; refusing to switch account")
    if run_id and data.get("run_id") != run_id:
        raise ValueError("Run ID mismatch; refusing to mix two production runs")
    current = machine_identity()
    if current["fingerprint"] != data.get("machine_fingerprint"):
        raise ValueError("Physical/virtual machine fingerprint mismatch; refusing cross-server execution")
    return data


def cmd_bind(args) -> None:
    video = canonical(args.video_root)
    logo = canonical(args.logo_root) if args.logo_root else None
    if not video.is_dir():
        raise NotADirectoryError(f"VIDEO_ROOT does not exist: {video}")
    if logo is not None and not logo.is_dir():
        raise NotADirectoryError(f"LOGO_ROOT does not exist: {logo}")
    ensure_disjoint(video, logo)
    if not args.device_id.strip() or not args.link_id.strip():
        raise ValueError("Exact Desktop Commander deviceId and link_id are required")
    work = workspace_root(video, create=True)
    # Idempotent setup: create child directories without deleting existing run data.
    for directory in ("tools", "runtime", "cache", "tmp", "runs"):
        target = work / directory
        if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
            raise ValueError(f"WORKSPACE_CHILD_LINK_FORBIDDEN: {target}")
        target.mkdir(exist_ok=True)
    binding_path = require_within(args.binding_file, work, "Binding manifest")
    expected_binding = work / "runs" / args.run_id / "server_binding.json"
    if normalized(binding_path) != normalized(expected_binding):
        raise ValueError("Binding manifest must be inside this run's VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/ folder")
    binding_path.parent.mkdir(parents=True, exist_ok=True)
    if binding_path.exists():
        raise FileExistsError(f"Refusing to replace an existing server binding: {binding_path}")
    identity = machine_identity()
    data = {
        "schema_version": SCHEMA_VERSION,
        "binding_id": uuid.uuid4().hex,
        "run_id": args.run_id,
        "server_label": args.server_label,
        "link_id": args.link_id,
        "device_id": args.device_id,
        "machine_fingerprint": identity["fingerprint"],
        "machine_identity": {k: identity[k] for k in ("system", "release", "machine", "hostname")},
        "video_root": str(video),
        "video_root_id": path_id(video),
        "workspace_root": str(work),
        "workspace_root_id": path_id(work),
        "logo_root": str(logo) if logo else None,
        "logo_root_id": path_id(logo),
        "created_at": now(),
        "policy": {
            "video_root": "source_read_only",
            "workspace_root": "read_write",
            "logo_root": "read_only",
            "source_video": "read_only",
            "server_failover": "forbidden",
        },
    }
    # Exclusive create: never silently overwrite or retarget a binding.
    with binding_path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({
        "status": "bound",
        "binding_id": data["binding_id"],
        "run_id": data["run_id"],
        "server_label": data["server_label"],
        "device_id": data["device_id"],
        "link_id": data["link_id"],
        "video_root": data["video_root"],
        "workspace_root": data["workspace_root"],
        "logo_root": data["logo_root"],
        "machine_fingerprint": data["machine_fingerprint"],
    }, ensure_ascii=False))


def cmd_verify(args) -> None:
    data = load_binding(
        Path(args.binding_file), Path(args.video_root),
        Path(args.logo_root) if args.logo_root else None,
        args.device_id, args.link_id, args.run_id,
    )
    video = canonical(args.video_root)
    work = workspace_root(video)
    logo = canonical(args.logo_root) if args.logo_root else None
    for raw in args.write_path or []:
        require_within(raw, work, "Write target")
    for raw in args.read_path or []:
        p = canonical(raw)
        if not is_within(p, video) and (logo is None or not is_within(p, logo)):
            raise ValueError(f"Read target is outside VIDEO_ROOT and LOGO_ROOT: {p}")
    if args.cwd:
        require_within(args.cwd, work, "Working directory")
    print(json.dumps({
        "status": "verified",
        "binding_id": data["binding_id"],
        "run_id": data["run_id"],
        "server_label": data["server_label"],
        "device_id": data["device_id"],
        "link_id": data["link_id"],
        "video_root": data["video_root"],
        "workspace_root": data["workspace_root"],
        "logo_root": data["logo_root"],
        "machine_fingerprint": data["machine_fingerprint"],
        "write_paths_checked": len(args.write_path or []),
        "read_paths_checked": len(args.read_path or []),
    }, ensure_ascii=False))


def binding_projection(data: dict) -> dict:
    return {
        "binding_id": data["binding_id"],
        "run_id": data["run_id"],
        "server_label": data["server_label"],
        "link_id": data["link_id"],
        "device_id": data["device_id"],
        "machine_fingerprint": data["machine_fingerprint"],
        "video_root": data["video_root"],
        "video_root_id": data["video_root_id"],
        "workspace_root": data["workspace_root"],
        "workspace_root_id": data["workspace_root_id"],
        "logo_root": data["logo_root"],
        "logo_root_id": data["logo_root_id"],
    }


def state_path_from_workflow_args(workflow_args: list[str], video_root: Path, run_id: str) -> Path:
    try:
        index = workflow_args.index("--state")
        raw = workflow_args[index + 1]
    except (ValueError, IndexError):
        raise ValueError("Every workflow-state command must include --state with an absolute path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("--state must be an absolute path inside VIDEO_ROOT")
    resolved = require_within(candidate, video_root, "Workflow state file")
    expected = workspace_root(video_root) / "runs" / run_id / "state.json"
    if normalized(resolved) != normalized(expected):
        raise ValueError("Workflow state must be this run's VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/state.json")
    return resolved


def read_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, data: dict) -> None:
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def validate_state_binding(state_file: Path, binding: dict) -> dict:
    state = read_json(state_file)
    if normalized(Path(state.get("workspace_root", ""))) != normalized(Path(binding["workspace_root"])):
        raise ValueError("Workflow state WORKSPACE does not match the selected film folder")
    if state.get("run_id") != binding.get("run_id"):
        raise ValueError("Workflow state run_id does not match the selected server binding")
    if normalized(Path(state.get("video_root", ""))) != normalized(Path(binding["video_root"])):
        raise ValueError("Workflow state VIDEO_ROOT does not match the selected folder")
    saved_logo = state.get("logo_root")
    expected_logo = binding.get("logo_root")
    if (normalized(Path(saved_logo)) if saved_logo else None) != (normalized(Path(expected_logo)) if expected_logo else None):
        raise ValueError("Workflow state LOGO_ROOT does not match the selected folder")
    if state.get("server_binding") != binding_projection(binding):
        raise ValueError("Workflow state is not bound to this exact server, account, run and folder")
    if state.get("remote_device_id") != binding.get("device_id"):
        raise ValueError("Workflow state remote device ID does not match the selected server")
    if state.get("remote_link_id") != binding.get("link_id"):
        raise ValueError("Workflow state connection link ID does not match the selected account")
    if state.get("server_fingerprint") != binding.get("machine_fingerprint"):
        raise ValueError("Workflow state machine fingerprint does not match the selected server")
    return state


def bind_workflow_arguments(workflow_args: list[str], binding: dict) -> list[str]:
    """Require workflow-state CLI context to match the immutable run binding."""
    result = list(workflow_args)
    expected = {
        "--remote-device-id": (binding["device_id"], False),
        "--remote-link-id": (binding["link_id"], False),
        "--expected-server-fingerprint": (binding["machine_fingerprint"], False),
        "--video-root": (binding["video_root"], True),
    }
    if binding.get("logo_root") is not None:
        expected["--logo-root"] = (binding["logo_root"], True)
    for flag, (value, is_path) in expected.items():
        if flag in result:
            index = result.index(flag)
            if index + 1 >= len(result):
                raise ValueError(f"Workflow argument {flag} has no value")
            actual = result[index + 1]
            matches = normalized(Path(actual)) == normalized(Path(value)) if is_path else actual == value
            if not matches:
                raise ValueError(f"Workflow argument {flag} does not match the immutable server/folder binding")
        else:
            result.extend([flag, value])
    if binding.get("logo_root") is None and "--logo-root" in result:
        raise ValueError("Workflow supplied a LOGO_ROOT although this run was bound with no logo folder")
    if result[0] == "init":
        init_expected = {"--run-id": binding["run_id"], "--server-label": binding["server_label"]}
        for flag, value in init_expected.items():
            if flag in result:
                index = result.index(flag)
                if index + 1 >= len(result) or result[index + 1] != value:
                    raise ValueError(f"Workflow argument {flag} does not match the immutable run binding")
            else:
                result.extend([flag, value])
    return result


def validate_declared_paths(data: dict, cwd: str | None, read_paths: list[str], write_paths: list[str]) -> tuple[Path, Path | None]:
    video = canonical(data["video_root"])
    work = workspace_root(video)
    logo = canonical(data["logo_root"]) if data.get("logo_root") else None
    if cwd:
        require_within(cwd, work, "Working directory")
    for raw in read_paths:
        target = canonical(raw)
        if not is_within(target, video) and (logo is None or not is_within(target, logo)):
            raise ValueError(f"Read target is outside VIDEO_ROOT and LOGO_ROOT: {target}")
    for raw in write_paths:
        require_within(raw, work, "Write target")
    return video, logo


def scoped_environment(video: Path) -> dict:
    work = workspace_root(video)
    temp_root = work / "tmp"
    cache_root = work / "cache"
    temp_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "TMP": str(temp_root),
        "TEMP": str(temp_root),
        "TMPDIR": str(temp_root),
        "PIP_CACHE_DIR": str(cache_root / "pip"),
        "HF_HOME": str(cache_root / "huggingface"),
        "HF_HUB_CACHE": str(cache_root / "huggingface" / "hub"),
        "TORCH_HOME": str(cache_root / "torch"),
        "XDG_CACHE_HOME": str(cache_root / "xdg"),
        "NUMBA_CACHE_DIR": str(cache_root / "numba"),
        "MPLCONFIGDIR": str(cache_root / "matplotlib"),
    })
    return env


def verify_execution_stage(data: dict, args) -> dict:
    """Reject any subprocess that is not inside a currently approved, RUNNING stage.

    This is a workflow gate, not an OS permissions boundary. The sandbox below
    supplies the filesystem boundary; neither is sufficient on its own.
    """
    video = canonical(data["video_root"])
    work = workspace_root(video)
    helper = require_within(work / "tools" / "workflow_state.py", work, "Workflow guard")
    if not helper.is_file():
        raise RuntimeError("WORKFLOW_HELPER_MISSING: no command may run before the state guard exists")
    spec = importlib.util.spec_from_file_location("review_phim_runtime_gate", helper)
    if not spec or not spec.loader:
        raise RuntimeError("WORKFLOW_HELPER_INVALID")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state_file = work / "runs" / data["run_id"] / "state.json"
    state = module.load_state(state_file)
    module.validate_cli_binding(argparse.Namespace(
        remote_device_id=data["device_id"], remote_link_id=data["link_id"],
        expected_server_fingerprint=data["machine_fingerprint"],
        video_root=video, logo_root=data.get("logo_root")), state)
    if state.get("run_id") != data["run_id"] or state.get("server_binding") != binding_projection(data):
        raise RuntimeError("WORKFLOW_SERVER_BINDING_MISMATCH")
    module.validate_command_gate(state, args.phase, step=args.step, item_id=args.item_id)
    return state


def trusted_bwrap() -> str:
    """Fail closed without a root-owned, non-writable Linux bubblewrap binary."""
    if platform.system() != "Linux":
        raise RuntimeError("OS_WRITE_SANDBOX_UNAVAILABLE: Windows/macOS require a separately configured isolated runner; no unisolated subprocess permitted")
    binary = shutil.which("bwrap")
    if not binary:
        raise RuntimeError("OS_WRITE_SANDBOX_UNAVAILABLE: install/configure trusted bubblewrap or use an isolated machine; command refused")
    exe = canonical(binary)
    if not exe.is_file() or is_within(exe, Path(os.environ.get("HOME", "/nonexistent"))) or exe.stat().st_uid != 0:
        raise RuntimeError("UNTRUSTED_SANDBOX_BINARY: bubblewrap must be system-installed and root-owned")
    if exe.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise RuntimeError("UNTRUSTED_SANDBOX_BINARY: bubblewrap is writable by non-root")
    return str(exe)


def isolated_argv(binary: str, work: Path, cwd: Path, command: list[str]) -> list[str]:
    """Readonly host root + only writable host bind-mount at WORKSPACE."""
    return [
        binary, "--die-with-parent", "--new-session", "--unshare-all", "--share-net",
        "--ro-bind", "/", "/",
        "--bind", str(work), str(work),
        "--proc", "/proc", "--dev", "/dev", "--chdir", str(cwd), "--",
        *command,
    ]


def cmd_run_command(args) -> None:
    data = load_binding(
        Path(args.binding_file), Path(args.video_root),
        Path(args.logo_root) if args.logo_root else None,
        args.device_id, args.link_id, args.run_id,
    )
    video, _logo = validate_declared_paths(data, args.cwd, args.read_path or [], args.write_path or [])
    command = list(args.command or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("A command is required after --; commands are executed without a shell")
    verify_execution_stage(data, args)
    cwd = canonical(args.cwd) if args.cwd else workspace_root(video)
    work = workspace_root(video)
    sandbox_binary = trusted_bwrap()
    sandboxed = isolated_argv(sandbox_binary, work, cwd, command)
    result = subprocess.run(sandboxed, cwd=str(work), env=scoped_environment(video), check=False)
    print(json.dumps({
        "status": "command_finished" if result.returncode == 0 else "command_failed",
        "returncode": result.returncode,
        "binding_id": data["binding_id"],
        "run_id": data["run_id"],
        "device_id": data["device_id"],
        "video_root": data["video_root"],
        "cwd": str(cwd),
        "read_paths_checked": len(args.read_path or []),
        "write_paths_checked": len(args.write_path or []),
        "executable": command[0],
        "isolation": "linux_bubblewrap_ro_root_rw_workspace",
        "phase": args.phase,
    }, ensure_ascii=False))
    if result.returncode:
        raise SystemExit(result.returncode)


def cmd_run_workflow(args) -> None:
    data = load_binding(
        Path(args.binding_file), Path(args.video_root),
        Path(args.logo_root) if args.logo_root else None,
        args.device_id, args.link_id, args.run_id,
    )
    video = canonical(args.video_root)
    script = require_within(args.workflow_script, workspace_root(video), "Workflow helper")
    if not script.is_file():
        raise FileNotFoundError(f"Workflow helper not found inside VIDEO_ROOT: {script}")
    workflow_args = list(args.workflow_args or [])
    if workflow_args and workflow_args[0] == "--":
        workflow_args = workflow_args[1:]
    if not workflow_args:
        raise ValueError("A workflow_state.py subcommand is required after --")
    binding = binding_projection(data)
    workflow_args = bind_workflow_arguments(workflow_args, data)
    state_file = state_path_from_workflow_args(workflow_args, video, args.run_id)
    is_init = workflow_args[0] == "init"
    if is_init:
        if state_file.exists():
            raise FileExistsError(f"Refusing to overwrite an existing run state: {state_file}")
    else:
        validate_state_binding(state_file, data)

    result = subprocess.run(
        [sys.executable, str(script), *workflow_args],
        cwd=str(workspace_root(video)), env=scoped_environment(video), check=False,
    )
    if result.returncode:
        print(json.dumps({
            "status": "workflow_command_failed",
            "returncode": result.returncode,
            "binding_id": data["binding_id"],
            "run_id": data["run_id"],
            "device_id": data["device_id"],
            "video_root": data["video_root"],
        }, ensure_ascii=False))
        raise SystemExit(result.returncode)

    if is_init:
        state = read_json(state_file)
        if state.get("run_id") != data.get("run_id"):
            raise ValueError("New workflow state run_id does not match server binding")
        if normalized(Path(state.get("video_root", ""))) != normalized(video):
            raise ValueError("New workflow state VIDEO_ROOT does not match server binding")
        saved_logo = state.get("logo_root")
        expected_logo = data.get("logo_root")
        if (normalized(Path(saved_logo)) if saved_logo else None) != (normalized(Path(expected_logo)) if expected_logo else None):
            raise ValueError("New workflow state LOGO_ROOT does not match server binding")
        state["server_binding"] = binding
        atomic_json(state_file, state)
        validate_state_binding(state_file, data)
    else:
        # Re-read after mutation to ensure the helper did not alter the binding.
        validate_state_binding(state_file, data)

    print(json.dumps({
        "status": "workflow_command_finished",
        "returncode": 0,
        "binding_id": data["binding_id"],
        "run_id": data["run_id"],
        "device_id": data["device_id"],
        "video_root": data["video_root"],
        "state_file": str(state_file),
    }, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    bind = sub.add_parser("bind", help="create an immutable per-run server/folder binding")
    bind.add_argument("--binding-file", required=True, type=Path)
    bind.add_argument("--run-id", required=True)
    bind.add_argument("--server-label", required=True)
    bind.add_argument("--device-id", required=True)
    bind.add_argument("--link-id", required=True)
    bind.add_argument("--video-root", required=True, type=Path)
    bind.add_argument("--logo-root", type=Path)
    bind.set_defaults(func=cmd_bind)
    verify = sub.add_parser("verify", help="verify server identity and folder scope before each action")
    verify.add_argument("--binding-file", required=True, type=Path)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--device-id", required=True)
    verify.add_argument("--link-id", required=True)
    verify.add_argument("--video-root", required=True, type=Path)
    verify.add_argument("--logo-root", type=Path)
    verify.add_argument("--write-path", action="append", default=[])
    verify.add_argument("--read-path", action="append", default=[])
    verify.add_argument("--cwd")
    verify.set_defaults(func=cmd_verify)
    command = sub.add_parser("run-command", help="verify binding and declared paths, then execute one argument-list command without a shell")
    command.add_argument("--binding-file", required=True, type=Path)
    command.add_argument("--run-id", required=True)
    command.add_argument("--device-id", required=True)
    command.add_argument("--link-id", required=True)
    command.add_argument("--video-root", required=True, type=Path)
    command.add_argument("--logo-root", type=Path)
    command.add_argument("--cwd")
    command.add_argument("--phase", required=True, choices=["install", "preflight", "step", "repair"])
    command.add_argument("--step", type=int)
    command.add_argument("--item-id")
    command.add_argument("--read-path", action="append", default=[])
    command.add_argument("--write-path", action="append", default=[])
    command.add_argument("command", nargs=argparse.REMAINDER)
    command.set_defaults(func=cmd_run_command)

    run = sub.add_parser("run-workflow", help="verify binding, then run the workflow-state helper on this server")
    run.add_argument("--binding-file", required=True, type=Path)
    run.add_argument("--run-id", required=True)
    run.add_argument("--device-id", required=True)
    run.add_argument("--link-id", required=True)
    run.add_argument("--video-root", required=True, type=Path)
    run.add_argument("--logo-root", type=Path)
    run.add_argument("--workflow-script", required=True)
    run.add_argument("workflow_args", nargs=argparse.REMAINDER)
    run.set_defaults(func=cmd_run_workflow)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        parser.exit(2, f"BLOCKED: {exc}\n")


if __name__ == "__main__":
    main()
