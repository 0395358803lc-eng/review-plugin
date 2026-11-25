# Khóa cứng máy chủ và thư mục — Review-Phim 1.2.8

Tài liệu này có **ưu tiên cao nhất** đối với mọi thao tác Production dùng Remote Desktop Commander. Nếu tài liệu nào khác nói khác, áp dụng tài liệu này. Mục tiêu là không bao giờ nhầm máy chủ, tài khoản kết nối, thư mục video hoặc thư mục logo.

## 1. Khóa nhận diện máy chủ

Một máy chủ được xác định bằng đủ ba yếu tố, không chỉ bằng tên hiển thị:

1. `link_id`: đúng tài khoản Desktop Commander đã dùng để liệt kê thiết bị.
2. `deviceId`: đúng ID thiết bị trả về từ `list_devices` và được người dùng chọn.
3. `machine_fingerprint`: dấu vân tay máy thực tế được `server_binding.py` tính trên máy đang chạy.

Tên máy chủ chỉ để hiển thị. Hai máy có cùng tên vẫn là hai máy khác nhau nếu `deviceId` khác nhau.

### Quy tắc bắt buộc cho mọi lần gọi Remote Desktop Commander

- Khi gọi `list_devices`, dùng đúng `link_id` hiện tại. Nếu có nhiều tài khoản kết nối có thể dùng được và chưa rõ tài khoản nào người dùng muốn, hỏi người dùng chọn tài khoản trước.
- Khi người dùng chọn máy, lưu nguyên văn `link_id`, `deviceId` và tên hiển thị vừa trả về. Không tự đổi chữ hoa/thường, không tạo lại, không dùng ID từ cuộc trò chuyện/lượt chạy cũ.
- Mọi Remote Desktop Commander action có trường `deviceId` đều phải truyền đúng `deviceId` và `link_id` đó, kể cả khi chỉ còn một máy online. Ngoại lệ có kiểm soát: `get_tool_result` được định danh bằng `call_id` của tác vụ ban đầu và phải dùng cùng `link_id`; `list_devices` chỉ dùng cùng `link_id` để liệt kê/kiểm tra đúng `deviceId` cũ. Không dùng action khác nếu không thể ràng buộc nó về đúng máy.
- Áp dụng cho `get_config`, `start_process`, `read_process_output`, `interact_with_process`, `list_sessions`, `list_processes`, `read_file`, `write_file`, `create_directory`, `list_directory`, `get_file_info`, tìm kiếm file và mọi thao tác khác có tham số thiết bị.
- PID/process session chỉ có ý nghĩa trên máy đã tạo nó. Mọi thao tác poll, tương tác, dừng hoặc kết thúc process phải dùng đúng `deviceId` và `link_id` đã tạo process.
- Không dùng `node:local`, Python/container cục bộ, Files/Library, máy ChatGPT hoặc một connector khác để xử lý dữ liệu Production. Tất cả đọc/ghi, cài đặt, render và kiểm tra file Production phải chạy trên máy đã chọn.

## 2. Khóa cứng thư mục

Ngay sau khi chọn máy, nhận đúng hai đường dẫn:

- `VIDEO_ROOT`: thư mục chứa phim nguồn, chỉ đọc (ngoài thao tác tạo `WORKSPACE`).
- `VIDEO_ROOT/WORKSPACE`: tạo tự động ngay sau khi xác minh VIDEO_ROOT và LOGO_ROOT; đây là **write-root duy nhất**.
- `LOGO_ROOT`: thư mục chứa logo — read-only; hoặc `null` khi người dùng xác nhận không dùng logo.

Trên chính máy đã chọn:

- Chuẩn hóa đường dẫn tuyệt đối và canonical path (`realpath`, giải quyết junction/symlink).
- Xác minh cả hai thư mục tồn tại; video nguồn phải nằm trong `VIDEO_ROOT`, logo phải nằm trong `LOGO_ROOT`.
- Hai root không được trùng hoặc lồng nhau. Nếu lồng nhau, dừng và yêu cầu chọn lại.
- Không tìm thư mục thay thế cùng tên ở Desktop, home, ổ khác, máy khác hoặc dự án khác.
- Mọi file tạm, cache, venv, model, state, log, manifest, proxy, thumbnail, audio, video trung gian và Final phải ở dưới `VIDEO_ROOT/WORKSPACE/`. Không ghi dữ liệu mới vào `.review-phim` ở gốc VIDEO_ROOT.
- Video gốc và logo gốc chỉ đọc. Không ghi vào `LOGO_ROOT`, kể cả file tạm.
- Với mọi đường dẫn output, kiểm tra canonical path vẫn nằm dưới `VIDEO_ROOT/WORKSPACE`; với mọi đường dẫn input, chỉ cho phép nằm dưới `VIDEO_ROOT` hoặc `LOGO_ROOT`.
- Nếu symlink/junction dẫn ra ngoài root, đường dẫn không hợp lệ và phải BLOCKED.
- Không đổi `VIDEO_ROOT`/`LOGO_ROOT` giữa lượt. Nếu người dùng muốn đổi thư mục, kết thúc lượt hiện tại và tạo lượt mới với xác nhận đường dẫn mới.

