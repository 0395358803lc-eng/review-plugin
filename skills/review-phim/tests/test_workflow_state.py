import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "workflow_state.py"
spec = importlib.util.spec_from_file_location("review_phim_workflow_state", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WorkflowStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.video = self.base / "videos"
        self.logo = self.base / "logos"
        self.video.mkdir(); self.logo.mkdir()
        self.work = self.video / ".review-phim" / "runs" / "run-test"
        self.work.mkdir(parents=True)
        self.state = self.work / "state.json"
        self.ev = self.work / "evidence.txt"
        self.ev.write_text("evidence", encoding="utf-8")
        self.binding = {
            "remote_device_id": "device-selected-A",
            "remote_link_id": "link-selected-A",
            "expected_server_fingerprint": mod.machine_fingerprint(),
            "video_root": self.video,
            "logo_root": self.logo,
        }
        self.call(mod.cmd_init, state=self.state, server_label="Selected Server A", run_id="run-test", **self.binding)

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, fn, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(argparse.Namespace(**kwargs))

    def context(self, **overrides):
        values = {"state": self.state, **self.binding}
        values.update(overrides)
        return values

    def mark(self, step, status, evidence=None, note="test", approved_skip=False, **overrides):
        args = self.context(**overrides)
        args.update(step=step, status=status, evidence=[Path(x) for x in (evidence or [])], note=note, approved_skip=approved_skip)
        return self.call(mod.cmd_mark, **args)

    def start_preflight(self, items=None):
        self.mark(0, "running")
        plan = self.work / "installation_plan.json"
        plan.write_text(json.dumps({"items": items or []}), encoding="utf-8")
        self.call(mod.cmd_set_plan, **self.context(plan_file=plan))
        for item in items or []:
            self.call(mod.cmd_install_mark, **self.context(item_id=item["id"], status="running", note="install", evidence=[]))
            self.call(mod.cmd_install_mark, **self.context(item_id=item["id"], status="pass", note="verified", evidence=[self.ev]))
        self.mark(0, "pass", evidence=[self.ev])

    def test_state_and_evidence_must_stay_inside_video_root(self):
        with self.assertRaises(ValueError):
            self.call(mod.cmd_init, state=self.base / "outside.json", server_label="x", run_id="bad-run", **self.binding)
        outside = self.base / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            mod.evidence_records([outside], self.video)
        logo_file = self.logo / "logo.png"
        logo_file.write_text("logo", encoding="utf-8")
        with self.assertRaises(ValueError):
            mod.evidence_records([logo_file], self.video)

    def test_logo_and_video_roots_cannot_overlap(self):
        with self.assertRaises(ValueError):
            self.call(mod.cmd_init, state=self.work / "bad.json", server_label="x",
                      remote_device_id="device-selected-A", remote_link_id="link-selected-A",
                      video_root=self.video, logo_root=self.video)

    def test_every_command_is_bound_to_exact_device_link_and_roots(self):
        with self.assertRaisesRegex(RuntimeError, "REMOTE_DEVICE_MISMATCH"):
            mod.state_path(argparse.Namespace(**self.context(remote_device_id="device-other")))
        with self.assertRaisesRegex(RuntimeError, "REMOTE_LINK_MISMATCH"):
            mod.state_path(argparse.Namespace(**self.context(remote_link_id="link-other")))
        with self.assertRaisesRegex(RuntimeError, "SERVER_FINGERPRINT_MISMATCH"):
            mod.state_path(argparse.Namespace(**self.context(expected_server_fingerprint="wrong-fingerprint")))
        with self.assertRaisesRegex(RuntimeError, "VIDEO_ROOT_MISMATCH"):
            mod.state_path(argparse.Namespace(**self.context(video_root=self.base)))
        other_logo = self.base / "other-logos"
        other_logo.mkdir()
        with self.assertRaisesRegex(RuntimeError, "LOGO_ROOT_MISMATCH"):
            mod.state_path(argparse.Namespace(**self.context(logo_root=other_logo)))

    def test_machine_fingerprint_mismatch_blocks_run(self):
        data = json.loads(self.state.read_text(encoding="utf-8"))
        data["server_fingerprint"] = "sha256:wrong-machine"
        self.state.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "SERVER_BINDING_MISMATCH"):
            mod.load_state(self.state)

    def test_folder_identity_change_blocks_run(self):
        data = json.loads(self.state.read_text(encoding="utf-8"))
        data["video_root_identity"]["inode"] += 1
        self.state.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "VIDEO_ROOT_IDENTITY_MISMATCH"):
            mod.load_state(self.state)

    def test_binding_manifest_is_required_and_immutable(self):
        manifest = self.work / "binding.json"
        self.assertTrue(manifest.is_file())
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["remote_device_id"] = "device-other"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "BINDING_MANIFEST_MISMATCH"):
            mod.load_state(self.state)

    def test_installation_items_must_be_sequential(self):
        self.mark(0, "running")
        plan = self.work / "plan.json"
        plan.write_text(json.dumps({"items": [{"id": "python", "name": "Python venv"}, {"id": "ffmpeg", "name": "FFmpeg"}]}), encoding="utf-8")
        self.call(mod.cmd_set_plan, **self.context(plan_file=plan))
        with self.assertRaises(ValueError):
            self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="running", note="wrong", evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="python", status="running", note="install", evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="python", status="pass", note="ok", evidence=[self.ev]))
        self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="running", note="install", evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="pass", note="ok", evidence=[self.ev]))
        self.mark(0, "pass", evidence=[self.ev])

    def test_workflow_steps_are_sequential(self):
        self.start_preflight()
        with self.assertRaises(ValueError):
            self.mark(2, "running")
        self.mark(1, "running")
        self.mark(1, "pass", evidence=[self.ev])
        self.mark(2, "running")

    def test_blocker_requires_repair_and_retest_before_next_step(self):
        self.start_preflight()
        self.mark(1, "running")
        self.call(mod.cmd_block, **self.context(step=1, install_item_id=None, error_code="TEST", symptom="failed", diagnosis="cause", proposal="repair inside video root", alternatives=[], risk="low", verification="rerun test", approval_required=False, evidence=[self.ev]))
        with self.assertRaises(ValueError):
            self.mark(2, "running")
        self.call(mod.cmd_repair, **self.context(step=1, action="repair", note="done", evidence=[self.ev]))
        self.call(mod.cmd_resolve, **self.context(step=1, verification_evidence=self.ev, note="verified", user_approved=False))
        self.mark(1, "pass", evidence=[self.ev])
        self.mark(2, "running")

    def test_voice_gate_blocks_step_21(self):
        self.start_preflight()
        for step in range(1, 21):
            self.mark(step, "running")
            self.mark(step, "pass", evidence=[self.ev])
        with self.assertRaises(ValueError):
            self.mark(21, "running")
        self.call(mod.cmd_select_voice, **self.context(voice="Voice A", engine="VieNeu-TTS", evidence=self.ev, note="chosen", user_confirmed=True))
        self.mark(21, "running")

    def test_no_overwrite_or_resume(self):
        with self.assertRaises(FileExistsError):
            self.call(mod.cmd_init, state=self.state, server_label="Selected Server A", run_id="run-test", **self.binding)
        with self.assertRaises(SystemExit):
            mod.build_parser().parse_args(["resume", "--state", str(self.state)])


if __name__ == "__main__":
    unittest.main()
