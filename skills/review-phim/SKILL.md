---
name: review-phim
description: "Điều phối nghiên cứu và sản xuất review phim với khóa máy chủ/thư mục, một lần duyệt toàn bộ danh mục cài đặt và phê duyệt riêng từng bước trong quy trình 40 bước; 8 QC tuần tự, BLOCKED phải sửa và xác minh PASS."
---
# Review-Phim 1.2.8

## Nguyên tắc cốt lõi

**Một lượt Production = một máy chủ + một tài khoản kết nối + một thư mục video + một thư mục logo + một chuỗi phê duyệt có audit.** Sau khi người dùng chọn, các thông tin lựa chọn này bị khóa cho đến khi lượt kết thúc. Không tự chuyển máy, đổi account, thay folder, tìm đường dẫn tương tự hoặc dùng tài nguyên từ dự án khác.

Trước khi làm việc, bắt buộc đọc `references/SERVER_BINDING.md` và `references/WORKSPACE_LAYOUT.md`. SERVER_BINDING ưu tiên nhận diện máy chủ; WORKSPACE_LAYOUT ưu tiên phạm vi ghi dữ liệu và vị trí các file. Tiếp tục tuân thủ `references/OPERATIONS.md`, `references/SEQUENTIAL_EXECUTION.md`, `references/WORKFLOW.md`, `references/QUALITY.md`, `references/SCHEMAS.md` và `references/EDITORIAL.md`.

## 1. Bắt đầu trực tiếp — không chọn chế độ

- Khi người dùng gọi Review-Phim để làm video, bắt đầu ngay bằng **liệt kê/chọn máy chủ**. KHÔNG hiện bảng hoặc hỏi người dùng chọn Research / Production / Resume / QC / Delivery.
- Nếu yêu cầu chỉ là hỏi thông tin phim hoặc YouTube, trả lời trực tiếp câu hỏi; không bắt chọn chế độ và không tự triển khai sản xuất.
- Không lấy lựa chọn từ chat trước để thay cho lựa chọn máy chủ và hai thư mục trong lượt hiện tại.

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
2. Chọn video nguồn chỉ từ `VIDEO_ROOT` **nhưng phải loại trừ thư mục `WORKSPACE` và các bản dựng bên trong**; chọn logo chỉ từ `LOGO_ROOT`. Nếu có nhiều file mơ hồ, hỏi người dùng chọn. Không tìm file ở máy hoặc folder khác.
3. **Tự tạo `VIDEO_ROOT/WORKSPACE` ngay sau khi xác minh hai thư mục** bằng thao tác Remote Desktop Commander trên CHÍNH máy đã chọn; không cần hỏi thêm tên workspace. Nếu `WORKSPACE` đã có, kiểm tra là thư mục thật (không symlink/junction), giữ nguyên dữ liệu cũ, tuyệt đối không xóa hay ghi đè. Nếu không thể tạo/kiểm tra, BLOCKED.
4. Sinh `RUN_ID` mới. Tạo `WORKSPACE/tools`, `WORKSPACE/runtime`, `WORKSPACE/cache`, `WORKSPACE/tmp`, `WORKSPACE/runs/<RUN_ID>`. Sao chép helper của plugin vào `WORKSPACE/tools`; không copy sang các thư mục khác.
5. Chạy `server_binding.py bind` theo `references/SERVER_BINDING.md` trên đúng máy, truyền đúng `deviceId` và `link_id`; helper cũng xác minh/tạo WORKSPACE khi cần. Nếu bind hoặc fingerprint thất bại, BLOCKED.
6. Lưu `server_binding.json` trong `VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/`. Chỉ tiếp tục khi `status=bound` và `workspace_root` cũng khớp.
7. Bắt đầu khảo sát rồi cổng phê duyệt danh mục cài đặt; tuyệt đối không hỏi lại chọn chế độ.

## 3. Luật không nhầm máy — áp dụng cho MỌI thao tác