## 3. Tạo manifest khóa cho mỗi lượt

Mỗi Production là một lượt mới. Sinh `RUN_ID` mới và đặt manifest tại:

`VIDEO_ROOT/WORKSPACE/runs/RUN_ID/server_binding.json`

Ngay sau khi người dùng chọn 2 thư mục, dùng công cụ file có ràng buộc đúng deviceId và link_id để **tạo `VIDEO_ROOT/WORKSPACE`** (bằng một thao tác mkdir duy nhất). Nếu WORKSPACE đã có, giữ nguyên, không xóa. Xác minh thư mục thật, không symlink/junction, không trỏ ra ngoài. Sau đó sao chép cả hai helper `skills/review-phim/scripts/server_binding.py` và `skills/review-phim/scripts/workflow_state.py` của plugin vào:

- `VIDEO_ROOT/WORKSPACE/tools/server_binding.py`
- `VIDEO_ROOT/WORKSPACE/tools/workflow_state.py`

Chỉ sao chép helper vào thư mục đã chọn trên đúng thiết bị. Dùng đường dẫn tuyệt đối. Với Windows, gọi `python` bằng PowerShell; với Linux/macOS dùng Python tương ứng. Helper `bind` kiểm tra và tự tạo WORKSPACE nếu chưa tồn tại (idempotent), nhưng muốn gọi helper từ WORKSPACE/tools thì phải tạo WORKSPACE trước như trên. Nếu helper không chạy hoặc không đọc được stable machine ID, BLOCKED — không hạ cấp sang nhận diện bằng tên máy.

Lệnh bind mẫu (thay placeholder bằng giá trị thực tế đã xác minh):

```powershell
python "<VIDEO_ROOT>\WORKSPACE\tools\server_binding.py" bind `
  --binding-file "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\server_binding.json" `
  --run-id "<RUN_ID>" `
  --server-label "<SERVER_LABEL>" `
  --device-id "<EXACT_DEVICE_ID>" `
  --link-id "<EXACT_LINK_ID>" `
  --video-root "<VIDEO_ROOT>" `
  --logo-root "<LOGO_ROOT>"
```

Nếu không dùng logo, bỏ `--logo-root`. Helper tạo manifest bằng chế độ exclusive-create, không cho ghi đè binding cũ. Manifest lưu ID thiết bị/tài khoản, machine fingerprint, canonical roots, WORKSPACE path/fingerprint, root fingerprints và chính sách `server_failover=forbidden`.

## 4. Cổng xác minh bắt buộc

Trước mỗi thao tác file trực tiếp hoặc truy vấn cấu hình sau khi bind:

1. Gọi `server_binding.py verify` trên chính thiết bị đã chọn bằng `start_process`, truyền đúng `deviceId` và `link_id`.
2. Xác minh kết quả là `status=verified`, đúng `binding_id`, `RUN_ID`, `deviceId`, `link_id`, `VIDEO_ROOT`, `LOGO_ROOT`.
3. Chỉ sau khi verify đạt mới thực hiện thao tác kế tiếp, vẫn bằng đúng `deviceId` và `link_id`.

Đối với lệnh shell, dùng `run-command` (tự verify binding/path); đối với state, dùng `run-workflow` (tự verify binding/state). Không cần gọi verify riêng ngay trước hai wrapper này vì mỗi wrapper đã thực hiện kiểm tra bên trong.

Mẫu verify trước khi ghi:

```powershell
python "<VIDEO_ROOT>\WORKSPACE\tools\server_binding.py" verify `
  --binding-file "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\server_binding.json" `
  --run-id "<RUN_ID>" `
  --device-id "<EXACT_DEVICE_ID>" `
  --link-id "<EXACT_LINK_ID>" `
  --video-root "<VIDEO_ROOT>" `
  --logo-root "<LOGO_ROOT>" `
  --write-path "<ABSOLUTE_OUTPUT_PATH>" `
  --cwd "<VIDEO_ROOT>\WORKSPACE"
