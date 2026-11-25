"""Integration probes of the remote binding wrapper and actual workflow helper.

Only ephemeral directories are touched. No command is sent to a real user server.
"""
import argparse
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("review_runtime_binding", SCRIPT_DIR / "server_binding.py")
binding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(binding)


class RuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="review_exec_integration_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / "film"
        self.logo = self.root / "logo"
        self.video.mkdir()
        self.logo.mkdir()
        self.run = "integration-run"
        self.work = self.video / "WORKSPACE"
        self.tools = self.work / "tools"
        self.tools.mkdir(parents=True)
        self.helper = self.tools / "workflow_state.py"
        shutil.copy2(SCRIPT_DIR / "workflow_state.py", self.helper)
        self.binding_file = self.work / "runs" / self.run / "server_binding.json"
        self.args = dict(
            binding_file=self.binding_file, run_id=self.run,
            server_label="Selected host", device_id="device-1", link_id="link-1",
            video_root=self.video, logo_root=self.logo,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            binding.cmd_bind(argparse.Namespace(**self.args))
        self.state = self.work / "runs" / self.run / "state.json"
        init = argparse.Namespace(**{k: v for k, v in self.args.items() if k != "server_label"},
                                   workflow_script=str(self.helper),
                                   workflow_args=["--", "init", "--state", str(self.state), "--run-id", self.run,
                                                  "--server-label", "Selected host"])
        with contextlib.redirect_stdout(io.StringIO()):
            binding.cmd_run_workflow(init)

    def command(self, phase="preflight", step=None, item_id=None, write=None):
        dst = write or (self.work / "should-not-exist.txt")
        payload = f"from pathlib import Path; Path({str(dst)!r}).write_text('UNEXPECTED')"
        return argparse.Namespace(**{k: v for k, v in self.args.items() if k != "server_label"},
                                  phase=phase, step=step, item_id=item_id, cwd=str(self.work),
                                  read_path=[], write_path=[str(dst)],
                                  command=[sys.executable, "-c", payload])

    def test_shell_blocked_before_plan_approval(self):
        dest = self.work / "should-not-exist.txt"
        with self.assertRaisesRegex(ValueError, "PREFLIGHT_NOT_RUNNING"):
            binding.cmd_run_command(self.command(write=dest))
        self.assertFalse(dest.exists())

    def test_step_command_cannot_run_without_approval(self):
        dest = self.work / "not-authorized.txt"
        with self.assertRaisesRegex(ValueError, "WRONG_CURRENT_STEP"):
            binding.cmd_run_command(self.command(phase="step", step=1, write=dest))
        self.assertFalse(dest.exists())

    def test_remote_account_is_still_locked(self):
        cmd = self.command()
        cmd.link_id = "different-connection"
        with self.assertRaisesRegex(ValueError, "link_id mismatch"):
            binding.cmd_run_command(cmd)

    def test_sandbox_failure_never_falls_back_to_native_subprocess(self):
        # The original audit demonstrated a command ran without state approval.
        # This test exercises strict fail-closed sandbox selection independently.
        with patch.object(binding.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(RuntimeError, "OS_WRITE_SANDBOX_UNAVAILABLE"):
                binding.trusted_bwrap()
        with patch.object(binding.platform, "system", return_value="Linux"), patch.object(binding.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "OS_WRITE_SANDBOX_UNAVAILABLE"):
                binding.trusted_bwrap()


if __name__ == "__main__":
    unittest.main()
