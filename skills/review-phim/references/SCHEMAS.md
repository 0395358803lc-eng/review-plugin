# Hợp đồng dữ liệu Review-Phim 1.2.8 — mọi file nằm trong thư mục phim đã chọn

Tất cả JSON UTF-8. WORKSPACE tự động được tạo trong thư mục phim sau khi chọn máy chủ, VIDEO_ROOT và LOGO_ROOT; không hỏi người dùng chọn nơi lưu. Không ghi credential, token, mật khẩu hoặc ID phiên.

## 1. Phạm vi đường dẫn
- `video_root`: đường dẫn `VIDEO_ROOT` do người dùng chọn; chỉ đọc phim nguồn. `VIDEO_ROOT/WORKSPACE` mới là write-root duy nhất.
- `logo_root`: đường dẫn `LOGO_ROOT` do người dùng chọn; read-only, hoặc `null` khi người dùng xác nhận không dùng logo.
- `workspace_root`: `VIDEO_ROOT/WORKSPACE`, auto-created after selecting server, VIDEO_ROOT, LOGO_ROOT; only write root.
- `run_workspace`: `VIDEO_ROOT/WORKSPACE/runs/<run_id>/`.
- `runtime_root`: `VIDEO_ROOT/WORKSPACE/runtime/`.
- Mọi `state.json`, `binding.json`, `approval_manifest.json`, manifest, log, evidence, cache, temp, model, venv, portable tool và artefact phải nằm dưới `VIDEO_ROOT/WORKSPACE`.
- Không output nào được phép nằm ngoài `VIDEO_ROOT/WORKSPACE`, kể cả gốc VIDEO_ROOT, LOGO_ROOT, Desktop hoặc đường dẫn symlink thoát WORKSPACE.

## 2. Manifest đầu vào
`inputs.json` trong run workspace ghi: `run_id`, `server_label`, `video_root`, `workspace_root`, `logo_root`, `source_video_path`, `selected_logo_path`, fingerprint video/logo, thời điểm xác minh và yêu cầu hiện tại. Video/logo gốc chỉ đọc. Không tự tìm input từ lần trước.

## 3. Báo cáo môi trường và kế hoạch cài đặt
`environment_report.json` và `installation_plan.json` phải nằm trong run workspace. Báo cáo môi trường ghi OS, CPU, RAM, GPU/VRAM, driver, dung lượng trống của volume chứa VIDEO_ROOT, Python, FFmpeg/FFprobe, thư viện/model/engine, version, trạng thái và smoke-test. Không dùng profile cũ làm bằng chứng.

`installation_plan.json` trong WORKSPACE/runs/<RUN_ID> có `items` theo thứ tự; mỗi item ghi tối thiểu `id`, `name`, `category`, `status`, `target_path`, `version`, `current_version`, `action`, `reason`, `source`, `estimated_size_bytes`, `estimated_duration_minutes`, `risk`, `verification`. Có thể bổ sung `description`, `estimated_download_bytes`, `already_present`, `required`, `license`, `notes`, `cache_path`. Đường dẫn target phải là absolute canonical path dưới VIDEO_ROOT/WORKSPACE. Không cài global.

`workflow_state.py set-install-plan` tạo `plan_snapshot` và `plan_sha256`. `approval_manifest.json` ghi `RUN_ID`, server/folder binding, plan snapshot/hash và trạng thái approval. Người dùng phải duyệt đúng hash trước khi bất kỳ mục nào được RUNNING. Nếu snapshot thay đổi, approval chuyển về PENDING và hash phải được duyệt lại.

## 4. Artefact chính
| Giai đoạn | Tệp gợi ý trong run workspace |
|---|---|
| Preflight | environment_report.json, installation_plan.json, approval_manifest.json, install_log/, smoke_tests/, state.json |
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

## 5. State và hợp đồng phê duyệt
`state.json` nằm trong run workspace. Schema version 9; `server_binding.json` schema 3. WORKSPACE có path và folder identity trong state/binding. Mỗi Production tạo `run_id` và state mới; không auto-resume state schema cũ.

### Preflight / danh mục cài đặt
- Preflight là cổng 0. Trước khi cài phải có `installation_plan.configured=true`, `plan_sha256` và `approval.status=approved` khớp hash.
- Lệnh `approve-install-plan` bắt buộc `--user-approved` và hash đang được hiển thị. Lệnh `install-mark --status running` bị chặn nếu chưa duyệt.
- Một lần duyệt mở khóa toàn bộ danh mục đã liệt kê; các package cài theo thứ tự từng mục và từng mục phải PASS với evidence. Không cần hỏi lại từng package.
- `cmd_mark step=0 status=pass` bị chặn nếu chưa duyệt plan, hash mismatch hoặc còn mục cài chưa PASS.

### Các bước sản xuất 01–40
- `step_approvals` lưu approval riêng cho từng bước: `step`, `status`, `approval_id`, `approved_at`, `approval_hash`, `consumed_at`.
- Bước hiện tại chỉ RUNNING sau `approve-step --step N --user-approved` và hash khớp binding cùng bằng chứng bước trước.
- Mỗi approval chỉ mở đúng một bước. Khi bước PASS, approval chuyển consumed; bước tiếp theo vẫn PENDING cho tới khi người dùng duyệt.
- Sau PASS, trạng thái `next_action` phải là `approve_step_NN`, trừ sau bước 20 là `select_voice`, và sau bước 40 là `run_complete`.
- Bước 21–40 khóa đến khi người dùng chọn giọng rõ ràng sau bước 20. Sau khi chọn giọng, vẫn phải duyệt bước 21 riêng.
- `approval_manifest.json` là audit mirror. Thiếu hoặc mismatch manifest phải BLOCKED; không tự tái tạo approval.