```

Mẫu verify trước khi đọc file:

```powershell
python "<VIDEO_ROOT>\WORKSPACE\tools\server_binding.py" verify `
  --binding-file "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\server_binding.json" `
  --run-id "<RUN_ID>" `
  --device-id "<EXACT_DEVICE_ID>" `
  --link-id "<EXACT_LINK_ID>" `
  --video-root "<VIDEO_ROOT>" `
  --logo-root "<LOGO_ROOT>" `
  --read-path "<ABSOLUTE_INPUT_PATH>"
```

Với `LOGO_ROOT=null`, bỏ `--logo-root`. Không dùng đường dẫn tương đối. Sau verify, thao tác thật vẫn phải truyền đúng `deviceId` và `link_id`.

### Chạy lệnh shell qua cổng binding
Không gọi trực tiếp `start_process` cho FFmpeg, Python, pip, model tools hoặc script sản xuất. Hãy gọi `server_binding.py run-command` bằng `start_process` trên đúng `deviceId` + `link_id`; khai báo mọi input/output path và working directory. Wrapper tự kiểm tra server binding, canonical paths, và đặt TEMP/cache trong `VIDEO_ROOT/WORKSPACE`. Lệnh con chạy bằng argument list (`shell=False`).

```powershell
python "<VIDEO_ROOT>\WORKSPACE\tools\server_binding.py" run-command `
  --binding-file "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\server_binding.json" `
  --run-id "<RUN_ID>" `
  --device-id "<EXACT_DEVICE_ID>" `
  --link-id "<EXACT_LINK_ID>" `
  --video-root "<VIDEO_ROOT>" `
  --logo-root "<LOGO_ROOT>" `
  --phase step --step 7 `
  --cwd "<VIDEO_ROOT>\WORKSPACE" `
  --read-path "<ABSOLUTE_INPUT_PATH>" `
  --write-path "<ABSOLUTE_OUTPUT_PATH>" `
  -- python "<VIDEO_ROOT>\WORKSPACE\scripts\task.py"
```

Không khai báo thiếu đường dẫn đọc/ghi. Mọi đường dẫn command dùng để đọc/ghi phải được khai báo tương ứng; output chỉ ở `VIDEO_ROOT/WORKSPACE`. Nếu không thể xác định hoặc kiểm soát path, BLOCKED. Với lệnh dài, `start_process` khởi chạy wrapper; mọi poll/interact/terminate phải giữ nguyên `deviceId` + `link_id`.

### Gọi thao tác file trực tiếp
Với `read_file`, `write_file`, `create_directory`, `move_file`, `list_directory` hoặc thao tác file tương tự: chạy `verify` với `--read-path`/`--write-path` phù hợp trước; sau đó gọi thao tác file bằng cùng `deviceId` + `link_id`. Không dùng `read_file`/`write_file` khi chưa verify phạm vi. `LOGO_ROOT` chỉ được khai báo trong `--read-path`, tuyệt đối không phải `--write-path`.

### Gọi workflow state

Không gọi trực tiếp `workflow_state.py`. Dùng cổng `run-workflow`, cổng này kiểm tra lại máy chủ, machine fingerprint và hai folder trước khi gọi state helper; tự truyền đúng `--remote-device-id`, `--remote-link-id`, `--expected-server-fingerprint`, `--video-root` và `--logo-root` vào helper:

```powershell
python "<VIDEO_ROOT>\WORKSPACE\tools\server_binding.py" run-workflow `
  --binding-file "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\server_binding.json" `
  --run-id "<RUN_ID>" `
  --device-id "<EXACT_DEVICE_ID>" `
  --link-id "<EXACT_LINK_ID>" `
  --video-root "<VIDEO_ROOT>" `
  --logo-root "<LOGO_ROOT>" `
  --workflow-script "<VIDEO_ROOT>\WORKSPACE\tools\workflow_state.py" `
  -- status --state "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\state.json"
