---
name: review-phim
description: "Điều phối nghiên cứu và sản xuất review phim. Production phải khóa đúng tài khoản Desktop Commander, deviceId, machine fingerprint, VIDEO_ROOT và LOGO_ROOT; không chuyển máy hoặc thư mục giữa lượt. Thực hiện 40 bước và 8 QC tuần tự; lỗi phải BLOCKED, đề xuất sửa và xác minh PASS trước khi tiếp tục."
---
# Review-Phim 1.2.5

## Nguyên tắc cốt lõi

**Một lượt Production = một máy chủ + một tài khoản kết nối + một thư mục video + một thư mục logo.** Sau khi người dùng chọn, bốn giá trị này bị khóa cho đến khi lượt kết thúc. Không tự chuyển máy, đổi account, thay folder, tìm đường dẫn tương tự hoặc dùng tài nguyên từ dự án khác.

Trước khi Production, bắt buộc đọc `references/SERVER_BINDING.md`. Tài liệu này có ưu tiên cao nhất đối với nhận diện máy chủ, Remote Desktop Commander và phạm vi thư mục. Tiếp tục tuân thủ `references/OPERATIONS.md`, `references/SEQUENTIAL_EXECUTION.md`, `references/WORKFLOW.md`, `references/QUALITY.md`, `references/SCHEMAS.md` và `references/EDITORIAL.md`.

## 1. Research hay Production

- **Research-only:** tìm thông tin phim, YouTube, nguồn phát hành, giấy phép, rủi ro bản quyền. Dùng web khi phù hợp; không chọn máy, không mở thư mục, không chạy SOP 40 bước.
- **Production:** xử lý file, transcript, phân tích footage, TTS, dựng, hậu kỳ, QC, thumbnail hoặc xuất video. Bắt buộc chọn máy và khóa binding theo tài liệu `SERVER_BINDING.md`.
- Không tự biến Research thành Production hoặc ngược lại.

## 2. Khởi động Production — đúng thứ tự

### A. Chọn tài khoản kết nối và máy chủ

1. Dùng `list_devices` với đúng tài khoản Desktop Commander. Nếu có nhiều tài khoản kết nối có thể dùng và chưa rõ tài khoản người dùng muốn, hỏi chọn tài khoản trước.
2. Liệt kê máy online/offline. Phân biệt các máy trùng tên bằng `deviceId`.
3. Chờ người dùng chọn một máy. Nếu người dùng đã nêu máy trong yêu cầu hiện tại, xác minh đúng `deviceId` đang online.
4. Lưu nguyên văn `link_id` và `deviceId` vừa chọn. Không dùng ID cũ từ lượt trước.
5. Chưa chạy lệnh, chưa khảo sát, chưa đọc/ghi file cho đến khi người dùng đã chọn máy và cung cấp đủ hai folder.

### B. Chọn hai folder ngay sau khi chọn máy

Hỏi đúng hai đường dẫn:
- `VIDEO_ROOT`: thư mục chứa video/phim nguồn.
- `LOGO_ROOT`: thư mục chứa logo, hoặc người dùng xác nhận không dùng logo.

Nếu hai đường dẫn đã có trong yêu cầu hiện tại thì dùng đúng chúng. Không hỏi thêm hồ sơ, checkpoint, cấu hình hay dữ liệu không cần thiết.

### C. Xác minh và bind

1. Trên đúng `deviceId` vừa chọn, xác minh `VIDEO_ROOT` và `LOGO_ROOT` tồn tại, có quyền phù hợp, không trùng/lồng nhau. Chỉ duyệt nội dung bên trong hai folder.
2. Chọn video nguồn chỉ từ `VIDEO_ROOT`; chọn logo chỉ từ `LOGO_ROOT`. Nếu có nhiều file mơ hồ, hỏi người dùng chọn. Không tìm file ở máy hoặc folder khác.
3. Sinh `RUN_ID` mới. Sao chép cả `scripts/server_binding.py` và `scripts/workflow_state.py` vào `VIDEO_ROOT/.review-phim/tools/`.
4. Chạy lệnh `bind` theo `references/SERVER_BINDING.md` trên đúng máy, truyền đúng `deviceId` và `link_id`. Nếu helper không xác minh được machine fingerprint hoặc bind thất bại, BLOCKED.
5. Lưu `server_binding.json` trong `VIDEO_ROOT/.review-phim/runs/<RUN_ID>/`. Không ghi binding ra ngoài.
6. Chỉ tiếp tục nếu bind trả về `status=bound` và toàn bộ server/folder values khớp lựa chọn người dùng.

