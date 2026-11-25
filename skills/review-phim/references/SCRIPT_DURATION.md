# Review-Phim 1.2.9 — Kiểm soát độ dài review theo nội dung phim

**Ưu tiên bắt buộc cho các bước 16–40, đặc biệt QC3 và QC4.** Tài liệu này bổ sung `EDITORIAL.md`, `WORKFLOW.md`, `QUALITY.md`. Không đặt mặc định video 7–9 phút, 8 phút, 10 phút hoặc bất kỳ thời lượng cố định nào cho tất cả phim. Không lấy thời lượng của phim ví dụ trong `EXAMPLE.md` làm thời lượng phim mới.

## 1. Thời lượng lấy từ đâu?

1. Nếu người dùng đưa ra thời lượng review mục tiêu, **ưu tiên đúng thời lượng ấy**. Lưu `target_source="user"`; nếu không thể đạt mà vẫn kể đúng, nêu lý do và xin quyết định mới, không âm thầm đổi mục tiêu.
2. Nếu người dùng chưa nêu mục tiêu, **ChatGPT tự xác định riêng từng phim**, xét: thời lượng phim gốc từ ffprobe, số lượng sự kiện cần kể, tuyến nhân vật, nhánh phụ có tác động, mức độ phức tạp nguyên nhân/hậu quả, xung đột, cao trào, nhịp kể và lượng hình ảnh có thể chứng minh. Lưu `target_source="story_derived"` kèm lời giải thích cụ thể.
3. Dùng tốc độ TTS ước tính theo kết quả smoke test hiện có. Trước bước 21 chưa biết chính xác preset giọng của người dùng: **không khẳng định đó là tốc độ thực tế của giọng cuối**. Bước 24 kiểm tra lại bằng thời lượng WAV thực.
4. Dành ngân sách nội dung theo nhiều phần: hook, bối cảnh, phát triển, biến cố, cao trào, giải quyết và kết. Có thể gộp thành ít nhất 3 phần phù hợp với phim, không kéo dài vô nghĩa.
5. Mục tiêu của `target_duration_sec` là **lời kể review**. Intro/outro, quảng cáo, cảnh nhạc không lời phải được báo riêng, không dùng để hợp thức hóa lời kể thiếu nội dung.

## 2. Quy trình bước 16–20

**Bước 16:** Dossier phải có danh mục tình tiết thực từ phim nguồn (`script/story_events.json`): `run_id`, `source_duration_sec`, `events`. Mỗi sự kiện có `id`, `source_start_sec`, `summary` (có căn cứ), `phase` và `required` (true nếu cần kể để hiểu câu chuyện). Ghi lại quan hệ nguyên nhân–hậu quả và vùng chưa xác minh. Số sự kiện tối thiểu để kiểm tra độ bao phủ nguồn: `max(3, min(12, floor(source_duration_sec/900)))`. Đây chỉ là ngưỡng chống hồ sơ quá sơ sài, không bảo đảm tự động tính chính xác nội dung.

**Bước 17:** Lập `script/editorial_duration_plan.json` trước khi viết V1; ghi thời lượng riêng phim, căn cứ, tốc độ TTS ước tính, số từ mục tiêu (= số giây × WPM ÷ 60), phân bổ theo phần. Viết V1 theo sự kiện, không áp thời lượng mẫu. Nếu phim nhiều biến cố, tăng ngân sách và giữ logic thay vì nén mọi phim xuống 7–9 phút.

**Bước 18–19:** Kiểm tra nguồn ngoài và đối chiếu từng sự kiện trong hồ sơ với V1/V2. Những sự kiện `required=true` không được bỏ qua. Nếu `required=false` và lược bỏ, phải ghi lý do. Không bịa chi tiết chỉ để tăng thời lượng.