- Sau khi bind, **mọi Remote Desktop Commander call phải truyền rõ cùng `deviceId` và cùng `link_id`**. Không bỏ tham số dù chỉ có một máy online; không dùng thiết bị mặc định.
- Điều này áp dụng cho mọi thao tác đọc/ghi file, liệt kê thư mục, shell, cài đặt, process, polling, tương tác, dừng process và kiểm tra cấu hình.
- Không dùng PID/session trên thiết bị khác. Mọi `read_process_output`, `interact_with_process`, `kill_process`, `force_terminate` phải dùng đúng `deviceId` và `link_id` tạo process.
- Trước thao tác file trực tiếp hoặc truy vấn cấu hình, chạy `server_binding.py verify` trên đúng máy và xác nhận `status=verified`, đúng `binding_id`, `RUN_ID`, `deviceId`, `link_id`, `VIDEO_ROOT`, `LOGO_ROOT`. Với thao tác đọc/ghi, truyền `--read-path`/`--write-path` tương ứng.
- **Không bao giờ chạy subprocess trực tiếp** bằng Desktop Commander `start_process`, PowerShell, Python/cmd, kể cả để cài package; chỉ chạy qua `server_binding.py run-command --phase install|preflight|step|repair`. Vẫn dùng Remote Desktop Commander để gọi chính wrapper trên máy đã khóa. Trước khi được duyệt, chỉ được khảo sát read-only qua công cụ đọc, không chạy shell để dò cấu hình. `run-command` kiểm tra `state.json` đúng RUN_ID, phase, install item/step đang RUNNING, các manifest và hash kế hoạch.
- `run-command` trên Linux yêu cầu `bubblewrap` tin cậy và thực thi trong mount namespace có host root chỉ đọc và `WORKSPACE` là vị trí ghi duy nhất; nếu không khởi chạy được sandbox phải BLOCKED. Trên Windows/macOS phiên bản này **không có sandbox OS đủ tin cậy**, vì vậy lệnh sản xuất sẽ BLOCKED cho tới khi được cung cấp môi trường cô lập hỗ trợ. Không cho phép chế độ bỏ qua sandbox.
- Mọi lệnh shell chạy qua `server_binding.py run-command`; wrapper xác minh binding, working directory, input/output paths và đặt cache/temp dưới `VIDEO_ROOT/WORKSPACE`. Khai báo đầy đủ `--read-path`, `--write-path`, `--cwd`; command được chạy bằng argument list, không shell ngầm.
- Với state helper, chỉ gọi qua `server_binding.py run-workflow`; wrapper xác minh binding và tự truyền device/link/fingerprint/folder context vào `workflow_state.py`. Không gọi trực tiếp `workflow_state.py`.
- Không dùng Python/container cục bộ, filesystem của ChatGPT, Files/Library, browser download hoặc máy khác để xử lý dữ liệu Production. Plugin package có thể được đọc để sao chép helper, nhưng mọi dữ liệu và artefact Production phải được xử lý trên máy chủ đã khóa.
- Mọi action có tham số `deviceId` đều phải truyền đúng ID đã chọn. Ngoại lệ chỉ dành cho action polling gắn với `call_id` đã tạo trên máy đã khóa (ví dụ `get_tool_result`): dùng nguyên `call_id` và cùng `link_id`, không tạo call mới ở máy khác. `list_devices` không nhận `deviceId`, chỉ dùng lúc chọn máy hoặc kiểm tra lại đúng ID cũ bằng cùng `link_id`; không chọn thiết bị thay thế. Nếu action có thể thực thi trên thiết bị mà không có cách ràng buộc/đối chiếu thì không dùng cho Production.
- Tên hiển thị không phải khóa. Máy cùng tên nhưng `deviceId` khác là máy khác.

## 4. Luật không nhầm folder

- `VIDEO_ROOT/WORKSPACE` canonical là write-root duy nhất. `VIDEO_ROOT` ngoài WORKSPACE chỉ đọc phim nguồn. Tất cả output, state, cache, temp, venv, model, log và Final phải nằm bên trong.
- `LOGO_ROOT` canonical là read-only. Không tạo, sửa, xóa, đổi tên hoặc ghi file vào đây.
- Video nguồn và logo nguồn luôn chỉ đọc.
- Mọi đường dẫn phải là absolute canonical path; không dùng relative path, `~`, đường dẫn đoán hoặc path từ lịch sử chat.
- Trước khi ghi, `server_binding.py verify --write-path` phải xác nhận target nằm trong `VIDEO_ROOT/WORKSPACE` (KHÔNG chỉ kiểm tra VIDEO_ROOT). Trước khi đọc, `--read-path` được lấy phim từ `VIDEO_ROOT` và logo từ `LOGO_ROOT`.
- Symlink/junction trỏ ra ngoài root, root đổi, folder mất hoặc path fingerprint mismatch đều là BLOCKED. Không tự tìm folder khác cùng tên.
- Nếu người dùng đổi folder, dừng lượt hiện tại và tạo run mới với binding mới. Không trộn state hoặc artefact cũ.