```

`workflow_state.py` schema 8 tạo thêm `approval_manifest.json` trong cùng run workspace. Đây là audit mirror cho hash danh mục cài đặt và phê duyệt riêng từng bước. Mọi lệnh `approve-install-plan`, `approve-step`, `install-mark` và `mark` phải chạy qua `run-workflow` trên đúng binding. Không tự sửa/tạo lại approval manifest, không bỏ qua lệnh approve, và không thực thi cài đặt/bước sản xuất nếu helper trả lỗi `NOT_APPROVED`, `HASH_MISMATCH` hoặc `APPROVAL_MANIFEST_MISMATCH`.

## 5. Khi mất kết nối, đổi máy hoặc đường dẫn không còn đúng

- Nếu một lệnh timeout/lỗi kết nối: dừng thao tác ghi và chuyển trạng thái BLOCKED. Poll kết quả chỉ bằng đúng `call_id` ban đầu và cùng `link_id`; `get_tool_result` không có trường `deviceId` vì nó đọc kết quả của call đã được gắn với thiết bị khi khởi chạy. Không gửi lại lệnh trên máy khác. Không khởi tạo lại lệnh có tác dụng phụ khi `call_id` cũ còn pending.
- Chỉ được gọi `list_devices` lại với **cùng `link_id`** để xem đúng `deviceId` đã chọn có online trở lại hay không. Nếu đúng ID đó online, xác minh lại machine fingerprint và binding rồi mới tiếp tục.
- Nếu `deviceId` biến mất, thay đổi, hoặc một máy cùng tên xuất hiện với ID khác: không tự chọn máy mới. Dừng và yêu cầu người dùng chọn lại máy. Lượt cũ không được chuyển sang máy mới.
- Nếu machine fingerprint khác, dù `deviceId` hoặc tên hiển thị giống nhau, BLOCKED.
- Nếu `VIDEO_ROOT`/`LOGO_ROOT` không tồn tại, canonical path đổi, quyền truy cập thay đổi hoặc binding mismatch: BLOCKED. Không tìm thư mục tương tự ở nơi khác.
- Chỉ người dùng mới có thể yêu cầu đổi máy, tài khoản hoặc folder. Việc đổi tạo một lượt mới và binding mới; không chuyển state, PID, cache, file tạm hoặc output của lượt cũ sang máy khác.
- Không xóa manifest/lock để "sửa nhanh". Chỉ tạo binding mới trong lượt mới sau khi người dùng chọn lại.

## 6. Dữ liệu phải mang theo binding

Ghi các trường sau trong `inputs.json`, `environment_report.json`, `state.json`, mọi QC report và `delivery_manifest.json`:

- `run_id`, `binding_id`
- `server_label`, `link_id`, `device_id`, `machine_fingerprint`
- `video_root`, `logo_root` (canonical)
- thời điểm xác minh cuối và trạng thái binding

Mọi báo cáo/artefact phải cùng `run_id` và `binding_id`. Nếu mismatch, đánh dấu STALE/BLOCKED; tuyệt đối không trộn artefact của lượt hoặc máy khác.


## Cổng thực thi v1.2.8 (quan trọng)
Lệnh `run-command` chỉ được dùng cho phase hợp lệ, ví dụ:

```powershell
python "<VIDEO_ROOT>\WORKSPACE\tools\server_binding.py" run-command `
  --binding-file "<VIDEO_ROOT>\WORKSPACE\runs\<RUN_ID>\server_binding.json" `
  --run-id "<RUN_ID>" --device-id "<DEVICE_ID>" --link-id "<LINK_ID>" `
  --video-root "<VIDEO_ROOT>" --logo-root "<LOGO_ROOT>" `
  --phase step --step 7 --cwd "<VIDEO_ROOT>\WORKSPACE" -- <EXECUTABLE> <ARGS>
```

Trên **Windows** ví dụ chỉ minh họa cấu trúc CLI, không có nghĩa có thể chạy: phiên bản này dừng `OS_WRITE_SANDBOX_UNAVAILABLE` nếu chưa có sandbox hệ điều hành hỗ trợ. Với Linux cần bubblewrap tin cậy, root mount read-only và WORKSPACE bind read-write. Không dùng `--phase` để giả mạo phê duyệt; wrapper kiểm tra state và approval.

Đối với `--phase install`, bắt buộc `--item-id` đúng mục đang RUNNING. `--phase preflight` chỉ có hiệu lực sau khi toàn bộ danh mục cài đặt PASS; `--phase repair --step N` chỉ cho blocker đang mở và phê duyệt khi rủi ro. Không thực thi lệnh tạo/ghi file bằng công cụ remote khác để né wrapper. Không được hứa cô lập filesystem trên Windows/macOS chưa được nghiệm thu.