**Bước 20:** Xuất V2 lời kể thuần `.txt` và `script/event_coverage.json` ánh xạ mỗi sự kiện về trích dẫn **thực sự xuất hiện trong V2**. QC3 phải tính lại số token cách bằng dấu cách, tốc độ đọc dự kiến, thời lượng dự kiến, và kiểm tra các trích dẫn; không duyệt tự khai trong báo cáo. Độ lệch được phép mặc định: 80–120% thời lượng mục tiêu. Nếu thiếu, sửa nội dung/điều chỉnh mục tiêu có lý do trong cùng bước; không tự nhồi lời vô nghĩa, bỏ cốt truyện hoặc cho QC3 PASS.

### Mẫu các file trong `VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/`

`script/story_events.json`:

```json
{
  "run_id": "run-example",
  "source_duration_sec": 5400,
  "events": [
    {"id":"event-01","source_start_sec":120,"phase":"mở đầu","required":true,"summary":"Nhân vật phát hiện dấu hiệu gây ra biến cố quan trọng"},
    {"id":"event-02","source_start_sec":1420,"phase":"phát triển","required":true,"summary":"Nhân vật đưa ra quyết định tác động tới cuộc điều tra"},
    {"id":"event-03","source_start_sec":3000,"phase":"cao trào","required":true,"summary":"Mâu thuẫn được đẩy lên và dẫn tới đối đầu trực tiếp"},
    {"id":"event-04","source_start_sec":5200,"phase":"kết","required":true,"summary":"Kết quả của đối đầu cho thấy hậu quả của lựa chọn"}
  ]
}
```

Với phim dài 5.400 giây, hồ sơ thực tế cần ít nhất 6 sự kiện có căn cứ (mẫu 4 sự kiện trên chỉ minh họa cấu trúc, **chưa đạt QC3**). Không tự gán mốc thời gian nếu chưa đối chiếu footage.

`script/editorial_duration_plan.json`:

```json
{
  "run_id": "run-example",
  "target_source": "story_derived",
  "target_duration_sec": 1080,
  "estimated_tts_wpm": 180,
  "rationale": "Mục tiêu riêng của phim dựa trên số biến cố bắt buộc, nhánh nhân vật, cao trào và nhịp kể đã quan sát.",
  "dossier_sha256": "<SHA256 của story_events.json>",
  "sections": [
    {"name":"mở đầu", "duration_sec":180},
    {"name":"diễn biến và xung đột", "duration_sec":630},
    {"name":"cao trào và kết thúc", "duration_sec":270}
  ]
}
```

`script/event_coverage.json`:

```json
{
  "run_id":"run-example",
  "events":[
    {"event_id":"event-01","status":"covered","quote":"Trích nguyên văn một câu đủ rõ trong V2 kể đúng tình tiết này"},
    {"event_id":"event-02","status":"covered","quote":"Trích nguyên văn một câu khác trong V2 kể tình tiết thứ hai"}
  ]
}
```

Thêm đầy đủ mọi sự kiện trong hồ sơ; các trích dẫn trên chỉ là placeholder, không được dùng như bằng chứng thật.

### QC3 report trước `qc-mark --gate 3`

Ngoài trường QC chung (`run_id`, `gate=3`, `step=20`, `status=pass`, `checks`, `evidence_paths`), phải có:

```json
"editorial_audit": {
  "dossier": "<đường dẫn tuyệt đối đến story_events.json>",
  "plan": "<đường dẫn tuyệt đối đến editorial_duration_plan.json>",
  "script": "<đường dẫn tuyệt đối đến review_script_v2.txt>",
  "coverage": "<đường dẫn tuyệt đối đến event_coverage.json>"
}
```

`workflow_state.py` tự đọc những file này, kiểm tra RUN_ID/path, hash dossier, số từ, dự kiến giọng đọc và trích dẫn của từng tình tiết cần thiết; ghi `editorial_audit` cùng SHA256 bốn file vào `state.qc_gates.3`. Thay file đã được duyệt sẽ làm các cổng sau BLOCKED. **Cần QC thủ công về tính đúng ngữ nghĩa và chất lượng kể chuyện**: kiểm tra chuỗi ký tự không thể tự chứng minh kịch bản đúng phim.