## 3. Luật không nhầm máy — áp dụng cho MỌI thao tác

- Sau khi bind, **mọi Remote Desktop Commander call phải truyền rõ cùng `deviceId` và cùng `link_id`**. Không bỏ tham số dù chỉ có một máy online; không dùng thiết bị mặc định.
- Điều này áp dụng cho mọi thao tác đọc/ghi file, liệt kê thư mục, shell, cài đặt, process, polling, tương tác, dừng process và kiểm tra cấu hình.
- Không dùng PID/session trên thiết bị khác. Mọi `read_process_output`, `interact_with_process`, `kill_process`, `force_terminate` phải dùng đúng `deviceId` và `link_id` tạo process.
- Trước thao tác file trực tiếp hoặc truy vấn cấu hình, chạy `server_binding.py verify` trên đúng máy và xác nhận `status=verified`, đúng `binding_id`, `RUN_ID`, `deviceId`, `link_id`, `VIDEO_ROOT`, `LOGO_ROOT`. Với thao tác đọc/ghi, truyền `--read-path`/`--write-path` tương ứng.
- Mọi lệnh shell chạy qua `server_binding.py run-command`; chính wrapper này xác minh binding, working directory, input/output paths và đặt cache/temp dưới `VIDEO_ROOT`. Khai báo đầy đủ `--read-path`, `--write-path`, `--cwd`; command được chạy bằng argument list, không shell ngầm.
- Với state helper, chỉ gọi qua `server_binding.py run-workflow`; wrapper xác minh binding và tự truyền device/link/fingerprint/folder context vào `workflow_state.py`. Không gọi trực tiếp `workflow_state.py`.
- Không dùng Python/container cục bộ, filesystem của ChatGPT, Files/Library, browser download hoặc máy khác để xử lý dữ liệu Production. Plugin package có thể được đọc để sao chép helper, nhưng mọi dữ liệu và artefact Production phải được xử lý trên máy chủ đã khóa.
- Mọi action có tham số `deviceId` đều phải truyền đúng ID đã chọn. Ngoại lệ chỉ dành cho action polling gắn với `call_id` đã tạo trên máy đã khóa (ví dụ `get_tool_result`): dùng nguyên `call_id` và cùng `link_id`, không tạo call mới ở máy khác. `list_devices` không nhận `deviceId`, chỉ dùng lúc chọn máy hoặc kiểm tra lại đúng ID cũ bằng cùng `link_id`; không chọn thiết bị thay thế. Nếu action có thể thực thi trên thiết bị mà không có cách ràng buộc/đối chiếu thì không dùng cho Production.
- Tên hiển thị không phải khóa. Máy cùng tên nhưng `deviceId` khác là máy khác.

## 4. Luật không nhầm folder

- `VIDEO_ROOT` canonical là write-root duy nhất. Tất cả output, state, cache, temp, venv, model, log và Final phải nằm bên trong.
- `LOGO_ROOT` canonical là read-only. Không tạo, sửa, xóa, đổi tên hoặc ghi file vào đây.
- Video nguồn và logo nguồn luôn chỉ đọc.
- Mọi đường dẫn phải là absolute canonical path; không dùng relative path, `~`, đường dẫn đoán hoặc path từ lịch sử chat.
- Trước khi ghi, `server_binding.py verify --write-path` phải xác nhận target nằm trong `VIDEO_ROOT`. Trước khi đọc, `--read-path` phải xác nhận target nằm trong `VIDEO_ROOT` hoặc `LOGO_ROOT`.
- Symlink/junction trỏ ra ngoài root, root đổi, folder mất hoặc path fingerprint mismatch đều là BLOCKED. Không tự tìm folder khác cùng tên.
- Nếu người dùng đổi folder, dừng lượt hiện tại và tạo run mới với binding mới. Không trộn state hoặc artefact cũ.

