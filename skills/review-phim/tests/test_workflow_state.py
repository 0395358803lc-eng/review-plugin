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
        self.video.mkdir(); self.logo.mkdir(); (self.video / "WORKSPACE").mkdir()
        self.work = self.video / "WORKSPACE" / "runs" / "run-test"
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

    def approve_install_plan(self):
        data = mod.load_state(self.state)
        digest = data["preflight"]["installation_plan"]["plan_sha256"]
        self.call(mod.cmd_approve_install_plan, **self.context(plan_sha256=digest, user_approved=True))

    def approve_step(self, step):
        self.call(mod.cmd_approve_step, **self.context(step=step, user_approved=True))

    def start_preflight(self, items=None):
        self.mark(0, "running")
        plan = self.work / "installation_plan.json"
        plan.write_text(json.dumps({"items": items or []}), encoding="utf-8")
        self.call(mod.cmd_set_plan, **self.context(plan_file=plan))
        self.approve_install_plan()
        for item in items or []:
            self.call(mod.cmd_install_mark, **self.context(item_id=item["id"], status="running", note="install", evidence=[]))
            self.call(mod.cmd_install_mark, **self.context(item_id=item["id"], status="pass", note="verified", evidence=[self.ev]))
        self.mark(0, "pass", evidence=[self.ev])

    def qc_pass(self, step):
        gate = mod.QC_GATES[step]
        report = self.work / f"QC{gate}.json"
        report.write_text(json.dumps({
            "run_id": "run-test", "gate": gate, "step": step, "status": "pass",
            "checks": [
                {"id": "coverage", "method": "coverage_count_checked", "passed": True},
                {"id": "integrity", "method": "file_checksum_checked", "passed": True},
            ],
            "evidence_paths": [str(self.ev)],
        }), encoding="utf-8")
        self.call(mod.cmd_qc_mark, **self.context(gate=gate, report=report))
        return report

    def test_evidence_at_film_root_is_rejected(self):
        outside_work = self.video / "original-source.mp4"
        outside_work.write_bytes(b"source")
        with self.assertRaises(ValueError):
            mod.evidence_records([outside_work], self.video)

    def test_install_target_must_stay_in_workspace(self):
        self.mark(0, "running")
        plan = self.work / "bad_plan.json"
        plan.write_text(json.dumps({"items": [{"id": "x", "name": "tool", "target_path": str(self.video / "bad_tool") }]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call(mod.cmd_set_plan, **self.context(plan_file=plan))

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
        with self.assertRaisesRegex(ValueError, "INSTALL_PLAN_NOT_APPROVED"):
            self.call(mod.cmd_install_mark, **self.context(item_id="python", status="running", note="without approval", evidence=[]))
        with self.assertRaises(ValueError):
            self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="running", note="wrong", evidence=[]))
        self.approve_install_plan()
        self.call(mod.cmd_install_mark, **self.context(item_id="python", status="running", note="install", evidence=[]))
        with self.assertRaisesRegex(ValueError, "duplicate install process"):
            self.call(mod.cmd_install_mark, **self.context(item_id="python", status="running", note="duplicate", evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="python", status="pass", note="ok", evidence=[self.ev]))
        self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="running", note="install", evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="pass", note="ok", evidence=[self.ev]))
        self.mark(0, "pass", evidence=[self.ev])

    def test_workflow_steps_are_sequential(self):
        self.start_preflight()
        with self.assertRaises(ValueError):
            self.mark(1, "running")
        self.approve_step(1)
        self.mark(1, "running")
        with self.assertRaisesRegex(ValueError, "must not be launched twice"):
            self.mark(1, "running")
        self.mark(1, "pass", evidence=[self.ev])
        with self.assertRaises(ValueError):
            self.mark(2, "running")
        with self.assertRaises(ValueError):
            self.approve_step(3)
        self.approve_step(2)
        self.mark(2, "running")

    def test_blocker_requires_repair_and_retest_before_next_step(self):
        self.start_preflight()
        self.approve_step(1)
        self.mark(1, "running")
        self.call(mod.cmd_block, **self.context(step=1, install_item_id=None, error_code="TEST", symptom="failed", diagnosis="cause", proposal="repair inside video root", alternatives=[], risk="low", verification="rerun test", approval_required=False, evidence=[self.ev]))
        with self.assertRaises(ValueError):
            self.mark(2, "running")
        self.call(mod.cmd_repair, **self.context(step=1, action="repair", note="done", evidence=[self.ev]))
        self.call(mod.cmd_resolve, **self.context(step=1, verification_evidence=self.ev, note="verified", user_approved=False))
        self.mark(1, "pass", evidence=[self.ev])
        self.approve_step(2)
        self.mark(2, "running")

    def test_voice_gate_blocks_step_21(self):
        self.start_preflight()
        for step in range(1, 21):
            self.approve_step(step)
            self.mark(step, "running")
            if step in mod.QC_GATES:
                self.qc_pass(step)
            self.mark(step, "pass", evidence=[self.ev])
        with self.assertRaises(ValueError):
            self.approve_step(21)
        with self.assertRaises(ValueError):
            self.mark(21, "running")
        self.call(mod.cmd_select_voice, **self.context(voice="Voice A", engine="VieNeu-TTS", evidence=self.ev, note="chosen", user_confirmed=True))
        with self.assertRaises(ValueError):
            self.mark(21, "running")
        self.approve_step(21)
        self.mark(21, "running")

    def test_install_plan_approval_is_bound_to_exact_hash_and_can_be_invalidated_before_install(self):
        self.mark(0, "running")
        plan = self.work / "plan.json"
        plan.write_text(json.dumps({"items": [{"id": "ffmpeg", "name": "FFmpeg", "version": "7.1", "target_path": str(self.video / "WORKSPACE" / "tools" / "ffmpeg"), "estimated_size_bytes": 1234}]}), encoding="utf-8")
        self.call(mod.cmd_set_plan, **self.context(plan_file=plan))
        old_hash = mod.load_state(self.state)["preflight"]["installation_plan"]["plan_sha256"]
        with self.assertRaises(ValueError):
            self.call(mod.cmd_approve_install_plan, **self.context(plan_sha256="wrong", user_approved=True))
        self.call(mod.cmd_approve_install_plan, **self.context(plan_sha256=old_hash, user_approved=True))
        plan.write_text(json.dumps({"items": [{"id": "ffmpeg", "name": "FFmpeg", "version": "7.2", "target_path": str(self.video / "WORKSPACE" / "tools" / "ffmpeg"), "estimated_size_bytes": 5678}]}), encoding="utf-8")
        self.call(mod.cmd_set_plan, **self.context(plan_file=plan))
        new_data = mod.load_state(self.state)
        self.assertNotEqual(old_hash, new_data["preflight"]["installation_plan"]["plan_sha256"])
        self.assertEqual(new_data["preflight"]["installation_plan"]["approval"]["status"], "pending")
        with self.assertRaisesRegex(ValueError, "INSTALL_PLAN_NOT_APPROVED"):
            self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="running", note="stale approval", evidence=[]))

    def test_already_present_installation_item_is_not_reinstalled(self):
        self.mark(0, "running")
        plan = self.work / "plan.json"
        plan.write_text(json.dumps({"items": [{"id": "python", "name": "Python venv", "already_present": True, "action": "already_present", "current_version": "3.13", "verification": "python --version"}, {"id": "ffmpeg", "name": "FFmpeg", "action": "install"}]}), encoding="utf-8")
        self.call(mod.cmd_set_plan, **self.context(plan_file=plan))
        data = mod.load_state(self.state)
        items = data["preflight"]["installation_plan"]["items"]
        self.assertEqual(items[0]["status"], "pending")  # No metadata-only auto-PASS.
        self.assertEqual(items[1]["status"], "pending")
        self.approve_install_plan()
        self.call(mod.cmd_install_mark, **self.context(item_id="python", status="running", note="verify installed Python", evidence=[]))
        with self.assertRaisesRegex(ValueError, "ALREADY_PRESENT_VERIFICATION_REQUIRED"):
            self.call(mod.cmd_install_mark, **self.context(item_id="python", status="pass", note="no report", evidence=[self.ev]))
        report = self.work / "python_check.json"
        report.write_text(json.dumps({"item_id":"python", "status":"pass", "observed_version":"3.13", "checks":[{"method":"python --version", "passed":True}]}))
        self.call(mod.cmd_install_mark, **self.context(item_id="python", status="pass", note="verified", evidence=[self.ev], verification_report=report))
        self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="running", note="install", evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg", status="pass", note="verified", evidence=[self.ev]))
        self.mark(0, "pass", evidence=[self.ev])

    def test_approval_manifest_tampering_blocks_state(self):
        manifest = self.work / "approval_manifest.json"
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["binding"]["remote_device_id"] = "other-device"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "APPROVAL_MANIFEST_MISMATCH"):
            mod.load_state(self.state)

    def test_next_step_requires_separate_explicit_approval(self):
        self.start_preflight()
        self.assertEqual(mod.next_action(mod.load_state(self.state)), "approve_step_01")
        self.approve_step(1)
        self.mark(1, "running")
        self.mark(1, "pass", evidence=[self.ev])
        self.assertEqual(mod.next_action(mod.load_state(self.state)), "approve_step_02")

    def test_qc1_must_be_checked_before_step9_pass(self):
        self.start_preflight()
        for step in range(1, 10):
            self.approve_step(step)
            self.mark(step, "running")
            if step == 9:
                with self.assertRaisesRegex(ValueError, "QC1_REQUIRED"):
                    self.mark(step, "pass", evidence=[self.ev])
                self.qc_pass(step)
            self.mark(step, "pass", evidence=[self.ev])
        self.assertEqual(mod.current_step(mod.load_state(self.state)), 10)

    def test_qc_report_change_blocks_final_pass(self):
        self.start_preflight()
        for step in range(1, 10):
            self.approve_step(step)
            self.mark(step, "running")
            if step == 9:
                report = self.qc_pass(step)
                report.write_text("{}")
                with self.assertRaisesRegex(ValueError, "QC1_REPORT_CHANGED"):
                    self.mark(step, "pass", evidence=[self.ev])
                return
            self.mark(step, "pass", evidence=[self.ev])

    def test_cannot_skip_without_this_steps_approval(self):
        self.start_preflight()
        with self.assertRaisesRegex(ValueError, "SKIPPED requires this step's explicit approval"):
            self.mark(1, "skipped", evidence=[self.ev], note="not applicable", approved_skip=True)
        self.approve_step(1)
        self.mark(1, "skipped", evidence=[self.ev], note="user confirmed not applicable", approved_skip=True)
        self.assertEqual(mod.current_step(mod.load_state(self.state)), 2)

    def test_cannot_block_unapproved_step_or_recover_into_running(self):
        self.start_preflight()
        kw=dict(step=1,install_item_id=None,error_code="TEST",symptom="bad",diagnosis="error",proposal="repair",alternatives=[],risk="high",verification="test",approval_required=False,evidence=[self.ev])
        with self.assertRaisesRegex(ValueError, "BLOCK_REQUIRES_RUNNING_STEP"):
            self.call(mod.cmd_block, **self.context(**kw))
        self.approve_step(1)
        self.mark(1,"running")
        self.call(mod.cmd_block, **self.context(**kw))
        b=mod.load_state(self.state)["blocker"]
        self.assertTrue(b["approval_required"])
        with self.assertRaisesRegex(ValueError,"REPAIR_APPROVAL_REQUIRED"):
            self.call(mod.cmd_repair, **self.context(step=1, action="fix", note="done", evidence=[self.ev]))
        with self.assertRaisesRegex(ValueError,"REPAIR_APPROVAL_REQUIRED"):
            mod.validate_command_gate(mod.load_state(self.state), "repair", step=1)
        self.call(mod.cmd_approve_repair, **self.context(step=1,blocker_id=b["blocker_id"],user_approved=True))
        mod.validate_command_gate(mod.load_state(self.state), "repair", step=1)
        self.call(mod.cmd_repair, **self.context(step=1,action="fix",note="verified",evidence=[self.ev]))
        self.call(mod.cmd_resolve, **self.context(step=1,verification_evidence=self.ev,note="retest",user_approved=False))
        self.assertEqual(mod.load_state(self.state)["steps"][0]["status"],"running")

    def test_install_plan_file_change_fails_closed(self):
        self.mark(0,"running")
        p=self.work/"plan.json"
        p.write_text(json.dumps({"items":[{"id":"ffmpeg","name":"FFmpeg","version":"1.0"}]}))
        self.call(mod.cmd_set_plan, **self.context(plan_file=p))
        self.approve_install_plan()
        p.write_text(json.dumps({"items":[{"id":"ffmpeg","name":"FFmpeg","version":"999.0"}]}))
        with self.assertRaisesRegex(ValueError,"INSTALL_PLAN_FILE_CHANGED"):
            self.call(mod.cmd_install_mark, **self.context(item_id="ffmpeg",status="running",note="try",evidence=[]))
        with self.assertRaisesRegex(ValueError,"INSTALL_PLAN_FILE_CHANGED"):
            mod.validate_command_gate(mod.load_state(self.state), "install", item_id="ffmpeg")

    def test_can_amend_pending_install_without_restarting_run_and_preserves_done_prefix(self):
        self.mark(0,"running")
        p=self.work/"plan.json"
        p.write_text(json.dumps({"items":[{"id":"a","name":"A"},{"id":"b","name":"B"}]}))
        self.call(mod.cmd_set_plan, **self.context(plan_file=p))
        self.approve_install_plan()
        self.call(mod.cmd_install_mark, **self.context(item_id="a",status="running",note="install",evidence=[]))
        self.call(mod.cmd_install_mark, **self.context(item_id="a",status="pass",note="verified",evidence=[self.ev]))
        p.write_text(json.dumps({"items":[{"id":"a","name":"A"},{"id":"b","name":"B", "version":"2"},{"id":"c","name":"C"}]}))
        self.call(mod.cmd_set_plan, **self.context(plan_file=p))
        d=mod.load_state(self.state)
        self.assertEqual([i["status"] for i in d["preflight"]["installation_plan"]["items"]],["pass","pending","pending"])
        self.assertEqual(d["preflight"]["installation_plan"]["approval"]["status"],"pending")
        with self.assertRaisesRegex(ValueError,"INSTALL_PLAN_NOT_APPROVED"):
            self.call(mod.cmd_install_mark, **self.context(item_id="b",status="running",note="try",evidence=[]))
        self.approve_install_plan()
        self.call(mod.cmd_install_mark, **self.context(item_id="b",status="running",note="approved",evidence=[]))

    def test_exec_requires_approved_running_state(self):
        self.mark(0,"running")
        with self.assertRaises(ValueError):
            mod.validate_command_gate(mod.load_state(self.state),"install",item_id="ffmpeg")
        self.start_preflight if False else None

    def test_no_overwrite_or_resume(self):
        with self.assertRaises(FileExistsError):
            self.call(mod.cmd_init, state=self.state, server_label="Selected Server A", run_id="run-test", **self.binding)
        with self.assertRaises(SystemExit):
            mod.build_parser().parse_args(["resume", "--state", str(self.state)])


if __name__ == "__main__":
    unittest.main()
