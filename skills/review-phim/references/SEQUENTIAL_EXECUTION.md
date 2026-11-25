# Hợp đồng thực thi tuần tự — không mở rộng phạm vi thư mục

## A. Luồng bắt buộc
1. Chọn máy chủ.
2. Hỏi/nhận thư mục phim `VIDEO_ROOT` và thư mục logo `LOGO_ROOT` ngay sau khi chọn máy.
3. Xác minh hai thư mục và file đầu vào trên máy đã chọn.
4. Khóa phạm vi: chỉ ghi dưới `VIDEO_ROOT`; chỉ đọc `LOGO_ROOT`; nguồn video cũng chỉ đọc.
5. Khảo sát cấu hình máy chủ và phần mềm.
6. Đề xuất cấu hình; cài từng thành phần một, tất cả trong `VIDEO_ROOT`.
7. Smoke test và preflight PASS.
8. Thực hiện bước 01–40 đúng thứ tự; dừng trước bước 21 để chọn giọng.
9. Thực hiện 8 QC tại đúng vị trí.

Không được khảo sát/cài đặt trước khi nhận đủ thư mục. Không được hỏi thư mục sau preflight. Không tự tạo workspace ngoài `VIDEO_ROOT`.

## B. Quy tắc phạm vi
- `VIDEO_ROOT` là write-root duy nhất. Tất cả output, state, log, cache, temp, venv, portable tools và final nằm bên trong nó.
- `LOGO_ROOT` là read-only. Không ghi, tạo, sửa, xóa hoặc đổi tên file tại đây.
- Video nguồn trong `VIDEO_ROOT` là read-only; output phải ở workspace con.
- Không ghi ra bất kỳ đường dẫn nào khác, kể cả Desktop, Documents, Downloads, home, `/tmp`, system folders, sandbox hoặc thư mục cạnh.
- Phần mềm hệ thống chỉ được kiểm tra/đọc. Không cài global, sửa PATH/registry, cài driver hoặc thay đổi cấu hình hệ thống.
- Mọi cache/temp phải được chuyển vào `VIDEO_ROOT/.review-phim/`. Nếu không kiểm soát được nơi ghi, BLOCKED.
- Mỗi lệnh phải có working directory và output path rõ ràng trong `VIDEO_ROOT`. Trước khi chạy, kiểm tra đường dẫn đã resolve không trỏ ra ngoài root.

## C. Kỷ luật tuần tự
- Chỉ chạy một bước hoặc một thành phần cài đặt tại một thời điểm.
- Không chạy song song, không batch package, không chuẩn bị output của bước sau.
- Ghi log/evidence trong workspace hiện tại. Chỉ PASS sau khi kiểm tra nội dung và artefact.
- PARTIAL, RUNNING, STALE và BLOCKED đều khóa bước kế tiếp.
- Không dùng checkpoint, state, lựa chọn giọng hoặc kết quả của phiên trước để bỏ qua bước. Mỗi lần gọi Production là run mới.

## D. BLOCKED và sửa chữa
1. Dừng ngay ở đúng thành phần/bước lỗi.
2. Hiển thị lỗi, exit code, log và bằng chứng.
3. Nêu nguyên nhân đã xác minh, giả thuyết, đề xuất sửa, lệnh cụ thể, rủi ro và tiêu chí PASS.
4. Đề xuất sửa phải nằm trong `VIDEO_ROOT`; không tự sửa ngoài thư mục.
5. Chỉ xin duyệt khi thao tác có rủi ro, ghi đè/xóa, tải lớn hoặc chi phí. Không thực hiện thay đổi hệ thống.
6. Sửa từng thao tác một, kiểm tra lại. Nếu lỗi còn, giữ BLOCKED và đưa đề xuất mới.
7. Chạy lại toàn bộ kiểm tra của bước hiện tại. Chỉ khi PASS mới sang bước tiếp.

### Mẫu báo cáo
- Trạng thái: BLOCKED — Preflight/Step N
- Lỗi và bằng chứng/log
- Nguyên nhân đã xác minh / giả thuyết
- Đề xuất sửa ưu tiên và phương án thay thế
- Lệnh/thao tác, rủi ro, thời gian/dung lượng
- Phê duyệt cần hay không
- Tiêu chí xác nhận PASS
- Bước sẽ tiếp tục: chính bước đang lỗi, không phải bước kế tiếp

## E. Skip
Chỉ skip khi thực sự không áp dụng và người dùng xác nhận rõ (ví dụ bỏ logo thì không thực hiện overlay logo). Không skip lỗi kỹ thuật, thiếu package, timeout, thiếu quyền hoặc chưa tìm ra nguyên nhân.
