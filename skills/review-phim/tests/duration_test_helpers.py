"""Deterministic test fixtures for review duration/plot coverage gates."""
from pathlib import Path
import json
import hashlib
import wave


def asset_fixture(work: Path, run_id: str = "run-test", target_sec: int = 600,
                  source_sec: int = 3600, rate_wpm: int = 120, miss: str | None = None):
    work.mkdir(parents=True, exist_ok=True)
    titles = [
        'Tại bến cảng người dẫn đầu phát hiện dấu vết bất ngờ',
        'Sau cuộc họp bí mật nhân vật chính thay đổi quyết định',
        'Người đồng hành tìm thấy manh mối dẫn tới vụ việc',
        'Ở hồi kết bằng chứng được công bố trước toàn bộ nhóm',
    ]
    events = []
    proof = []
    for i, phrase in enumerate(titles):
        event_id = f'event-{i+1}'
        events.append({'id':event_id,'phase':['mở đầu','phát triển','cao trào','kết'][i],
                       'required':True, 'summary':f'Tình tiết quan trọng thứ {i+1}: {phrase} cho thấy nguyên nhân và hậu quả',
                       'source_start_sec':int(i * source_sec / len(titles))})
        proof.append({'event_id':event_id, 'status':'covered', 'quote':phrase})
    if miss:
        proof = [e for e in proof if e['event_id'] != miss]
    dossier = {'run_id':run_id,'source_duration_sec':source_sec,'events':events}
    dossier_file = work/'story_events.json'
    dossier_file.write_text(json.dumps(dossier,ensure_ascii=False),encoding='utf-8')
    target_tokens = round(target_sec * rate_wpm / 60)
    # Repeated neutral technical filler serves only as a deterministic length test;
    # real story accuracy must be reviewed by a person/model against source evidence.
    filler = 'Diễn biến này làm thay đổi sự lựa chọn của các nhân vật và dẫn tới tình tiết mới.'
    text = (' '.join(titles) + ' ' + ((filler+' ')*1000)).split()
    script = ' '.join(text[:target_tokens])
    script_file = work/'review_script_v2.txt'
    script_file.write_text(script,encoding='utf-8')
    coverage_file = work/'event_coverage.json'
    coverage_file.write_text(json.dumps({'run_id':run_id,'events':proof},ensure_ascii=False),encoding='utf-8')
    plan = {'run_id':run_id,'target_source':'story_derived','target_duration_sec':target_sec,
            'estimated_tts_wpm':rate_wpm,'rationale':'Phân bổ theo từng biến cố quan trọng, độ dài phim, cao trào và diễn biến cần giữ đầy đủ.',
            'dossier_sha256':hashlib.sha256(dossier_file.read_bytes()).hexdigest(),
            'sections':[{'name':'mở đầu','duration_sec':target_sec/5},
                        {'name':'phát triển','duration_sec':target_sec*3/5},
                        {'name':'cao trào và kết','duration_sec':target_sec/5}]}
    plan_file = work/'editorial_duration_plan.json'
    plan_file.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
    return {'dossier':str(dossier_file),'plan':str(plan_file),'script':str(script_file),
            'coverage':str(coverage_file)}


def make_pcm_wav(path: Path, seconds: float, rate: int = 8000):
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.writeframes(b'\x80' * int(seconds * rate))
    return path