## 5. Quy trình sản xuất

1. Khảo sát OS, CPU, RAM, GPU/VRAM, dung lượng, quyền và phần mềm trên đúng máy đã khóa.
2. Tạo `environment_report.json` và `installation_plan.json` trong run workspace dưới `VIDEO_ROOT`.
3. Trình bày cấu hình và kế hoạch cài; chờ người dùng duyệt trước khi cài.
4. Cài từng thành phần một, tất cả trong `VIDEO_ROOT`; xác minh version/import/API/smoke test rồi mới sang thành phần tiếp.
5. Preflight PASS rồi mới bắt đầu `references/WORKFLOW.md`.
6. Thực hiện đủ 40 bước theo đúng thứ tự, không chạy song song, không gộp bước, không tạo trước artefact của bước sau.
7. Dừng bắt buộc sau bước 20/QC3 để người dùng chọn preset giọng thực tế trước bước 21.
8. Thực hiện 8 QC tại đúng vị trí trong `references/QUALITY.md`.
9. Giao video và metadata; không tự đăng YouTube.

Mọi manifest, log, QC report và artefact phải ghi cùng `run_id`, `binding_id`, `deviceId`, `link_id`, machine fingerprint, `VIDEO_ROOT` và `LOGO_ROOT`. Không trộn file từ lượt/máy khác.

## 6. BLOCKED — không tự failover

Nếu máy chủ mất kết nối, `deviceId` đổi/mất, fingerprint không khớp, đường dẫn thay đổi hoặc binding verify thất bại:

1. Dừng ngay thao tác đang chạy; không tiếp tục ghi hoặc render.
2. Ghi lỗi và bằng chứng trong `VIDEO_ROOT` nếu máy vẫn truy cập được.
3. Hiển thị chẩn đoán, nguyên nhân đã xác minh/giả thuyết, phương án sửa, rủi ro, yêu cầu phê duyệt và tiêu chí kiểm tra.
4. Chỉ được kiểm tra lại `list_devices` bằng đúng `link_id` cũ để xem chính `deviceId` đã chọn có online trở lại hay không.
5. Nếu đúng `deviceId` online, verify lại machine fingerprint và folder binding. Chỉ tiếp tục nếu PASS.
6. Nếu `deviceId` khác, fingerprint khác hoặc máy không online: dừng và hỏi người dùng. Không chọn máy khác dù cùng tên, cùng cấu hình hoặc đang online.
7. Chỉ người dùng mới được yêu cầu đổi máy. Khi đổi máy, phải bắt đầu lượt mới và bind lại; không chuyển state, PID, cache, temp hay output của lượt cũ sang máy mới.

Không được tự chuyển server để né lỗi, không tự đổi account, không tự đổi folder, không xóa binding để mở khóa. Chỉ tiếp tục bước hiện tại sau khi lỗi được sửa và kiểm chứng PASS.

## 7. Tiêu chuẩn hoàn tất

- Giữ nguyên SOP 11 giai đoạn, 40 bước, 8 QC và các điểm dừng.
- Giữ nguyên video/logo nguồn.
- Toàn bộ artefact Production ở trong `VIDEO_ROOT`; `LOGO_ROOT` không thay đổi.
- Binding server/folder đúng từ đầu đến cuối; tất cả process thuộc đúng `deviceId`.
- Báo cáo rõ codec, độ phân giải, fps, duration, audio, subtitle, logo, QC, hash, hạn chế và tình trạng quyền.
- Không tuyên bố đã nghiệm thu nếu chưa kiểm tra trên chính máy chủ đã khóa.
