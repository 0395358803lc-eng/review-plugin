import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util
import argparse
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "server_binding.py"
spec = importlib.util.spec_from_file_location("review_phim_server_binding", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ServerBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "video"
        self.logo = self.root / "logo"
        self.video.mkdir()
        self.logo.mkdir()
        self.run_id = "run-test-001"
        self.device_id = "device-exact-001"
        self.link_id = "link-exact-001"
        self.binding = self.video / "WORKSPACE" / "runs" / self.run_id / "server_binding.json"
        self.identity = {
            "system": "TestOS", "release": "1", "machine": "x86_64",
            "hostname": "selected-host", "fingerprint": "a" * 64,
        }
        self.identity_patch = patch.object(mod, "machine_identity", return_value=self.identity)
        self.identity_patch.start()
        self.addCleanup(self.identity_patch.stop)
        self.bind()

    def tearDown(self):
        self.tmp.cleanup()

    def run_quiet(self, fn, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(args)

    def bind(self):
        args = argparse.Namespace(
            binding_file=self.binding, run_id=self.run_id, server_label="Server A",
            device_id=self.device_id, link_id=self.link_id,
            video_root=self.video, logo_root=self.logo,
        )
        self.run_quiet(mod.cmd_bind, args)

    def verify(self, **changes):
        values = dict(
            binding_file=self.binding, run_id=self.run_id,
            device_id=self.device_id, link_id=self.link_id,
            video_root=self.video, logo_root=self.logo,
            write_path=[], read_path=[], cwd=str(self.video / "WORKSPACE"),
        )
        values.update(changes)
        return self.run_quiet(mod.cmd_verify, argparse.Namespace(**values))

    def test_workspace_created_automatically_after_folder_selection(self):
        work = self.video / "WORKSPACE"
        self.assertTrue(work.is_dir())
        self.assertTrue(self.binding.is_file())
        self.assertEqual(json.loads(self.binding.read_text(encoding="utf-8"))["workspace_root"], str(work.resolve()))

    def test_workspace_replaced_at_same_path_is_blocked(self):
        original_work = self.video / "WORKSPACE"
        original_id = mod.path_id(original_work)
        other = self.video / "WORKSPACE-old"
        original_work.rename(other)
        original_work.mkdir()
        # Even a copied manifest must not authorize a replacement WORKSPACE.
        import shutil
        copied_binding = original_work / "runs" / self.run_id / "server_binding.json"
        copied_binding.parent.mkdir(parents=True)
        shutil.copy2(other / "runs" / self.run_id / "server_binding.json", copied_binding)
        self.assertNotEqual(original_id, mod.path_id(original_work))
        with self.assertRaisesRegex(ValueError, "WORKSPACE_IDENTITY_MISMATCH"):
            self.verify()

    def test_run_command_denies_non_workspace_output(self):
        args = argparse.Namespace(
            binding_file=self.binding, run_id=self.run_id,
            device_id=self.device_id, link_id=self.link_id,
            video_root=self.video, logo_root=self.logo,
            cwd=str(self.video / "WORKSPACE"),
            read_path=[], write_path=[str(self.video / "wrong_output.txt")],
            command=[sys.executable, "-c", "print('not allowed')"],
        )
        with self.assertRaisesRegex(ValueError, "Write target is outside"):
            self.run_quiet(mod.cmd_run_command, args)

    def test_cannot_write_to_film_root_outside_workspace(self):
        with self.assertRaisesRegex(ValueError, "Write target is outside"):
            self.verify(write_path=[str(self.video / "unauthorized.mp4")])
        with self.assertRaisesRegex(ValueError, "Working directory is outside"):
            self.verify(cwd=str(self.video))

    def test_symlink_workspace_is_blocked(self):
        other = self.root / "fake-workspace"
        other.mkdir()
        self.binding.unlink()
        import shutil
        shutil.rmtree(self.video / "WORKSPACE")
        try:
            (self.video / "WORKSPACE").symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink not supported")
        with self.assertRaisesRegex(ValueError, "WORKSPACE_LINK_FORBIDDEN"):
            self.bind()

    def test_exact_server_and_folder_binding_passes(self):
        self.verify(write_path=[str(self.video / "WORKSPACE" / "output.mp4")],
                    read_path=[str(self.video / "source.mp4"), str(self.logo / "logo.png")])
        data = json.loads(self.binding.read_text(encoding="utf-8"))
        self.assertEqual(data["device_id"], self.device_id)
        self.assertEqual(data["link_id"], self.link_id)
        self.assertEqual(data["video_root"], str(self.video.resolve()))
        self.assertEqual(data["logo_root"], str(self.logo.resolve()))

    def test_wrong_device_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "deviceId mismatch"):
            self.verify(device_id="device-B")

    def test_wrong_account_link_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "link_id mismatch"):
            self.verify(link_id="another-account")

    def test_wrong_machine_fingerprint_is_rejected(self):
        with patch.object(mod, "machine_identity", return_value={**self.identity, "fingerprint": "b" * 64}):
            with self.assertRaisesRegex(ValueError, "machine fingerprint mismatch"):
                self.verify()

    def test_changed_video_or_logo_root_is_rejected(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises((ValueError, NotADirectoryError)):
            self.verify(video_root=other)
        other_logo = self.root / "other-logo"
        other_logo.mkdir()
        with self.assertRaisesRegex(ValueError, "LOGO_ROOT does not match"):
            self.verify(logo_root=other_logo)

    def test_recreated_folder_at_same_path_is_rejected(self):
        old_identity = mod.path_id(self.logo)
        backup = self.root / "logo-old"
        self.logo.rename(backup)
        self.logo.mkdir()
        self.assertNotEqual(mod.path_id(self.logo), old_identity)
        with self.assertRaisesRegex(ValueError, "folder identity fingerprint changed"):
            self.verify()

    def test_write_outside_video_root_is_rejected(self):
        outside = self.root / "outside.mp4"
        with self.assertRaisesRegex(ValueError, "Write target is outside"):
            self.verify(write_path=[str(outside)])

    def test_logo_root_is_read_only(self):
        with self.assertRaisesRegex(ValueError, "Write target is outside"):
            self.verify(write_path=[str(self.logo / "changed.png")])

    def test_read_outside_both_roots_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Read target is outside"):
            self.verify(read_path=[str(self.root / "other-file.txt")])

    def test_symlink_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.video / "WORKSPACE" / "escape"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation is unavailable")
        with self.assertRaisesRegex(ValueError, "Write target is outside"):
            self.verify(write_path=[str(link / "file.mp4")])

    def test_run_command_checks_server_and_all_declared_paths(self):
        source = self.video / "source.txt"
        source.write_text("input", encoding="utf-8")
        output = self.video / "WORKSPACE" / "runs" / self.run_id / "output.txt"
        code = "from pathlib import Path; Path(r'%s').write_text('ok', encoding='utf-8')" % output
        args = argparse.Namespace(
            binding_file=self.binding, run_id=self.run_id, device_id=self.device_id, link_id=self.link_id,
            video_root=self.video, logo_root=self.logo, cwd=str(self.video / "WORKSPACE"),
            read_path=[str(source)], write_path=[str(output)],
            command=[sys.executable, "-c", code],
        )
        args.phase="step";args.step=1;args.item_id=None
        with self.assertRaisesRegex(RuntimeError, "WORKFLOW_HELPER_MISSING"):
            self.run_quiet(mod.cmd_run_command, args)
        self.assertFalse(output.exists())
        args.write_path = [str(self.logo / "forbidden.txt")]
        with self.assertRaisesRegex(ValueError, "Write target is outside"):
            self.run_quiet(mod.cmd_run_command, args)

    def test_untrusted_or_missing_os_sandbox_blocks_process(self):
        with patch.object(mod.platform, "system", return_value="Windows"):
            with self.assertRaisesRegex(RuntimeError,"OS_WRITE_SANDBOX_UNAVAILABLE"):
                mod.trusted_bwrap()
        with patch.object(mod.platform, "system", return_value="Linux"), patch.object(mod.shutil,"which",return_value=None):
            with self.assertRaisesRegex(RuntimeError,"OS_WRITE_SANDBOX_UNAVAILABLE"):
                mod.trusted_bwrap()
        argv=mod.isolated_argv("/usr/bin/bwrap",self.video/"WORKSPACE",self.video/"WORKSPACE",["python","-V"])
        self.assertIn("--ro-bind",argv)
        self.assertIn("--bind",argv)
        self.assertEqual(argv[-2:],["python","-V"])

    def test_workflow_wrapper_injects_immutable_binding_arguments(self):
        original = ["status", "--state", str(self.video / "WORKSPACE" / "runs" / self.run_id / "state.json")]
        bound = mod.bind_workflow_arguments(original, mod.binding_projection(json.loads(self.binding.read_text(encoding="utf-8"))))
        self.assertIn("--remote-device-id", bound)
        self.assertIn(self.device_id, bound)
        self.assertIn("--remote-link-id", bound)
        self.assertIn(self.link_id, bound)
        self.assertIn("--expected-server-fingerprint", bound)

    def test_binding_cannot_be_overwritten(self):
        with self.assertRaises(FileExistsError):
            self.bind()

    def test_overlapping_roots_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlap"):
            mod.ensure_disjoint(self.video, self.video / "nested-logo")

    def test_guarded_workflow_binds_state_and_rejects_wrong_binding(self):
        helper = self.video / "WORKSPACE" / "tools" / "workflow_state.py"
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "args=sys.argv[1:]\n"
            "if args[0] == 'init':\n"
            "  state=Path(args[args.index('--state')+1])\n"
            "  video=Path(args[args.index('--video-root')+1])\n"
            "  logo=Path(args[args.index('--logo-root')+1]) if '--logo-root' in args else None\n"
            "  run=args[args.index('--run-id')+1]\n"
            "  device=args[args.index('--remote-device-id')+1]\n"
            "  link=args[args.index('--remote-link-id')+1]\n"
            "  fingerprint=args[args.index('--expected-server-fingerprint')+1]\n"
            "  state.parent.mkdir(parents=True, exist_ok=True)\n"
            "  state.write_text(json.dumps({'run_id':run,'video_root':str(video),'workspace_root':str(video/'WORKSPACE'),'logo_root':str(logo) if logo else None,'remote_device_id':device,'remote_link_id':link,'server_fingerprint':fingerprint}), encoding='utf-8')\n"
            "else:\n"
            "  print('status-ok')\n",
            encoding="utf-8",
        )
        state = self.video / "WORKSPACE" / "runs" / self.run_id / "state.json"
        args = argparse.Namespace(
            binding_file=self.binding, run_id=self.run_id,
            device_id=self.device_id, link_id=self.link_id,
            video_root=self.video, logo_root=self.logo,
            workflow_script=str(helper),
            workflow_args=[
                "--", "init", "--state", str(state), "--run-id", self.run_id,
                "--server-label", "Server A", "--video-root", str(self.video),
                "--logo-root", str(self.logo),
            ],
        )
        self.run_quiet(mod.cmd_run_workflow, args)
        saved = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(saved["server_binding"]["device_id"], self.device_id)
        self.assertEqual(saved["server_binding"]["link_id"], self.link_id)

        args.workflow_args = ["--", "status", "--state", str(state)]
        self.run_quiet(mod.cmd_run_workflow, args)

        saved["server_binding"]["device_id"] = "device-B"
        state.write_text(json.dumps(saved), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not bound to this exact server"):
            self.run_quiet(mod.cmd_run_workflow, args)

        args.workflow_script = str(self.root / "outside.py")
        with self.assertRaisesRegex(ValueError, "Workflow helper is outside"):
            self.run_quiet(mod.cmd_run_workflow, args)

    def test_approval_gates_are_enforced_through_server_binding_wrapper(self):
        workflow_script = Path(__file__).resolve().parents[1] / "scripts" / "workflow_state.py"
        target_script = self.video / "WORKSPACE" / "tools" / "workflow_state.py"
        target_script.parent.mkdir(parents=True, exist_ok=True)
        target_script.write_text(workflow_script.read_text(encoding="utf-8"), encoding="utf-8")
        stable_id = mod.stable_machine_id()
        real_fingerprint = __import__("hashlib").sha256("\n".join([
            __import__("platform").system(), __import__("platform").machine(), stable_id,
        ]).encode("utf-8")).hexdigest()
        actual_identity = {
            "system": __import__("platform").system(),
            "release": __import__("platform").release(),
            "machine": __import__("platform").machine(),
            "hostname": __import__("platform").node(),
            "fingerprint": real_fingerprint,
        }
        with patch.object(mod, "machine_identity", return_value=actual_identity):
            self.binding.unlink()
            self.bind()
            state = self.video / "WORKSPACE" / "runs" / self.run_id / "state.json"

            def invoke(*workflow_args):
                args = argparse.Namespace(
                    binding_file=self.binding, run_id=self.run_id, device_id=self.device_id, link_id=self.link_id,
                    video_root=self.video, logo_root=self.logo, workflow_script=str(target_script),
                    workflow_args=["--", *workflow_args],
                )
                return self.run_quiet(mod.cmd_run_workflow, args)

            invoke("init", "--state", str(state), "--server-label", "Server A", "--video-root", str(self.video),
                   "--logo-root", str(self.logo), "--run-id", self.run_id)
            evidence = state.parent / "evidence.txt"
            evidence.write_text("verified", encoding="utf-8")
            invoke("mark", "--state", str(state), "--step", "0", "--status", "running", "--note", "preflight start")
            plan_file = state.parent / "installation_plan.json"
            plan_file.write_text(json.dumps({"items": [{
                "id": "ffmpeg", "name": "FFmpeg", "version": "7.1",
                "target_path": str(self.video / "WORKSPACE" / "runtime" / "ffmpeg"),
                "estimated_size_bytes": 1234, "risk": "low", "verification": "ffmpeg -version",
            }]}), encoding="utf-8")
            invoke("set-install-plan", "--state", str(state), "--plan-file", str(plan_file))
            with self.assertRaises(SystemExit):
                invoke("install-mark", "--state", str(state), "--item-id", "ffmpeg", "--status", "running", "--note", "must be blocked")
            plan_hash = json.loads(state.read_text(encoding="utf-8"))["preflight"]["installation_plan"]["plan_sha256"]
            invoke("approve-install-plan", "--state", str(state), "--plan-sha256", plan_hash, "--user-approved")
            invoke("install-mark", "--state", str(state), "--item-id", "ffmpeg", "--status", "running", "--note", "install")
            invoke("install-mark", "--state", str(state), "--item-id", "ffmpeg", "--status", "pass", "--note", "verified", "--evidence", str(evidence))
            invoke("mark", "--state", str(state), "--step", "0", "--status", "pass", "--note", "preflight pass", "--evidence", str(evidence))
            with self.assertRaises(SystemExit):
                invoke("mark", "--state", str(state), "--step", "1", "--status", "running", "--note", "must wait for approval")
            invoke("approve-step", "--state", str(state), "--step", "1", "--user-approved")
            invoke("mark", "--state", str(state), "--step", "1", "--status", "running", "--note", "step 1")
            invoke("mark", "--state", str(state), "--step", "1", "--status", "pass", "--note", "step 1 pass", "--evidence", str(evidence))
            invoke("status", "--state", str(state))
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["step_approvals"]["1"]["status"], "consumed")
            approval_manifest = json.loads((state.parent / "approval_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(approval_manifest["step_approvals"]["1"]["status"], "consumed")

    def test_actual_workflow_state_runs_through_server_binding_gate(self):
        from pathlib import Path as P
        workflow_script = P(__file__).resolve().parents[1] / "scripts" / "workflow_state.py"
        target_script = self.video / "WORKSPACE" / "tools" / "workflow_state.py"
        target_script.parent.mkdir(parents=True, exist_ok=True)
        target_script.write_text(workflow_script.read_text(encoding="utf-8"), encoding="utf-8")
        real_fingerprint = __import__("hashlib").sha256("\n".join([
            __import__("platform").system(), __import__("platform").machine(),
            mod.stable_machine_id(),
        ]).encode("utf-8")).hexdigest()
        actual_identity = {
            "system": __import__("platform").system(),
            "release": __import__("platform").release(),
            "machine": __import__("platform").machine(),
            "hostname": __import__("platform").node(),
            "fingerprint": real_fingerprint,
        }
        with patch.object(mod, "machine_identity", return_value=actual_identity):
            self.binding.unlink()
            self.bind()
            state = self.video / "WORKSPACE" / "runs" / self.run_id / "state.json"
            init_args = argparse.Namespace(
                binding_file=self.binding, run_id=self.run_id, device_id=self.device_id, link_id=self.link_id,
                video_root=self.video, logo_root=self.logo, workflow_script=str(target_script),
                workflow_args=["--", "init", "--state", str(state), "--server-label", "Server A",
                               "--video-root", str(self.video), "--logo-root", str(self.logo), "--run-id", self.run_id],
            )
            self.run_quiet(mod.cmd_run_workflow, init_args)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["remote_device_id"], self.device_id)
            self.assertEqual(saved["remote_link_id"], self.link_id)
            self.assertEqual(saved["server_fingerprint"], real_fingerprint)
            self.assertEqual(saved["server_binding"]["device_id"], self.device_id)
            status_args = argparse.Namespace(**{**vars(init_args), "workflow_args": ["--", "status", "--state", str(state)]})
            self.run_quiet(mod.cmd_run_workflow, status_args)


if __name__ == "__main__":
    unittest.main()
