# Tám tầng kiểm duyệt và xử lý lỗi

Mỗi QC gate lưu JSON/Markdown có `run_id`, gate, status, input/output fingerprints, phương pháp, phạm vi, metrics, issue IDs, evidence, quyết định sửa/giữ, giới hạn và thời gian kiểm tra. `pass` chỉ khi tiêu chí kỹ thuật và phạm vi công bố đạt; không có nghĩa chính xác tuyệt đối. `partial` không phải pass. `blocked` dừng quy trình. `stale` khi đầu vào thay đổi. `skipped` chỉ khi gate thật sự không áp dụng, có lý do và chấp thuận; không dùng để né lỗi.

| Cổng | Sau bước | Phạm vi và bằng chứng tối thiểu |
|---|---:|---|
| QC1 — Nhận dạng âm thanh | 09 | Stream/language đúng, mọi chunk có manifest, segment ID/timecode hợp lệ, không mất dòng khi dịch, khoảng im lặng và flags được ghi, nguồn không đổi. Kiểm tra số segment, timestamp và file đọc được. |
| QC2 — Hiểu phim | 16 | Coverage ảnh theo ID, transcript liên kết, vùng nghi vấn có kết quả hoặc lý do chưa xác minh. Dossier nhân vật/sự kiện/nguyên nhân/hậu quả, chứng cứ timecode, phân biệt diễn giải. |
| QC3 — Kịch bản | 20 | V1/V2 riêng; ngôi thứ ba, hook có thật, logic kể chuyện, trình tự hợp lý, không bịa động cơ/số liệu, tên thống nhất, nguồn web đọc được và có căn cứ phim. Lưu audit. |
| QC4 — Giọng đọc | 24 | User đã chọn giọng ở điểm dừng trước 21; preset thực tế đã xác minh; đủ segment và đúng text, tín hiệu/duration/sample rate/peak, ASR ngược và candidate có căn cứ. Nghe thực tế chỉ khi có khả năng. |
| QC5 — Timeline | 28 | Mỗi đơn vị lời kể có clip và lý do; source bounds hợp lệ, frame intervals liên tục, duration audio-video sai lệch trong dung sai một frame, reuse/cross-cut có cờ. |
| QC6 — Hình ảnh bản dựng | 32 | Ảnh đầu–giữa–cuối từng clip; batch/coverage; kiểm tra flagged và toàn bộ; clip sửa có ảnh từ render mới. Nêu rõ nếu không xem chuyển động liên tục. |
| QC7 — Hậu kỳ | 36 | Subtitle text đầy đủ, cue không overlap; mẫu trước/sau xử lý subtitle gốc; đo LUFS/true peak, track lengths, không clipping, music rights/original, ducking, stems. |
| QC8 — Thành phẩm | 39 | FFprobe codec/fps/width/height/duration/nb_frames và decode đầy đủ; frame count; cue midpoint và nối có chữ; logo đúng file; audio hash khi copy; source preserved, output path/bytes/SHA256. |

## Ngưỡng đề xuất
- Không bỏ sót ID hoặc clip không có timestamp; không có gap/overlap timeline trừ transition được mô hình hóa. Source in/out nằm trong duration nguồn. Sai lệch tổng thời lượng hình/tiếng tối đa một frame trừ padding codec được giải thích.
- Subtitle nguyên văn, tối đa 2 dòng, đủ thời lượng đọc; cue ngắn dưới 1s hoặc trên 25 ký tự/s phải rà soát. Không cắt sai câu để đạt ngưỡng. Kiểm tra dấu tiếng Việt.
- Nhạc nền dưới lời đọc; hướng tới voice -17 đến -19 LUFS, bed -30 đến -35 LUFS, peak bản phối <= -1 dBTP; điều chỉnh theo nội dung và đo thực.
- Cross-cut/reuse có chủ ý có thể giữ nếu có lý do rõ. Không coi ASR là nghe thật.

## Quy trình thất bại — bắt buộc BLOCKED và sửa trước khi đi tiếp
Khi bất kỳ kiểm tra nào thất bại:
1. Dừng ngay ở preflight/bước/QC hiện tại. Không khởi chạy bước sau.
2. Lưu log, exit code, phiên bản, input/output fingerprint và phạm vi ảnh hưởng.
3. Hiển thị báo cáo: lỗi; bằng chứng; nguyên nhân đã xác minh/giả thuyết; đề xuất sửa ưu tiên; phương án khác; lệnh/thao tác; rủi ro; cần phê duyệt hay không; tiêu chí xác nhận.
4. Không sửa thay đổi phá hủy, ghi đè, thay đổi hệ thống, tải lớn hoặc phát sinh chi phí nếu chưa duyệt.
5. Thực hiện từng thay đổi một. Sau sửa, chạy lại test lỗi và kiểm tra hồi quy liên quan.
6. Nếu không đạt, giữ BLOCKED, cập nhật nguyên nhân và đề xuất sửa mới.
7. Nếu đạt, ghi evidence và chạy lại kiểm tra đầy đủ của bước hiện tại. Chỉ khi bước hiện tại PASS mới được đi tiếp.

Không tự chuyển máy, tự đổi model, tự hạ chất lượng, tự bỏ QC hoặc chấp nhận hạn chế thay người dùng. Nếu người dùng chủ động chấp nhận một hạn chế, ghi rõ phạm vi, rủi ro và trạng thái `accepted_with_limitations`; chỉ cho qua nếu tiêu chí QC cho phép và không làm sai tuyên bố kết quả. Không coi kiểm tra kỹ thuật là xác nhận quyền sử dụng/đủ điều kiện kiếm tiền YouTube.
