#!/usr/bin/env python3
"""Binding-preserving Windows Sandbox adapter for Review-Phim 1.3.0.

On Windows, use this as the CLI entrypoint *instead of* server_binding.py.
It imports and reuses the unmodified official binding/workflow/state functions.
No production subprocess is launched unless stage approval and guest acceptance
have both passed; no fallback to an unisolated host subprocess is possible.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path

import windows_sandbox as win


def load_binding_helper():
    file = Path(__file__).resolve().with_name("server_binding.py")
    spec = importlib.util.spec_from_file_location("review_original_binding", str(file))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot import the original server-binding helper")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def shared_arguments(parser: argparse.ArgumentParser) -> None:
    for key in ("binding-file", "run-id", "device-id", "link-id", "video-root"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--logo-root")


def command(args, mod) -> None:
    if platform.system() != "Windows":
        # Preserve the existing Linux bubblewrap implementation.
        mod.cmd_run_command(args)
        return
    binding = mod.load_binding(
        Path(args.binding_file), Path(args.video_root),
        Path(args.logo_root) if args.logo_root else None,
        args.device_id, args.link_id, args.run_id,
    )
    video, _ = mod.validate_declared_paths(binding, args.cwd, args.read_path or [], args.write_path or [])
    requested = list(args.command or [])
    if requested and requested[0] == "--":
        requested = requested[1:]
    if not requested:
        raise ValueError("Missing executable arguments")
    # This checks per-step approval, installation-plan hash and the phase.
    mod.verify_execution_stage(binding, args)
    cwd = str(mod.canonical(args.cwd) if args.cwd else mod.workspace_root(video))
    result = win.execute(binding=binding, cwd=cwd, command=requested)
    code = int(result.get("exit_code", 1))
    print(json.dumps({
        "status": "command_finished" if code == 0 else "command_failed",
        "returncode": code, "run_id": binding["run_id"],
        "binding_id": binding["binding_id"], "device_id": binding["device_id"],
        "video_root": binding["video_root"], "workspace_root": binding["workspace_root"],
        "phase": args.phase, "isolation": "windows_sandbox_vm",
        "guest_job_id": result.get("job_id"), "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }, ensure_ascii=False))
    if code:
        raise SystemExit(code)


def sandbox_control(argv: list[str], mod) -> None:
    parser = argparse.ArgumentParser(description="Review-Phim Windows sandbox OS isolation check")
    shared_arguments(parser)
    args = parser.parse_args(argv[1:])
    # Only `doctor` is a no-side-effect read-only capability query.
    if argv[0] == "sandbox-doctor":
        mod.load_binding(Path(args.binding_file), Path(args.video_root),
                         Path(args.logo_root) if args.logo_root else None,
                         args.device_id, args.link_id, args.run_id)
        result = win.doctor()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["status"] != "ELIGIBLE_NOT_ACCEPTED":
            raise SystemExit(2)
        return
    binding = mod.load_binding(Path(args.binding_file), Path(args.video_root),
                               Path(args.logo_root) if args.logo_root else None,
                               args.device_id, args.link_id, args.run_id)
    if argv[0] == "sandbox-acceptance":
        result = win.acceptance(binding=binding)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    raise ValueError("Unknown sandbox control action")


def main() -> None:
    try:
        mod = load_binding_helper()
        if len(sys.argv) > 1 and sys.argv[1] in ("sandbox-doctor", "sandbox-acceptance"):
            sandbox_control(sys.argv[1:], mod)
            return
        parser = mod.build_parser()
        args = parser.parse_args()
        if args.func == mod.cmd_run_command:
            command(args, mod)
        else:
            # Immutable binding and workflow paths stay controlled by original helper.
            args.func(args)
    except (win.SandboxBlocked, ValueError, RuntimeError, OSError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