## 5. Quy trình sản xuất và cổng phê duyệt

1. Khảo sát OS, CPU, RAM, GPU/VRAM, dung lượng, quyền và phần mềm trên đúng máy đã khóa.
2. Tạo `environment_report.json` và `installation_plan.json` trong `VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/`.
3. Liệt kê **toàn bộ danh mục cần cài/cập nhật** trong một bảng trước khi cài. Mỗi mục phải có: tên/danh mục, tình trạng hiện tại, phiên bản đích, hành động (cài/cập nhật/đã có-không cần cài), đường dẫn đích tuyệt đối trong `VIDEO_ROOT/WORKSPACE`, nguồn, dung lượng tải/dung lượng đĩa dự kiến, thời gian ước tính, mức rủi ro và phép kiểm tra sau cài. Không gộp các mục mơ hồ thành một dòng; không đưa package đã tương thích vào danh sách cài mà không ghi rõ `already_present`.
4. Ghi `installation_plan.json`, gọi `set-install-plan`, lấy `plan_sha256`, hiển thị danh sách cuối cùng và **dừng**. Hiển thị đúng một nút `Phê duyệt cài đặt toàn bộ danh mục` (hoặc câu xác nhận tương đương nếu host không hỗ trợ nút). Nút phải gửi lại `RUN_ID` và `plan_sha256`; chỉ sau khi người dùng bấm nút/đưa ra câu phê duyệt rõ ràng mới gọi `approve-install-plan --user-approved --plan-sha256 <hash>`. Không chạy bất kỳ lệnh cài đặt nào trước khi trạng thái APPROVED được ghi trong `approval_manifest.json`.
5. Sau khi kế hoạch được duyệt, cài **tất cả** mục đã duyệt theo thứ tự trong danh sách, mọi `target_path` nằm dưới `VIDEO_ROOT/WORKSPACE`. Không hỏi duyệt lại từng package. Mỗi package vẫn phải chạy riêng lẻ theo RUNNING → install → version/import/API/smoke test → evidence → PASS; chỉ PASS mới sang package kế. Nếu danh sách, phiên bản, nguồn, dung lượng hoặc đường dẫn đích thay đổi, phê duyệt cũ hết hiệu lực: cập nhật plan, tính hash mới, trình bày lại và xin duyệt lại trước khi cài tiếp.
6. Chạy smoke test tổng hợp và đánh dấu preflight PASS. Sau đó **không tự động bắt đầu bước 01**: hiển thị một nút `Phê duyệt thực hiện bước 01` và chờ.
7. Với mỗi bước 01–40: chỉ sau khi người dùng phê duyệt đúng bước hiện tại mới gọi `approve-step --step N --user-approved`, sau đó mới đánh dấu RUNNING và thực hiện đúng một bước. Không thực hiện bước tiếp theo trong cùng lượt thực thi. Khi bước hiện tại hoàn tất, kiểm tra output/evidence/QC, đánh dấu PASS, trình bày báo cáo rồi dừng với đúng một nút phê duyệt cho bước kế tiếp.
8. Sau bước 20/QC3, không hiển thị nút bước 21 ngay. Dừng để người dùng chọn preset giọng thực tế; sau khi lựa chọn được ghi nhận, hiển thị nút `Phê duyệt thực hiện bước 21`. Việc chọn giọng không tự động phê duyệt bước 21.
9. Các bước kết thúc QC1–QC8 (09, 16, 20, 24, 28, 32, 36, 39) phải tạo báo cáo QC JSON và gọi `qc-mark --gate K --report <path>` khi đang RUNNING, kiểm chứng report/evidence, rồi mới PASS. Không được SKIPPED các bước mang cổng QC.
10. Bước 40 là bước cuối, không tạo nút bước 41. Thực hiện 8 QC tại đúng vị trí trong `references/QUALITY.md`; bàn giao video và metadata, không tự đăng YouTube.

