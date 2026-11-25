# review-phim 1.2.9

Phiên bản kiểm soát **máy chủ → thư mục phim → thư mục logo → WORKSPACE**. Không hỏi menu chọn chế độ khi người dùng gọi plugin để sản xuất. Tự tạo `VIDEO_ROOT/WORKSPACE` trên đúng máy chủ; tất cả output/runtime/model/cache/temp/manifest trong WORKSPACE, logo và phim gốc chỉ đọc.

- Một lần duyệt toàn bộ danh mục cài đặt; mọi mục kể cả phần mềm đã cài vẫn phải được kiểm chứng thực tế trước PASS.
- Mỗi bước sản xuất 01–40 có approval riêng, một lần chạy một bước; 8 QC phải có report và evidence trước PASS.
- `server_binding.py run-command` kiểm tra state, approval, phase, plan hash và sandbox OS trước khi khởi chạy lệnh. Linux dùng bubblewrap hệ thống với chỉ WORKSPACE RW, host root RO. **Windows/macOS chưa hỗ trợ sandbox** và mặc định BLOCKED đối với mọi lệnh production, không fallback không an toàn.
- Chặn SKIPPED chưa duyệt, chặn BLOCKED khởi động lại bước chưa duyệt, yêu cầu approve-repair theo blocker ID cho sửa chữa có rủi ro, và cho sửa danh mục đang pending/đã có prefix PASS trong cùng RUN_ID với phê duyệt hash mới.
- Không tự đăng YouTube, không tự chuyển máy/folder. Không tự khẳng định nút UI được bảo đảm hiển thị trên mọi giao diện.

Xem `skills/review-phim/references/EXECUTION_SECURITY.md`, `WORKFLOW.md`, `SERVER_BINDING.md` và các bài kiểm thử.


## Review dài/ngắn theo từng phim (1.2.9)

- Không mặc định review 7–9 phút. Bước 16 ghi story events; bước 17 lập thời lượng mục tiêu theo phim (ưu tiên số phút người dùng đưa ra), tốc độ TTS ước tính và phân bổ thời lượng từng phần.
- Bước 20/QC3 đọc kịch bản V2 thật, đếm đơn vị cách bằng dấu trắng, ước tính thời lượng, kiểm chứng trích dẫn cho các sự kiện bắt buộc, khóa hash của dossier/plan/script/coverage.
- Bước 24/QC4 đo WAV PCM thật; audio ngắn hơn mục tiêu phải chỉnh sửa có phê duyệt. Có `reopen-editorial` để quay lại bước 16 hoặc 17, lưu revision và buộc duyệt lại từng bước. QC5/QC8 kiểm tra WAV không bị thay đổi.
- Tất cả giữ nguyên quy tắc binding, WORKSPACE và phê duyệt; xem `skills/review-phim/references/SCRIPT_DURATION.md`. Kiểm tra thời lượng và quote không thay thế việc xem/nghe, đánh giá semantic hay quyền sử dụng footage.
