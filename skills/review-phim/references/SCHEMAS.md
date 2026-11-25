# Hợp đồng dữ liệu — mọi file nằm trong thư mục phim đã chọn

Tất cả JSON UTF-8. Không ghi credential, token, mật khẩu hoặc ID phiên.

## 1. Phạm vi đường dẫn
- `video_root`: đường dẫn `VIDEO_ROOT` do người dùng chọn; là write-root duy nhất.
- `logo_root`: đường dẫn `LOGO_ROOT` do người dùng chọn; read-only, hoặc `null` khi người dùng xác nhận không dùng logo.
- `run_workspace`: `VIDEO_ROOT/.review-phim/runs/<run_id>/`.
- `runtime_root`: `VIDEO_ROOT/.review-phim/runtime/`.
- Mọi `state.json`, manifest, log, evidence, cache, temp, model, venv, portable tool và artefact phải nằm dưới `VIDEO_ROOT`.
- Không có output nào được phép nằm trong `LOGO_ROOT` hoặc ngoài `VIDEO_ROOT`.

## 2. Manifest đầu vào
`inputs.json` trong run workspace ghi: `run_id`, `server_label`, `video_root`, `logo_root`, `source_video_path`, `selected_logo_path`, fingerprint video/logo, thời điểm xác minh và yêu cầu hiện tại. Video/logo gốc chỉ đọc. Không tự tìm input từ lần trước.

## 3. Báo cáo môi trường và kế hoạch cài đặt
`environment_report.json` và `installation_plan.json` phải nằm trong run workspace. Báo cáo môi trường ghi OS, CPU, RAM, GPU/VRAM, driver, dung lượng trống của volume chứa VIDEO_ROOT, Python, FFmpeg/FFprobe, thư viện/model/engine, version, trạng thái và smoke-test. Không dùng profile cũ làm bằng chứng.

`installation_plan.json` có `items` theo thứ tự; mỗi item ghi id, name, target_path dưới VIDEO_ROOT, status, log/evidence. Không cài global. Không cần một điểm dừng duyệt plan riêng cho cài đặt local an toàn đã được yêu cầu; nếu cần thao tác ngoài phạm vi hoặc có rủi ro thì BLOCKED và xin hướng xử lý.

## 4. Artefact chính
| Giai đoạn | Tệp gợi ý trong run workspace |
|---|---|
| Preflight | environment_report.json, installation_plan.json, install_log/, smoke_tests/, state.json |
| 1 | inputs.json, source_probe.json, workspace_report.json |
| 2 | asr/transcript_source.json, transcript_vi.json, TXT/SRT/VTT |
| 3 | frames/index.json, observations batches, visual_transcript_timeline.json |
| 4 | understanding/flagged_ranges.json, retries/, evidence_sheets/, film_understanding_verified.md |
| 5 | script/review_script_v1.txt, review_script_v2.txt, audit và sources.json |
| 6 | voice_selection.json, tts/segments/*.wav, narration_final.wav, narration_timeline.json |
| 7 | timeline/narration_units.json, scene_database.json, scene_matching.json, video_timeline_draft.json |
| 8 | preview/preview_v1.mp4, sheets/, visual_cut_review.csv, changes.json, preview_v2.mp4 |
| 9 | postproduction/subtitle_cues.json, narration_vi.srt/.ass, audio stems, audio_report.json |
| 10 | delivery/review_final.mp4, review_final_logo.mp4, render_report.json, SHA256 |
| 11 | youtube/title.txt, description.txt, hashtags.txt, thumbnail.png nếu tạo, delivery_manifest.json |

## 5. State của một lượt
`state.json` nằm trong run workspace. Mỗi lần gọi Production tạo `run_id` và state mới; không có auto-resume. Chỉ `pass` và `skipped` hợp lệ là hoàn tất; `partial`, `blocked`, `stale`, `running` khóa bước sau.

Preflight là cổng 0. Installation plan chạy theo thứ tự; từng thành phần phải RUNNING → cài → xác minh → PASS. Không cần duyệt plan lần nữa nếu tất cả cài đặt đều nằm trong VIDEO_ROOT và đã nằm trong yêu cầu. Nếu lỗi, BLOCKED.

Sau preflight, chỉ bước chưa hoàn tất đầu tiên được RUNNING. PASS yêu cầu evidence file nằm trong VIDEO_ROOT, có hash SHA-256 và note kiểm tra. BLOCKED phải có diagnosis, proposal, risk, verification criteria, evidence và repair attempts. Sau sửa, xác minh và chạy lại toàn bộ bước hiện tại trước khi PASS. Bước 21–40 khóa đến khi người dùng chọn giọng rõ ràng tại điểm dừng sau bước 20/QC3.

## 6. Timeline
```json
{"fps":"25/1","duration":4.0,"source_duration":120.0,"clips":[{"clip_id":1,"unit_id":1,"narration":"Lời kể.","review_start_frame":0,"review_end_frame":100,"source_start":20.0,"source_end":24.0,"speed":1.0,"transition":"cut","visual_observation":"Mô tả ảnh thực","evidence_frame_ids":[5],"flags":[]}]}
```
Frame end exclusive. Không coi helper timeline là bằng chứng nội dung khớp.

## 7. Báo cáo bàn giao
Kèm đường dẫn file đã kiểm tra (tất cả trong VIDEO_ROOT), duration/frame/codec/resolution/fps, audio/subtitle/logo, status 8 QC, phạm vi kiểm tra, lỗi/giới hạn, checksum và xác nhận phim gốc/logo gốc không bị thay đổi.
