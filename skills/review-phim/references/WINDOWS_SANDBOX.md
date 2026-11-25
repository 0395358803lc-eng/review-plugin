# Windows Sandbox (Review-Phim 1.3.1) — đặc tả an toàn và nghiệm thu

Áp dụng cho Windows; phần này **supersede** câu "Windows/macOS không có sandbox" trong tài liệu 1.2.x, nhưng không sửa nguyên tắc machine binding, WORKSPACE, cổng phê duyệt, 40 bước, 8 QC. Windows chỉ khả dụng khi sandbox VM thực sự chạy và PASS. macOS vẫn BLOCKED.

## Điều kiện
- Windows 11 Pro/Enterprise/Education (hoặc edition Windows 10 tương ứng) được Microsoft hỗ trợ, virtualization trong BIOS bật, Windows Sandbox feature được bật, máy có RAM/CPU phù hợp.
- `WindowsSandbox.exe` phải là system binary tin cậy ở `C:\Windows\System32`; không chạy file giả ở user/profile/WORKSPACE.
- Không đổi OS edition, BIOS, Hyper-V features, drivers, registry, firewall/ACL hệ thống hay reboot tự động. Nếu thiếu điều kiện: `UNSUPPORTED_WINDOWS_EDITION`, `OS_WRITE_SANDBOX_UNAVAILABLE` hoặc mã tương ứng, yêu cầu người dùng thay đổi điều kiện riêng, sau đó kiểm tra lại.
- **Windows Home/Home Single Language không hỗ trợ Windows Sandbox**; một lệnh shell hoặc unit test PASS không phải là nghiệm thu sandbox.

## Thiết lập
Sau tạo `VIDEO_ROOT/WORKSPACE` và bind (mỗi call đúng link_id + deviceId), copy 5 script từ plugin vào `WORKSPACE/tools`:
`server_binding.py`, `workflow_state.py`, `windows_sandbox_adapter.py`, `windows_sandbox.py`, `windows_sandbox_guest.ps1`.

Sử dụng interpreter đã xác thực trên host chỉ để **gọi adapter quản lý** (không chạy công việc media dưới host); interpreter sản xuất trong VM phải là **portable runtime cài riêng vào WORKSPACE** và được dùng bằng đường dẫn mapped guest. Interpreter ở `.review-phim` cũ không được phép làm runtime Production.

Mọi CLI ràng buộc với `--binding-file`, `--run-id`, `--device-id`, `--link-id`, `--video-root`, `--logo-root` đúng server/folder đã chọn. Trên Windows gọi `windows_sandbox_adapter.py` cho `bind`, `verify`, `run-workflow`, `run-command`. Các lệnh `run-command` vẫn phải có `--phase`, `--cwd`, `--read-path`, `--write-path`, đúng trạng thái phê duyệt của bước hoặc item.

### Kiểm tra host đọc-only
`python WORKSPACE\tools\windows_sandbox_adapter.py sandbox-doctor --binding-file ... --run-id ... --device-id ... --link-id ... --video-root ... --logo-root ...`

`ELIGIBLE_NOT_ACCEPTED` chỉ là xác nhận máy **có khả năng**, chưa có quyền chạy Production. Nếu Windows Home, trả BLOCKED; không có fallback.

### Nghiệm thu guest thực tế
`python WORKSPACE\tools\windows_sandbox_adapter.py sandbox-acceptance --binding-file ... --run-id ... --device-id ... --link-id ... --video-root ... --logo-root ...`

Runner tạo job và config `.wsb` trong `WORKSPACE/runs/<RUN_ID>/sandbox_jobs`; chạy một VM Windows Sandbox mới, mapping:
- `VIDEO_ROOT` → `C:\ReviewSourceReadOnly` với `ReadOnly=true`.
- `LOGO_ROOT` → `C:\ReviewLogoReadOnly` với `ReadOnly=true`.
- `WORKSPACE` → `C:\ReviewWorkspace` với `ReadOnly=false`.

Tắt Networking, VGpu, ClipboardRedirection, PrinterRedirection, AudioInput, VideoInput; bật ProtectedClient. Guest chạy `windows_sandbox_guest.ps1`, thử tạo-xóa file trong WORKSPACE (phải PASS), thử ghi vào hai thư mục nguồn (phải DENIED), xác minh không có network adapter hoạt động. Chỉ khi nhận kết quả guest có nonce/job ID hợp lệ và tất cả check PASS mới tạo `sandbox_acceptance.json` cùng binding/version/hash runner. Đây **không phải** QC video.

Nếu timeout, thiếu feature, thay script guest, sai binding, thiếu approval, không có portable runtime, mapping không read-only hoặc guest không PASS, chặn `run-command`. Không cho phép `--unsafe`, `--no-sandbox`, `--ignore-approval` hoặc `--force`. VM sẽ tắt sau khi ghi report. Không sử dụng `taskkill` trên session sandbox của người khác.

## Ghi chú triển khai
- VM có ổ C: riêng và có thể tạo file tạm **trong guest**; điều kiện bảo vệ là **không có host write ngoài WORKSPACE**. Không mount host C:.
- `WORKSPACE` RW là bề mặt rủi ro có chủ đích: chỉ đưa vào đó runtime, script và dữ liệu cần dùng, sao lưu output quan trọng và kiểm tra hash. Test guest không thay thế kiểm tra mã độc hoặc bảo đảm an toàn tuyệt đối.
- Input AV/FFmpeg lớn hoặc bản dịch có thể cần portable Python/FFmpeg và model đặt trong WORKSPACE; đừng chuyển lén venv cũ ngoài WORKSPACE sang guest.
- Plugin không tự migrate 375/1.250 đoạn dịch từ run cũ. Nếu muốn tái sử dụng bản cũ, phải xác minh nguồn phim, hash, cùng nội dung, user approval và data lineage trong lượt mới; không tự coi bước 09 PASS.

## Nghiệm thu định lượng
- Static/unit tests: XML mapping chính xác, network/clipboard disabled, đường dẫn khác root bị chặn, không chạy khi chưa có acceptance, Windows Home blocked, no sandbox fallback.
- Host check: edition/feature/virtualization; báo `BLOCKED` với mã thực khi thiếu.
- **Chỉ nhãn `ACCEPTED_REAL_GUEST`** nếu acceptance thật trên đúng deviceId/link_id/binding pass hết 4 điều kiện (kể cả logo nếu có). Không tự cấp chứng nhận dựa trên mock hoặc test Linux.
- Xuất `sandbox_acceptance.json`, job result, thời gian và hash trong WORKSPACE; kiểm tra lại trước mỗi run-command.

Nguồn: Microsoft Learn, "Use and configure Windows Sandbox" và "Install Windows Sandbox".
