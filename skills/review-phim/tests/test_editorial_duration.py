"""Regressions for film-specific script timing and evidence-linked review coverage."""
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path

from duration_test_helpers import asset_fixture, make_pcm_wav

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'workflow_state.py'
spec = importlib.util.spec_from_file_location('review_phim_editorial_workflow', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EditorialDurationTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.root = Path(self.t.name)
        self.video = self.root / 'video'
        self.work = self.video / 'WORKSPACE'
        self.work.mkdir(parents=True)
        self.run = self.work / 'runs' / 'audit-1'
        self.run.mkdir(parents=True)
        self.data = {'run_id':'audit-1','video_root':str(self.video), 'qc_gates':{}}
        self.paths = asset_fixture(self.run,'audit-1')

    def tearDown(self):
        self.t.cleanup()

    def get(self, name):
        return Path(self.paths[name])

    def test_film_specific_duration_plan_can_pass_ten_minutes(self):
        report = mod.audit_review_script(self.data, self.paths)
        self.assertEqual(report['target_duration_sec'],600)
        self.assertGreaterEqual(report['word_count_whitespace'],1100)
        self.assertEqual(report['required_events'],4)

    def test_custom_twenty_minute_review_not_truncated_to_eight(self):
        paths = asset_fixture(self.run,'audit-1',target_sec=1200)
        report = mod.audit_review_script(self.data, paths)
        self.assertEqual(report['target_duration_sec'],1200)
        self.assertGreater(report['estimated_duration_sec'], 1000)

    def test_qc3_blocks_eight_minute_script_when_plan_is_twenty(self):
        paths=asset_fixture(self.run,'audit-1',target_sec=1200)
        script=Path(paths['script'])
        script.write_text(' '.join(script.read_text(encoding='utf-8').split()[:960]),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'QC3_SCRIPT_TOO_SHORT_FOR_TARGET'):
            mod.audit_review_script(self.data, paths)

    def test_qc3_blocks_missing_required_plot_event(self):
        paths=asset_fixture(self.run,'audit-1',miss='event-3')
        with self.assertRaisesRegex(ValueError,'QC3_REQUIRED_PLOT_GAP'):
            mod.audit_review_script(self.data, paths)

    def test_qc3_blocks_fabricated_quote(self):
        coverage=json.loads(self.get('coverage').read_text(encoding='utf-8'))
        coverage['events'][0]['quote']='Một sự kiện không hề xuất hiện trong kịch bản V2 do AI tự khai'
        self.get('coverage').write_text(json.dumps(coverage,ensure_ascii=False),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'QC3_COVERAGE_QUOTE_UNVERIFIED'):
            mod.audit_review_script(self.data, self.paths)

    def test_qc3_requires_source_film_events_at_feature_length(self):
        dossier=json.loads(self.get('dossier').read_text(encoding='utf-8'))
        dossier['source_duration_sec']=7200
        dossier['events']=dossier['events'][:3]
        self.get('dossier').write_text(json.dumps(dossier,ensure_ascii=False),encoding='utf-8')
        plan=json.loads(self.get('plan').read_text(encoding='utf-8'))
        plan['dossier_sha256']=mod.sha256(self.get('dossier'))
        self.get('plan').write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'QC3_DOSSIER_UNDERINDEXED'):
            mod.audit_review_script(self.data, self.paths)

    def test_qc3_rejects_tampered_script_after_approval(self):
        self.data['qc_gates']['3']={'editorial_audit':mod.audit_review_script(self.data,self.paths)}
        mod.verify_editorial_audit(self.data)
        self.get('script').write_text(self.get('script').read_text(encoding='utf-8')+' khác',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'QC3_EDITORIAL_SOURCE_CHANGED'):
            mod.verify_editorial_audit(self.data)

    def test_qc4_measures_actual_wav_and_refuses_short_audio(self):
        self.data['qc_gates']['3']={'editorial_audit':mod.audit_review_script(self.data,self.paths)}
        wav=make_pcm_wav(self.run/'narration_final.wav', 480)
        audio=mod.audit_tts_master(self.data,{'master_wav':str(wav)})
        self.assertEqual(audio['actual_duration_sec'],480)
        make_pcm_wav(wav, 420)
        with self.assertRaisesRegex(ValueError,'QC4_TTS_DURATION_MISMATCH'):
            mod.audit_tts_master(self.data,{'master_wav':str(wav)})

    def test_qc4_and_downstream_detect_audio_modified(self):
        self.data['qc_gates']['3']={'editorial_audit':mod.audit_review_script(self.data,self.paths)}
        wav=make_pcm_wav(self.run/'narration_final.wav', 605)
        report=mod.audit_tts_master(self.data,{'master_wav':str(wav)})
        self.data['qc_gates']['4']={'tts_duration_audit':report}
        mod.verify_tts_master(self.data)
        make_pcm_wav(wav, 608)
        with self.assertRaisesRegex(ValueError,'QC4_TTS_AUDIO_CHANGED'):
            mod.verify_tts_master(self.data)

    def test_editorial_files_outside_bound_run_rejected(self):
        self.paths['script']=str(self.root/'unbound_review.txt')
        (self.root/'unbound_review.txt').write_text('fake',encoding='utf-8')
        with self.assertRaises(ValueError):
            mod.audit_review_script(self.data,self.paths)

if __name__=='__main__':
    unittest.main()
