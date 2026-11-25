# Hợp đồng thực thi tuần tự và phê duyệt — không mở rộng phạm vi thư mục

## A. Luồng bắt buộc
1. Chọn máy chủ.
2. Nhận `VIDEO_ROOT` và `LOGO_ROOT` ngay sau khi chọn máy.
3. Xác minh hai thư mục và file đầu vào trên máy đã chọn.
4. Tự động tạo `VIDEO_ROOT/WORKSPACE` trên máy đã chọn; xác minh không phải symlink/junction, giữ nguyên nội dung cũ.
5. Khóa phạm vi: **chỉ ghi dưới `VIDEO_ROOT/WORKSPACE`**, chỉ đọc `LOGO_ROOT` và phim nguồn ở ngoài WORKSPACE.
6. Khảo sát cấu hình máy chủ và phần mềm.
7. Lập danh mục cài đặt đầy đủ, hiển thị phiên bản, hành động, target path, nguồn, dung lượng, thời gian, rủi ro và phép kiểm tra.
8. Dừng chờ người dùng phê duyệt **toàn bộ danh mục một lần**. Ghi approval gắn với `RUN_ID` và `plan_sha256`.
9. Sau khi duyệt, cài từng danh mục theo thứ tự, không hỏi duyệt lại từng package; mỗi mục vẫn phải PASS riêng.
10. Smoke test và preflight PASS.
11. Dừng chờ phê duyệt bước 01.
12. Mỗi lần chỉ thực hiện đúng một bước 01–40. Sau khi bước hiện tại PASS, báo cáo và dừng chờ duyệt bước kế tiếp.
13. Sau bước 20, dừng để chọn giọng; sau lựa chọn giọng vẫn phải duyệt riêng bước 21.
14. Thực hiện 8 QC tại đúng vị trí. Không tự đăng YouTube.


Không khảo sát/cài đặt trước khi nhận đủ thư mục. Không tự tạo workspace ngoài `VIDEO_ROOT`.

## B. Quy tắc phạm vi
- `VIDEO_ROOT/WORKSPACE` là write-root duy nhất; các file nguồn bên ngoài WORKSPACE chỉ đọc. Không ghi ra ngay gốc VIDEO_ROOT ngoài tạo thư mục WORKSPACE. Tất cả output, state, log, cache, temp, venv, portable tools và final nằm trong WORKSPACE.
- `LOGO_ROOT` là read-only. Không ghi, tạo, sửa, xóa hoặc đổi tên file tại đây.
- Video nguồn trong `VIDEO_ROOT` là read-only; output phải ở workspace con.
- Không ghi ra bất kỳ đường dẫn nào khác, kể cả Desktop, Documents, Downloads, home, `/tmp`, system folders, sandbox hoặc thư mục cạnh.
- Phần mềm hệ thống chỉ được kiểm tra/đọc. Không cài global, sửa PATH/registry, cài driver hoặc thay đổi cấu hình hệ thống.
- Mọi cache/temp phải được chuyển vào `VIDEO_ROOT/WORKSPACE/`. Nếu không kiểm soát được nơi ghi, BLOCKED.
- Mỗi lệnh phải có working directory và output path rõ ràng trong `VIDEO_ROOT/WORKSPACE`. Trước khi chạy, kiểm tra đường dẫn đã resolve không trỏ ra ngoài root.

## C. Cổng phê duyệt và chống chạy vượt bước

### C1. Danh mục cài đặt
- `set-install-plan` chỉ ghi danh sách và hash, không tự cấp quyền cài đặt.
- Danh mục phải thể hiện mọi package/model/tool cần cài hoặc cập nhật; phân biệt mục đã có tương thích và mục thật sự cần cài.
- Sau khi hiển thị danh mục, dừng. Chỉ một xác nhận rõ ràng của người dùng mới được gọi `approve-install-plan --user-approved --plan-sha256 <hash>`.
- `install-mark --status running` bị từ chối nếu chưa có approval hợp lệ. Approval phải khớp hash của snapshot danh mục. Thay đổi nội dung plan trước khi cài sẽ reset approval về PENDING.
- Sau khi được duyệt, cài tất cả danh mục đã liệt kê theo thứ tự, không cần hỏi lại từng package. Không thêm package ngoài danh sách. Nếu phát sinh package mới, dừng, cập nhật danh sách, xin duyệt hash mới.
- Preflight không được PASS nếu danh mục chưa được duyệt, hash không khớp hoặc còn item chưa PASS.

### C2. Mỗi bước sản xuất
- Bước hiện tại phải được người dùng duyệt riêng bằng `approve-step --step N --user-approved` trước khi chuyển sang RUNNING.
- Mỗi phê duyệt chỉ mở khóa đúng một bước; approval được gắn với `RUN_ID`, server/folder binding và bằng chứng của bước trước.
- Không được gọi `mark --status running` nếu không có approval cho đúng bước. Khi bước PASS, approval được đánh dấu consumed và không thể tái sử dụng cho bước khác.
- Sau PASS, chỉ được hiển thị báo cáo và nút duyệt bước kế tiếp. Không tự gọi lệnh chạy bước kế tiếp trong cùng phản hồi.
- Bước 01 cũng cần một nút duyệt sau preflight PASS. Không tự động bắt đầu bước 01.
- Bước 21 chỉ có thể được duyệt sau khi bước 20 PASS và người dùng đã chọn giọng; việc chọn giọng không tự duyệt bước 21.
- Bước 40 là cuối; không tạo nút 41.
- Nếu người dùng không bấm nút/không gửi câu phê duyệt rõ ràng, giữ nguyên trạng thái chờ. “Tiếp tục” chung chung không đủ để mở khóa.

