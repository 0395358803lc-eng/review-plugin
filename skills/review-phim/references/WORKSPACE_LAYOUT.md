# Quy ước WORKSPACE bất biến — Review-Phim 1.2.8

## Bắt buộc ngay sau khi chọn thư mục
1. Chọn chính xác account/link_id và deviceId.
2. Người dùng chọn VIDEO_ROOT (thư mục chứa phim) và LOGO_ROOT (thư mục chứa logo; có thể không dùng).
3. Xác minh quyền Desktop Commander của `LOGO_ROOT` theo `LOGO_ACCESS.md` (bổ sung đúng folder đã chọn vào allowedDirectories nếu cần, giữ nguyên mọi entry cũ); sau đó verify hai thư mục và phim/logo nguồn **trên đúng máy**.
4. Tạo `VIDEO_ROOT/WORKSPACE` ngay; không hỏi nơi khác, không tạo ở cạnh VIDEO_ROOT. Nếu đã có, không xóa/ghi đè dữ liệu trước, chỉ tạo phần con cho RUN_ID mới. Nếu symlink/junction, BLOCKED.
5. Tạo `WORKSPACE/tools`, `runtime`, `cache`, `tmp`, `runs/<RUN_ID>`; copy script helper vào `WORKSPACE/tools`.
6. Bind machine and selected roots; workspace path/fingerprint cũng phải được lưu và xác minh mỗi lệnh.
7. Khảo sát máy và đề xuất danh sách cài, chỉ cài bên trong WORKSPACE sau một lần user phê duyệt toàn bộ danh sách.
8. Thực hiện từng bước 01–40; mỗi bước cần phê duyệt trước, PASS mới được hiển thị duyệt bước kế. Giữ QC1–QC8, dừng chọn giọng trước 21.

## Bất biến đường dẫn
- VIDEO_ROOT: chỉ đọc phim gốc và chỉ cho phép tạo thư mục WORKSPACE.
- LOGO_ROOT: chỉ đọc logo. Không chỉnh sửa, không dùng làm nơi xuất kết quả.
- WORKSPACE_ROOT = canonical(VIDEO_ROOT / 'WORKSPACE'): **toàn bộ dữ liệu/công cụ/cache/temp/install/output** phải ở trong.
- `WORKSPACE/tools/server_binding.py`, `WORKSPACE/tools/workflow_state.py`.
- `WORKSPACE/runtime/` chứa Python venv/portable FFmpeg/models và danh mục cài đặt; `WORKSPACE/cache/`, `WORKSPACE/tmp/` chứa cache và file tạm.
- `WORKSPACE/runs/<RUN_ID>/` chứa `server_binding.json`, `binding.json`, `state.json`, `approval_manifest.json`, `environment_report.json`, `installation_plan.json`, `inputs.json`, `logs/`, `reports/`, `asr/`, `frames/`, `understanding/`, `script/`, `tts/`, `timeline/`, `preview/`, `postproduction/`, `delivery/`, `youtube/`.
- Khai báo `--cwd`, `--write-path` trong WORKSPACE. `--read-path` có thể trỏ tới phim nguồn trong VIDEO_ROOT, logo nguồn trong LOGO_ROOT hoặc dữ liệu WORKSPACE.
- Không được tạo file mới ở VIDEO_ROOT trừ bản thân WORKSPACE; không được ghi sang `.review-phim`, Desktop, Documents, home, system temp, `/tmp` hay ổ đĩa/máy khác.
- Mọi ví dụ cũ về `.review-phim` hoặc VIDEO_ROOT là write-root không còn hiệu lực. Căn cứ điều khiển là `server_binding.py` và `workflow_state.py` bản 1.2.8.

## Tách dữ liệu theo lượt và phim
- Nếu VIDEO_ROOT chứa nhiều file video khả dĩ, yêu cầu người dùng chọn **một phim nguồn** trước khi bắt đầu; tuyệt đối không chọn file video bên trong WORKSPACE làm phim gốc, không xử lý phim khác.
- Mỗi lượt chạy mới có RUN_ID khác, ghi vào `WORKSPACE/runs/<RUN_ID>`; không lấy state hoặc clip của lượt/phim khác khi chưa có lựa chọn rõ ràng.
- Dùng lại runtime đã cài trong WORKSPACE chỉ khi đã kiểm tra tương thích, không coi cache/model là bằng chứng hoàn tất bước hay lý do bỏ phê duyệt.
- Không auto-resume phiên cũ và không tự xuất bản YouTube.


## Bảo vệ tiến trình v1.2.8
- Chỉ `VIDEO_ROOT/WORKSPACE` được mount RW khi dùng Linux bubblewrap. Phần còn lại của filesystem host được mount RO.
- `run-command` kiểm tra approval/state trước khi gọi sandbox; không có sandbox thì BLOCKED. Các công cụ CLI khác hoặc process đã chạy bằng quyền người dùng ngoài wrapper **không được** xem là đã nằm trong sandbox.
- Trên Windows/macOS phải cấp riêng môi trường sandbox OS đã kiểm chứng trước khi sản xuất; hiện plugin cố ý từ chối lệnh chưa được cô lập.
