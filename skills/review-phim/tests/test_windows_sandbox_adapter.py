"""Prove adapter cannot launch a Windows guest without the original approval gate."""
import importlib.util
import pathlib
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("windows_sandbox_adapter", ROOT / "windows_sandbox_adapter.py")
# Standalone load of windows_sandbox helper from the same source directory.
import sys
sys.path.insert(0, str(ROOT))
import windows_sandbox
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class AdapterTests(unittest.TestCase):
    def test_denied_stage_does_not_launch_guest(self):
        binding = {"run_id": "r", "video_root": r"E:\phim_7", "workspace_root": r"E:\phim_7\WORKSPACE",
                   "logo_root": r"E:\logo", "binding_id": "b", "device_id": "d", "machine_fingerprint": "x"}
        fake = types.SimpleNamespace()
        fake.load_binding = Mock(return_value=binding)
        fake.validate_declared_paths = Mock(return_value=(r"E:\phim_7", r"E:\logo"))
        fake.verify_execution_stage = Mock(side_effect=ValueError("NOT_APPROVED"))
        fake.canonical = lambda x: x
        fake.workspace_root = lambda x: r"E:\phim_7\WORKSPACE"
        args = types.SimpleNamespace(binding_file="ignored", video_root=r"E:\phim_7", logo_root=r"E:\logo",
            device_id="d", link_id="l", run_id="r", cwd=None, read_path=[], write_path=[],
            command=["--", "powershell.exe", "-NoProfile"], phase="step")
        with patch.object(adapter.platform, "system", return_value="Windows"), \
             patch.object(adapter.win, "execute") as execute:
            with self.assertRaisesRegex(ValueError, "NOT_APPROVED"):
                adapter.command(args, fake)
            execute.assert_not_called()
            fake.verify_execution_stage.assert_called_once()


if __name__ == "__main__":
    unittest.main()