Chỉ `pass` và `skipped` hợp lệ là hoàn tất; `partial`, `blocked`, `stale`, `running` khóa bước sau. PASS yêu cầu evidence file trong VIDEO_ROOT/WORKSPACE, SHA-256 và note kiểm tra. BLOCKED phải có diagnosis, proposal, risk, verification criteria, evidence và repair attempts. Sau sửa, xác minh và chạy lại toàn bộ bước hiện tại trước khi mở approval cho bước sau.

## 6. Timeline
```json
{"fps":"25/1","duration":4.0,"source_duration":120.0,"clips":[{"clip_id":1,"unit_id":1,"narration":"Lời kể.","review_start_frame":0,"review_end_frame":100,"source_start":20.0,"source_end":24.0,"speed":1.0,"transition":"cut","visual_observation":"Mô tả ảnh thực","evidence_frame_ids":[5],"flags":[]}]}
```
Frame end exclusive. Không coi helper timeline là bằng chứng nội dung khớp.

## 7. Báo cáo bàn giao
Kèm đường dẫn file đã kiểm tra (tất cả trong VIDEO_ROOT), duration/frame/codec/resolution/fps, audio/subtitle/logo, status 8 QC, phạm vi kiểm tra, lỗi/giới hạn, checksum và xác nhận phim gốc/logo gốc không bị thay đổi.


## 8. Kiểm soát thực thi v1.2.8
- `installation_plan.plan_file`, `plan_file_sha256` và `plan_sha256` được so lại trước approve/install/preflight/run-command. Sửa tệp sau duyệt làm cổng dừng ngay; muốn thêm package phải gọi lại set-install-plan và duyệt hash mới.
- Mục `already_present` vẫn `pending` cho đến khi được duyệt, kiểm chứng thực sự RUNNING và cung cấp JSON `--verification-report` chứa `item_id`, `observed_version`, `status=pass`, `checks` có `method` và `passed=true`.
- `state.qc_gates`: các mốc 09/16/20/24/28/32/36/39 phải có `qc-mark` PASS. JSON report gồm `run_id`, `gate`, `step`, `status=pass`, `checks` ít nhất 2 mục (id, method, passed) và `evidence_paths` nằm trong WORKSPACE. Đây là bằng chứng kỹ thuật tự khai, không thay thế nghiệm thu trực quan/nghe thực tế.
- `blocker.repair_approved`: phê duyệt rủi ro medium/high/critical gắn `blocker_id`; không được gọi lệnh repair trước đó.
- `server_binding.py run-command` chỉ cho phép phase đúng, approval hợp lệ và Linux bubblewrap sandbox. Chế độ không có sandbox mặc định BLOCKED; không có tham số bỏ qua.
- Không thể dùng cờ `--user-approved` để chứng minh mật mã rằng người dùng đã bấm nút thật; host/ứng dụng phải bảo đảm mapping thông điệp người dùng. Giữ audit đầy đủ, không tuyên bố đây là chữ ký số.


## 9. SCRIPT_DURATION — dữ liệu QC3/QC4 bắt buộc (v1.2.9)
- Tham khảo `references/SCRIPT_DURATION.md`. Bước 16 tạo `script/story_events.json` có `run_id`, `source_duration_sec`, mảng events (`id`, `summary`, `source_start_sec`, `phase`, `required`).
- Bước 17 tạo `script/editorial_duration_plan.json` có `run_id`, `target_source=user|story_derived`, `target_duration_sec`, `estimated_tts_wpm`, `rationale`, `dossier_sha256`, `sections:[{name,duration_sec}]`. Không dùng thời lượng mặc định 7–9 phút.
- Bước 20 tạo `script/review_script_v2.txt` và `script/event_coverage.json` (`run_id`, `events:[{event_id,status=covered|omitted,quote|reason}]`). Tất cả `required=true` phải có quote nguyên văn riêng biệt trong V2.
- QC3 JSON report chung phải thêm `editorial_audit:{dossier,plan,script,coverage}` (các đường dẫn tuyệt đối trong cùng RUN_ID). `workflow_state.py qc-mark --gate 3` tính lại số từ/duration và kiểm tra độ phủ; ghi immutable SHA256 của bốn file trong state. Ngưỡng 80–120% target là kiểm tra lời kể dự kiến, không áp thời lượng cố định cho các phim.
- QC4 JSON report chung thêm `tts_duration_audit:{master_wav}` (WAV PCM thật). `workflow_state.py qc-mark --gate 4` đọc số frame/sample-rate, so 80–120% target và lưu SHA256 audio. QC5/QC8 kiểm tra audio SHA vẫn đúng.
- Nếu QC3/4 quá ngắn, xin duyệt riêng `reopen-editorial --from-step 16|17 --reason ... --evidence ... --user-approved` để tạo lượt chỉnh sửa trong RUN_ID, lưu lịch sử, đặt lại các bước/approvals/QC liên quan; KHÔNG tự quay lại hoặc sửa file đã duyệt mà không có phê duyệt.
- State schema 9; lượt cũ schema 8 không tự động resume sau nâng cấp. `server_binding.py` vẫn giữ cơ chế khóa server/folder, không auto failover.
