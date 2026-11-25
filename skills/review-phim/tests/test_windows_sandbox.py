"""Unit checks only. They are not equivalent to a real Windows Sandbox guest acceptance."""
import importlib.util
import os
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "windows_sandbox.py"
spec = importlib.util.spec_from_file_location("windows_sandbox", HERE)
win = importlib.util.module_from_spec(spec)
spec.loader.exec_module(win)

VIDEO = r"E:\phim_7"
WORK = r"E:\phim_7\WORKSPACE"
LOGO = r"E:\logo"


class WindowsSandboxTests(unittest.TestCase):
    def test_wsb_strict_mappings_and_no_network(self):
        xml = win.sandbox_xml(VIDEO, LOGO, WORK,
                              r"C:\ReviewWorkspace\tools\windows_sandbox_guest.ps1",
                              r"C:\ReviewWorkspace\runs\x\sandbox_jobs\job.json")
        root = ET.fromstring(xml)
        for prop in ("Networking", "VGpu", "AudioInput", "VideoInput", "PrinterRedirection", "ClipboardRedirection"):
            self.assertEqual(root.findtext(prop), "Disable")
        self.assertEqual(root.findtext("ProtectedClient"), "Enable")
        mappings = root.findall("./MappedFolders/MappedFolder")
        self.assertEqual(len(mappings), 3)
        self.assertEqual([x.findtext("ReadOnly") for x in mappings], ["true", "true", "false"])
        self.assertEqual([x.findtext("HostFolder") for x in mappings], [VIDEO, LOGO, WORK])
        self.assertIn("-JobPath", root.findtext("./LogonCommand/Command"))

    def test_host_to_guest_translation_scoped(self):
        self.assertEqual(win.map_path(r"E:\phim_7\WORKSPACE\runs\r\result.json", VIDEO, LOGO, WORK),
                         r"C:\ReviewWorkspace\runs\r\result.json")
        self.assertEqual(win.map_path(r"E:\phim_7\film.mp4", VIDEO, LOGO, WORK),
                         r"C:\ReviewSourceReadOnly\film.mp4")
        self.assertEqual(win.map_path(r"E:\logo\watermark.png", VIDEO, LOGO, WORK),
                         r"C:\ReviewLogoReadOnly\watermark.png")
        for path in (r"E:\phim_70\bad.txt", r"C:\Windows\Temp\abc", r"F:\other\film.mp4"):
            with self.assertRaises(win.SandboxBlocked):
                win.map_path(path, VIDEO, LOGO, WORK)

    def test_argument_translation_and_no_unscoped_runtime(self):
        executable = r"E:\phim_7\WORKSPACE\runtime\python\python.exe"
        cmd = [executable, r"E:\phim_7\WORKSPACE\scripts\task.py", "--input=E:\\phim_7\\film.mp4", "--language", "vi"]
        guest_exe, args = win.classify_command(cmd, VIDEO, LOGO, WORK)
        self.assertTrue(guest_exe.startswith(win.GUEST_WORK))
        self.assertIn("ReviewSourceReadOnly", args)
        self.assertIn("ReviewWorkspace", args)
        with self.assertRaises(win.SandboxBlocked):
            win.classify_command([r"E:\phim_7\.review-phim\venv\Scripts\python.exe", "a.py"], VIDEO, LOGO, WORK)
        with self.assertRaises(win.SandboxBlocked):
            win.classify_command(["python.exe", "a.py"], VIDEO, LOGO, WORK)

    def test_no_unaccepted_execution(self):
        b = {"workspace_root": str(pathlib.Path(tempfile.mkdtemp())), "run_id": "id", "binding_id": "bind",
             "machine_fingerprint": "machine", "video_root": VIDEO, "logo_root": LOGO}
        with patch.object(win, "find_windows_sandbox_exe", return_value=r"C:\Windows\System32\WindowsSandbox.exe"):
            with self.assertRaises(win.SandboxBlocked) as cm:
                win.execute(binding=b, cwd=WORK, command=["powershell.exe", "-NoProfile"])
            self.assertIn("SANDBOX_NOT_ACCEPTED", str(cm.exception))

    def test_windows_home_always_blocks(self):
        with patch.object(win.platform, "system", return_value="Windows"), \
             patch.object(win, "windows_edition", return_value={"edition": "CoreSingleLanguage", "build": "26300", "product": "Windows 11 Home Single Language"}):
            with self.assertRaises(win.SandboxBlocked) as cm:
                win.find_windows_sandbox_exe()
            self.assertIn("UNSUPPORTED_WINDOWS_EDITION", str(cm.exception))

    def test_non_windows_fails_closed(self):
        with patch.object(win.platform, "system", return_value="Linux"):
            self.assertEqual(win.doctor()["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()


class AcceptanceGuardTests(unittest.TestCase):
    def test_rejects_forged_or_stale_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            run_dir = pathlib.Path(root) / "runs" / "r1"
            tools = pathlib.Path(root) / "tools"
            run_dir.mkdir(parents=True)
            tools.mkdir(parents=True)
            (tools / win.GUEST_PROBE).write_text("valid guest runner", encoding="utf-8")
            binding = {
                "workspace_root": root,
                "video_root": VIDEO,
                "logo_root": LOGO,
                "binding_id": "b1",
                "run_id": "r1",
                "machine_fingerprint": "f1",
            }
            proof = {
                "status": "PASS", "engine": "windows_sandbox_vm", "version": win.VERSION,
                "binding_id": "other", "run_id": "r1", "machine_fingerprint": "f1",
                "video_root": VIDEO, "workspace_root": root, "logo_root": LOGO,
                "guest_runner_sha256": __import__("hashlib").sha256(b"valid guest runner").hexdigest(),
                "guest_checks": {"workspace_rw": True, "video_root_ro": True,
                                 "logo_root_ro": True, "network_disabled": True},
            }
            stamp = run_dir / "sandbox_acceptance.json"
            stamp.write_text(__import__("json").dumps(proof), encoding="utf-8")
            with self.assertRaises(win.SandboxBlocked) as cm:
                win.require_acceptance(binding)
            self.assertIn("SANDBOX_ACCEPTANCE_STALE", str(cm.exception))
            proof["binding_id"] = "b1"
            stamp.write_text(__import__("json").dumps(proof), encoding="utf-8")
            win.require_acceptance(binding)
            (tools / win.GUEST_PROBE).write_text("tampered", encoding="utf-8")
            with self.assertRaises(win.SandboxBlocked):
                win.require_acceptance(binding)