### C3. Nút phê duyệt trong ChatGPT
- Hiển thị đúng một nút tương tác thật cho hành động đang chờ; nút gửi token `REVIEW_PHIM_APPROVE_INSTALL_PLAN <RUN_ID> <PLAN_SHA256>` hoặc `REVIEW_PHIM_APPROVE_STEP <RUN_ID> <STEP_2_DIGITS>`.
- Nút cài đặt có nghĩa là phê duyệt toàn bộ danh mục đã hiển thị; nút bước có nghĩa là phê duyệt duy nhất bước kế tiếp.
- Nếu host không hỗ trợ button, cung cấp đúng token làm fallback; không giả vờ có nút. Kiểm tra RUN_ID/hash/bước trước khi gọi helper.
- Không tạo nhiều nút cho các bước tương lai, không có nút “duyệt tất cả 40 bước”.

## D. Kỷ luật tuần tự
- Chỉ chạy một bước hoặc một thành phần cài đặt tại một thời điểm.
- Không chạy song song, không batch package, không chuẩn bị trước artefact của bước sau.
- Ghi log/evidence trong workspace hiện tại. Chỉ PASS sau khi kiểm tra nội dung và artefact.
- PARTIAL, RUNNING, STALE và BLOCKED đều khóa bước sau.
- Không dùng checkpoint, state, lựa chọn giọng hoặc kết quả của phiên trước để bỏ qua bước. Mỗi lần gọi Production là run mới.

## E. BLOCKED và sửa chữa
1. Dừng ngay ở đúng thành phần/bước lỗi.
2. Hiển thị lỗi, exit code, log và bằng chứng.
3. Nêu nguyên nhân đã xác minh, giả thuyết, đề xuất sửa, lệnh cụ thể, rủi ro và tiêu chí PASS.
4. Đề xuất sửa phải nằm trong `VIDEO_ROOT`; không tự sửa ngoài thư mục.
5. Chỉ xin duyệt khi thao tác sửa có rủi ro, ghi đè/xóa, tải lớn hoặc chi phí. Không thực hiện thay đổi hệ thống.
6. Sửa từng thao tác một, kiểm tra lại. Nếu lỗi còn, giữ BLOCKED và đưa đề xuất mới.
7. Chạy lại toàn bộ kiểm tra của mục/bước hiện tại. Chỉ khi PASS mới được mở nút phê duyệt cho bước tiếp theo.

### Mẫu báo cáo BLOCKED
- Trạng thái: BLOCKED — Preflight/Step N
- Lỗi và bằng chứng/log
- Nguyên nhân đã xác minh / giả thuyết
- Đề xuất sửa ưu tiên và phương án thay thế
- Lệnh/thao tác, rủi ro, thời gian/dung lượng
- Phê duyệt cần hay không
- Tiêu chí xác nhận PASS
- Bước sẽ tiếp tục: chính bước đang lỗi, không phải bước kế tiếp

## F. Skip
Chỉ skip khi thực sự không áp dụng và người dùng xác nhận rõ (ví dụ bỏ logo thì không thực hiện overlay logo). Không skip lỗi kỹ thuật, thiếu package, timeout, thiếu quyền hoặc chưa tìm ra nguyên nhân.


## G. Hợp đồng thực thi 1.2.8 — fail closed
- Sau bind, cổng `server_binding.py run-command` bắt buộc `--phase install|preflight|step|repair`, `--item-id` cho install hoặc `--step` cho step/repair. State phải đúng máy/thư mục, hash kế hoạch tệp nguồn không thay đổi, trạng thái đúng RUNNING, approval đã được tiêu thụ đúng bước.
- Chỉ Linux có binary bubblewrap hệ thống và có mount namespace hoạt động được phép chạy lệnh bên trong sandbox read-only root + bind RW `WORKSPACE`. Không có sandbox tương thích thì BLOCKED; **không chạy fallback không sandbox**.
- Sau khi phát sinh blocker medium/high/critical, phải hiển thị đề xuất sửa rồi nhận phê duyệt đúng `blocker_id` bằng `approve-repair` trước khi thực hiện lệnh sửa.
- Không SKIPPED bước chưa được phê duyệt; các bước 09/16/20/24/28/32/36/39 không được SKIPPED. `qc-mark` cần report có ít nhất hai phép kiểm tra, file evidence ở WORKSPACE và hash.
- Một khi bắt đầu cài, nếu thêm phụ thuộc mới phải hoàn thành/khôi phục item hiện tại, giữ mục đã PASS, lập lại kế hoạch có mục mới và duyệt hash mới. Phê duyệt cũ không cấp quyền cho phụ thuộc mới.


## G. Phân bổ thời lượng và sửa kịch bản có phê duyệt (v1.2.9)
- Trong một run, trước bước 20 phải lập mục tiêu thời lượng phim riêng và chứng minh độ bao phủ cốt truyện theo `references/SCRIPT_DURATION.md`. Không mặc định review 7–9 phút.
- QC3 phải kiểm tra `editorial_audit` từ kịch bản và hồ sơ sự kiện thật; QC4 phải kiểm tra `tts_duration_audit` từ WAV PCM thật. Thiếu hoặc sai không được PASS. Không lách bằng filler, tốc độ TTS bất thường hoặc outro kéo dài.
- Nếu cần quay lại bước 16 hoặc 17, chỉ gọi `reopen-editorial` sau khi người dùng phê duyệt rõ, ghi lý do và evidence. Lượt cũ được ghi lịch sử, các bước từ điểm quay lại trở đi bị reset, toàn bộ approvals và QC liên quan hết hiệu lực, bắt buộc chờ duyệt từng bước lại.
- Không cho phép thay đổi file đã QC3 rồi âm thầm qua QC4/5/8; kiểm tra lại SHA256 và thời lượng WAV thực.
