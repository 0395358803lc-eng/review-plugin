# LOGO_ROOT: tự cấp quyền truy cập thư mục đã chọn — Review-Phim 1.2.10

## Nguyên nhân và mục tiêu

Desktop Commander có cấu hình `allowedDirectories` quyết định **thư mục công cụ file được truy cập**. Lỗi `Path not allowed` khi `VIDEO_ROOT` đọc được nhưng `LOGO_ROOT` bị chặn thường do `LOGO_ROOT` chưa nằm trong danh sách. Đây **không phải** lỗi `server_binding.py` khi hai đường dẫn nằm trên các ổ đĩa khác nhau; mã này cho phép đọc `LOGO_ROOT` đã được bind ngay cả khi nằm ngoài `VIDEO_ROOT`.

Người dùng được chọn `LOGO_ROOT` ở **bất cứ thư mục riêng biệt hợp lệ nào trên máy chủ đã chọn** (ví dụ `D:\logo\New folder`, `E:\assets\logo`, thư mục có khoảng trắng, Unicode), không bị yêu cầu chuyển logo sang thư mục phim/WORKSPACE. Chỉ ngoại lệ an toàn: không chọn trùng/lồng nhau với `VIDEO_ROOT` theo khóa hiện tại; không chọn symlink/junction dẫn sai máy; không thể tự vượt quyền NTFS, chính sách doanh nghiệp hoặc sandbox của công cụ.

## Trước khi bind: trình tự bắt buộc sau khi người dùng chọn hai thư mục

1. Ghi rõ `link_id`, `deviceId`, `VIDEO_ROOT`, `LOGO_ROOT` của lượt hiện tại. Không dùng account/device từ lượt trước. Không tạo WORKSPACE hoặc bind nếu chưa xác minh logo được phép đọc.
2. Gọi `get_config` trên **đúng link_id và deviceId**, đọc `allowedDirectories`. Không đoán cấu hình; không đọc hoặc sửa cấu hình của máy khác.
3. Nếu `allowedDirectories` là **mảng không rỗng** và không chứa chính xác `LOGO_ROOT`/đường dẫn cha đã cấp quyền: thêm **duy nhất** đường dẫn `LOGO_ROOT` người dùng đã chọn, không thêm ổ gốc `D:\`, không thêm thư mục cha `D:\logo` khi người dùng chọn `D:\logo\New folder`, không xóa các mục cũ. Dùng `set_config_value(key="allowedDirectories", value=[...old, exact selected logo folder], link_id=..., deviceId=...)`. Đây là thao tác user đã ủy quyền bởi việc yêu cầu tự cấp quyền cho thư mục logo đã chọn.
4. **Tuyệt đối không dùng `allowedDirectories=[]` để mở quyền**, bởi Desktop Commander coi `[]` là cho phép toàn bộ filesystem. Nếu `[]` đã tồn tại thì danh sách không phải nguyên nhân chặn; KHÔNG sửa. Nếu `get_config` không trả về danh sách hợp lệ hoặc `set_config_value` không được phép thì BLOCKED và báo rõ giới hạn.
5. Gọi `get_config` lại cùng account/device và đối chiếu: tất cả entry cũ phải được giữ nguyên và entry mới đúng `LOGO_ROOT`. Nếu tool trả lỗi, không coi quyền đã được cấp.
6. Gọi `get_file_info`/`list_directory` trong chính `LOGO_ROOT` trên cùng account/device để xác minh thực tế; đọc thử đúng file logo người dùng chọn (`read_file` nếu là ảnh, dùng phương án kiểm chứng read-only thích hợp). Phân biệt `PATH_NOT_ALLOWED` do tool allowlist, `OS_ACCESS_DENIED` do Windows/ACL, `NOT_FOUND` và lỗi kết nối. Chỉ tiếp tục nếu đọc thực tế PASS; không dựa vào success của `set_config_value` đơn độc.
7. Xác minh `VIDEO_ROOT` không bị mất quyền trong cấu hình, file phim vẫn truy cập được. Sau đó tạo `VIDEO_ROOT/WORKSPACE`, ghi dấu binding và vào preflight. Việc ghi và render vẫn chỉ dưới WORKSPACE. Khi chọn logo mới cho một RUN_ID khác, làm lại quy trình trên; **không** tự thay LOGO_ROOT của run đã khóa.

## Quy tắc bảo mật

- `allowedDirectories` là quyền truy cập của connector và **không hỗ trợ read-only riêng theo thư mục**: việc thêm đường dẫn sẽ cho connector khả năng thực hiện các công cụ ghi ở đó. Chính sách của plugin vẫn **nghiêm cấm** gọi `write_file`, `edit_block`, `move_file`, `create_directory`, script tạo file hoặc công cụ khác để ghi vào LOGO_ROOT. `server_binding.py verify --write-path` cũng phải từ chối bất kỳ ghi nào ngoài WORKSPACE. Không tuyên bố đây là ACL read-only của OS.
- Không tự động thay đổi `icacls`, Windows ACL, owner, elevation/UAC, ổ đĩa, policy endpoint hoặc quyền hệ thống khác. `get_config`/`set_config_value` chỉ xử lý allowlist của công cụ. Nếu Windows vẫn không có quyền đọc, giữ BLOCKED và yêu cầu người dùng cấp quyền OS theo cách phù hợp.
- Bất kỳ thay đổi cấu hình connector nào cũng tồn tại sau lượt chạy và có thể ảnh hưởng phiên khác. Chỉ thêm chính xác folder đã chọn (least privilege); lưu thay đổi vào báo cáo `logo_access_audit.json` trong WORKSPACE sau khi tạo WORKSPACE, không ghi token, credentials, clientHistory. Không tự thu hồi/xóa quyền của phiên khác.
- Nếu việc cập nhật allowlist bị chặn bởi bảng Run/Cancel của host, tôn trọng xác nhận của user; không né bằng PowerShell/đổi command. Nếu tool bị từ chối 2 lần bởi client, dùng luồng `review_device_call` theo mô tả của connector.
- Tuyệt đối không đổi máy/tài khoản/thư mục phim/logo để lách lỗi. Nếu logo nằm ngoài quyền kiểm soát của thiết bị, báo BLOCKED thật, không gán lỗi `LOGO_ROOT` cho `VIDEO_ROOT`.

## Logic tính allowlist (tham khảo mã đã kiểm thử)

`scripts/plan_logo_access.py` là helper **thuần tính toán**, không thay cấu hình. Đưa object cấu hình từ `get_config` và đường dẫn logo đã chọn vào `plan_logo_access(config, logo_root)` để lấy danh sách mới; sau đó vẫn phải gọi `set_config_value` qua công cụ đúng máy. Trình tự lệnh không yêu cầu chạy script trước khi bind. Helper từ chối root drive và tương đối, giữ nguyên các entry cũ, không trả về `[]` như một bản cập nhật.