## 3. QC4 và các bước 25–39

- Bước 21–23: sau khi người dùng chọn giọng, sử dụng đúng V2 đã được QC3 và giữ trọn các phân đoạn. Không cắt câu chuyện để đạt một thời lượng quen thuộc.
- Bước 24: ghép ra `tts/narration_final.wav` có audio PCM thật (hoặc chuyển một bản *sao chép* master sang PCM WAV trong WORKSPACE để kiểm tra), đo frame/sample-rate trực tiếp; QC4 report cần `"tts_duration_audit":{"master_wav":"<đường dẫn WAV tuyệt đối>"}`. Cổng tính lại duration và kiểm tra đạt 80–120% mục tiêu QC3, lưu SHA256 audio. Không đo bằng lời tự khai.
- Nếu QC4 quá ngắn hoặc quá dài: BLOCKED; báo thời lượng mục tiêu/thực tế và nguyên nhân, không kéo chậm/tăng tốc bất thường cho đủ phút. Đề xuất **`reopen-editorial`**, bắt buộc người dùng phê duyệt riêng, quay lại bước 17 hoặc 16, lưu bản cũ, bỏ approval/QC sau đó và duyệt lại từng bước.
- Bước 25–28: timeline phải giữ toàn bộ lời kể và có độ dài tương ứng với WAV master; QC5 từ chối nếu WAV đã bị thay đổi. Báo riêng thời lượng timeline và so với audio bằng thông tin frame/FFprobe thực tế.
- Bước 29–39: giữ nguyên độ dài lời kể đã duyệt. Không cắt còn 7–9 phút để giảm render. QC8 kiểm tra video Final theo ffprobe và đối chiếu WAV master; thời lượng intro/outro riêng. QC5/QC8 chặn nếu audio nguồn đã thay đổi sau QC4.

## 4. Reopen có kiểm soát (không tự chạy)

Chỉ sau khi người dùng xác nhận rõ, chạy trên đúng server bằng `server_binding.py run-workflow`:

```text
reopen-editorial --state <STATE_PATH> --from-step 17 --reason "Kịch bản và giọng đọc thiếu các nút thắt đã xác minh" --evidence <REPORT_PATH> --user-approved
```

Chọn `--from-step 16` nếu dossier thiếu tình tiết (cần chạy lại QC2), hoặc `17` nếu dàn ý/kịch bản cần mở rộng. Helper sao lưu bản đã duyệt nếu còn nguyên hash, lưu lịch sử revision, reset các bước từ đó đến 40, xoá approvals/QC không còn hợp lệ và reset lựa chọn giọng. **Đây là lựa chọn của người dùng, không tự sửa hoặc tự chạy bước tiếp.** Sau đó hiển thị phê duyệt riêng bước được mở lại.

## 5. Giới hạn và tuyên bố chính xác

- `str.split()` là đếm đơn vị cách nhau bởi dấu trắng, không phải word segmentation ngôn ngữ Việt; tốc độ WPM ước tính có thể sai. QC4 dùng WAV thật để điều chỉnh.
- Phân tích chứng cứ sự kiện bằng trích dẫn và timestamp vẫn cần đối chiếu với phim; helper không thực hiện semantic understanding. Số lượng sự kiện tối thiểu không đồng nghĩa bảo đảm nội dung hay.
- Các phép đo QC4 yêu cầu WAV PCM có cấu trúc hợp lệ, không xác minh ngữ điệu/cảm xúc hay đồng bộ clip. Không thay TTS/ASR, kiểm tra nghe thật hoặc hậu kỳ bằng phép tính thời lượng.
- Không thay đổi cổng phê duyệt, server binding, sandbox, WORKSPACE hay quyền tư liệu. Không thể đảm bảo video nào cũng đạt một thời lượng hay lượng xem cố định.