### 5.1. Giao diện nút phê duyệt trong ChatGPT

- Khi host hỗ trợ nút tương tác, hiển thị **một nút duy nhất** cho đúng hành động đang chờ. Nút gửi thông điệp xác nhận theo token chính xác: `REVIEW_PHIM_APPROVE_INSTALL_PLAN <RUN_ID> <PLAN_SHA256>` hoặc `REVIEW_PHIM_APPROVE_STEP <RUN_ID> <STEP_2_DIGITS>`. Không hiển thị nút giả chỉ để trang trí.
- Nút cài đặt chỉ phê duyệt toàn bộ danh mục trong đúng hash kế hoạch; nút bước chỉ phê duyệt đúng một bước kế tiếp. Không dùng một nút chung để phê duyệt nhiều bước.
- Sau khi hiển thị nút, dừng mọi công việc. Không tự gọi công cụ tiếp theo trong cùng phản hồi.
- Nếu giao diện hiện tại không hỗ trợ nút thật, hiển thị đúng token tương ứng để người dùng gửi lại; không giả vờ có nút và không hiểu từ “tiếp tục” chung chung là phê duyệt. Trước khi gọi helper, đối chiếu RUN_ID và hash/số bước trong token với state hiện hành.
- Sau mỗi bước PASS, báo cáo tối thiểu: bước vừa hoàn tất, đầu ra thực tế, đường dẫn trong `VIDEO_ROOT`, phép kiểm tra và bằng chứng, trạng thái QC, lỗi/giới hạn còn lại, bước kế tiếp đang chờ duyệt.
- Không gộp nhiều bước vào một lần thực thi, kể cả khi người dùng nói “tiếp tục”. Chỉ một lần phê duyệt rõ ràng mới mở khóa đúng một bước.

Mọi manifest, log, QC report và artefact phải ghi cùng `run_id`, `binding_id`, `deviceId`, `link_id`, machine fingerprint, `VIDEO_ROOT` và `LOGO_ROOT`. Không trộn file từ lượt/máy khác.

## 6. BLOCKED — không tự failover

Nếu máy chủ mất kết nối, `deviceId` đổi/mất, fingerprint không khớp, đường dẫn thay đổi hoặc binding verify thất bại:

1. Dừng ngay thao tác đang chạy; không tiếp tục ghi hoặc render.
2. Ghi lỗi và bằng chứng trong `VIDEO_ROOT` nếu máy vẫn truy cập được.
3. Hiển thị chẩn đoán, nguyên nhân đã xác minh/giả thuyết, phương án sửa, rủi ro, yêu cầu phê duyệt và tiêu chí kiểm tra. Lệnh sửa có rủi ro trung bình/cao/rất cao cần `approve-repair` cho đúng blocker_id trước khi chạy; lệnh sửa cũng phải đi qua sandbox và cổng `--phase repair`.
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

## WORKSPACE — nguồn sự thật duy nhất về vị trí ghi

- Bắt buộc đọc `references/WORKSPACE_LAYOUT.md` trước khi thao tác. Tài liệu này có ưu tiên cao nhất về cấu trúc WORKSPACE, ghi dữ liệu và giới hạn đường dẫn; supersede mọi ví dụ thư mục `.review-phim` còn ở tài liệu cũ.
- Dữ liệu sản xuất mới không ghi trong `.review-phim` hay thư mục ẩn khác ở VIDEO_ROOT. Không tự chuyển/migrate dữ liệu cũ vào WORKSPACE.
- Khi VIDEO_ROOT chứa nhiều phim, phải xác định đúng phim đang được chọn rồi mới sản xuất; không dùng dữ liệu từ phim khác.
- Giữ nguyên 1 lần duyệt danh mục cài đặt + 1 lần duyệt cho từng bước 01–40 + dừng chọn giọng sau bước 20; không tự chạy bước tiếp.
