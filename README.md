# review-phim 1.2.5

Nâng cấp khóa cứng **một lượt Production = một máy chủ + một tài khoản Remote Desktop Commander + một thư mục video + một thư mục logo**. Sau khi người dùng chọn máy, mọi thao tác Remote Desktop Commander phải truyền lại đúng `link_id` và `deviceId` đã chọn; không bỏ trống để công cụ tự chọn máy.

Plugin tạo `server_binding.json` bất biến trong `VIDEO_ROOT`, ghi dấu vân tay máy thực tế, ID thiết bị/tài khoản và fingerprint của hai thư mục. `server_binding.py` xác minh binding trước thao tác, chặn đường dẫn ngoài phạm vi, cung cấp `run-command` và cổng `run-workflow`. `workflow_state.py` cũng kiểm tra lại máy, tài khoản và canonical roots trong từng lệnh.

Nếu máy mất kết nối, đổi ID, đổi tài khoản, fingerprint máy/thư mục thay đổi hoặc đường dẫn không khớp: **BLOCKED tại máy và thư mục hiện tại**. Không tự chuyển máy, không tìm folder tương tự, không copy state/PID/cache sang máy khác. Muốn đổi máy hoặc folder phải kết thúc lượt và bắt đầu lượt mới với lựa chọn rõ ràng của người dùng.

`VIDEO_ROOT` là write-root duy nhất. `LOGO_ROOT` và video/logo nguồn chỉ đọc. Workspace, state, logs, cache, temp, venv, công cụ portable và mọi đầu ra nằm trong `VIDEO_ROOT`. Không ghi ra Desktop, Documents, Downloads, home, `/tmp`, thư mục hệ thống, sandbox hoặc ổ khác.

Giữ nguyên quy trình 40 bước, 8 tầng QC, thực hiện tuần tự và dừng trước bước 21 để người dùng chọn giọng. BLOCKED phải có đề xuất sửa và kiểm chứng PASS trước khi tiếp tục. Không tự đăng YouTube.


## GitHub mirror

This repository mirrors Review-Phim plugin version 1.2.5. The `assets/icon.png` file is a regenerated repository icon, not byte-identical to the original binary asset in the private plugin package.
