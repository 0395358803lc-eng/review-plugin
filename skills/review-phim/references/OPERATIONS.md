# Vận hành Review-Phim 1.2.9 — phạm vi thư mục và phê duyệt bắt buộc

## 1. Thứ tự khởi động duy nhất
1. Liệt kê máy chủ Remote Desktop Commander và chờ người dùng chọn.
2. Ngay sau khi chọn máy, nhận `VIDEO_ROOT` và `LOGO_ROOT` (hoặc xác nhận không dùng logo).
3. Xác minh hai thư mục và file đầu vào trên đúng máy.
4. **Tự động tạo `VIDEO_ROOT/WORKSPACE` trên đúng máy, không hỏi người dùng chọn nơi lưu**, xác minh là thư mục thật, không link/junction. Đặt tools/runtime/cache/tmp/runs bên trong.
5. Chỉ sau đó mới khảo sát phần cứng/phần mềm, đề xuất cấu hình và cài đặt.
6. Hoàn thành preflight rồi mới mở bước 01; bước 01 cũng cần một phê duyệt riêng.

Không được đảo thành khảo sát/cài đặt trước rồi mới hỏi thư mục. Khi chọn phim gốc, phải loại trừ mọi file bên trong `WORKSPACE`. Không hỏi thêm profile hoặc yêu cầu người dùng tạo JSON.

## 2. Ranh giới đọc/ghi
- `VIDEO_ROOT`: thư mục phim người dùng chọn, chỉ đọc nguồn. Chỉ cho phép tạo thư mục `WORKSPACE` ở đây; mọi ghi tiếp theo phải nằm bên trong `VIDEO_ROOT/WORKSPACE`.
- `VIDEO_ROOT/WORKSPACE`: thư mục duy nhất để cài phần mềm local và lưu mọi sản phẩm; không ghi file ra phần còn lại của VIDEO_ROOT.
- `LOGO_ROOT`: thư mục logo người dùng chọn. Chỉ đọc file ảnh; không tạo/sửa/xóa/ghi file trong đó.
- Phim nguồn trong `VIDEO_ROOT` cũng chỉ đọc. File mới phải ghi vào workspace con.
- Mọi state, manifest, log, report, temp, cache, model cache, venv, portable binary, proxy, timeline, audio, phụ đề, thumbnail và final phải nằm dưới `VIDEO_ROOT/WORKSPACE`.
- Đường dẫn ví dụ: `VIDEO_ROOT/WORKSPACE/runs/<run_id>/` cho công việc; `VIDEO_ROOT/WORKSPACE/runtime/` cho venv/công cụ/cache được phép dùng chung sau khi xác minh lại.
- Không ghi vào thư mục home, Desktop, Documents, Downloads, `/tmp`, thư mục hệ thống, thư mục cha/kề, ổ đĩa khác hoặc sandbox. Không tạo workspace ở cạnh video folder.
- Chỉ truy vấn OS/hardware và đọc thông tin phiên bản phần mềm hệ thống ở chế độ read-only. Không cài global, sửa PATH/registry, cài driver/CUDA hệ thống hoặc dùng package manager hệ thống.
- Mọi tiến trình phải đặt working directory, output path, `TEMP`, `TMP`, `PIP_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME` và cache liên quan bên trong `VIDEO_ROOT/WORKSPACE/`. Nếu ứng dụng không cho đổi cache/temp và có nguy cơ ghi ngoài phạm vi, dừng BLOCKED.
- `VIDEO_ROOT` và `LOGO_ROOT` nên là hai thư mục riêng, không lồng nhau. Nếu trùng/lồng nhau gây mơ hồ quyền ghi, hỏi người dùng chọn lại để giữ logo folder read-only.

## 3. Khảo sát sau khi đã chọn thư mục
Trên đúng máy đã chọn, kiểm tra theo thứ tự:
1. OS, phiên bản, kiến trúc, shell.
2. CPU, cores, RAM tổng/trống.
3. GPU, VRAM, driver/CUDA (chỉ đọc).
4. Dung lượng trống trên volume chứa `VIDEO_ROOT` và quyền tạo `WORKSPACE` trong thư mục phim và quyền ghi trong `WORKSPACE`.
5. Python/pip/venv; chỉ dùng global runtime ở chế độ đọc, không sửa.
6. FFmpeg/FFprobe/encoder/decoder; smoke test output trong workspace.
7. PyTorch/CTranslate2/Faster-Whisper/VieNeu-TTS và API/preset thực tế.
8. OpenCV/PySceneDetect/Pillow/SoundFile/MoviePy và module timeline/render.
9. Model/cache hiện có: chỉ đọc metadata; nếu tải model mới, lưu trong `VIDEO_ROOT/WORKSPACE/cache/`.

Ghi `environment_report.json` trong workspace của lượt hiện tại. Mỗi mục là `present`, `missing`, `incompatible`, `failed` hoặc `unverified`, có version và bằng chứng. Không lấy profile cũ làm bằng chứng.

## 4. Kế hoạch cài đặt — một lần duyệt toàn bộ danh mục
Trước khi cài, tạo một danh sách hoàn chỉnh. Mỗi mục phải ghi:
- ID, tên và nhóm chức năng.
- Tình trạng hiện tại và phiên bản hiện có.
- Hành động: cài mới, cập nhật, hoặc đã có/không cần cài.
- Phiên bản đích và nguồn tải/phân phối.
- Đường dẫn cài đặt tuyệt đối dưới `VIDEO_ROOT/WORKSPACE`.
- Dung lượng tải, dung lượng đĩa dự kiến, thời gian ước tính.
- Rủi ro, phụ thuộc và phép kiểm tra sau cài.

Danh mục tham khảo (chỉ đưa mục thực sự cần cài vào hàng đợi cài đặt):
1. Python runtime/venv trong `VIDEO_ROOT`.
2. FFmpeg/FFprobe portable trong `VIDEO_ROOT`.
3. PyTorch/CUDA package tương thích trong venv (không cài driver hệ thống).
4. NumPy và thư viện nền.
5. CTranslate2/Faster-Whisper và model ASR.
6. VieNeu-TTS, engine và model/voice resources cần thiết.
7. OpenCV/PySceneDetect/Pillow/SoundFile/MoviePy.
8. Module timeline/render, helper và công cụ phụ trợ.
9. Smoke test từng thành phần và kiểm tra tích hợp.

Lưu `installation_plan.json`, đăng ký bằng `set-install-plan`, lấy `plan_sha256`, hiển thị danh sách và dừng chờ một lần phê duyệt toàn bộ. Không cài trước khi `approve-install-plan --user-approved --plan-sha256 <hash>` thành công và approval manifest đã được ghi. Nếu có 0 mục cần cài, vẫn hiển thị trạng thái “không cần cài thêm” và yêu cầu người dùng duyệt để xác nhận danh sách rỗng trước khi hoàn tất preflight.

Sau khi được duyệt, cài tất cả mục theo thứ tự; không hỏi duyệt lại từng package. Mỗi mục phải RUNNING → cài → kiểm tra version/import/API/smoke test → evidence → PASS. Chỉ PASS mới sang mục kế tiếp. Nếu kế hoạch thay đổi về tên, phiên bản, nguồn, dung lượng, rủi ro, hành động hoặc target path, hash thay đổi và phê duyệt cũ mất hiệu lực; phải trình bày lại toàn bộ danh sách và xin duyệt lại. Không cài global hoặc chạy pip hàng loạt. Nếu không thể cài trong thư mục đã chọn, BLOCKED và đề xuất cách xử lý; không tự mở rộng phạm vi.

## 5. Smoke test
- Python/venv: interpreter, import cơ bản.
- FFmpeg: decode đoạn nhỏ, encode test, ffprobe output.
- GPU: chỉ thử nếu driver/runtime tương thích; không tự thay đổi driver.
- ASR: load model và nhận dạng đoạn ngắn; cache trong VIDEO_ROOT/WORKSPACE.
- TTS: load engine, liệt kê preset thực tế, tạo audio test kỹ thuật ngắn.
- Vision/scene: đọc ảnh và detect scene trên clip ngắn.
- Workspace: ghi/đọc file test bên trong workspace; không ghi vào `LOGO_ROOT` hoặc ngoài `VIDEO_ROOT`.

## 6. Cấu trúc workspace
Tạo trong `VIDEO_ROOT`:
`VIDEO_ROOT/WORKSPACE/runs/<run_id>/{inputs,logs,reports,asr,frames,understanding,script,tts,timeline,preview,postproduction,delivery,youtube}`.

`VIDEO_ROOT/WORKSPACE/runtime/` chứa venv và portable tools; `VIDEO_ROOT/WORKSPACE/cache` và `tmp` chứa cache/temp, không dùng cache ngoài WORKSPACE. Mỗi lần Production tạo run/state mới; không tìm checkpoint cũ để resume. Nếu dùng lại runtime trong cùng thư mục, phải kiểm tra version/API và smoke test lại trước khi dùng.

## 7. Cổng phê duyệt từng bước sản xuất
- Sau preflight PASS, không tự chạy bước 01. Hiển thị một nút phê duyệt bước 01 và dừng.
- Mỗi lần chỉ được phê duyệt và chạy một bước hiện tại. Trước khi chạy bước N, ghi `approve-step --step N --user-approved` trong state helper.
- Khi bước N PASS, lưu evidence và báo cáo, sau đó hiển thị một nút duy nhất để phê duyệt bước N+1. Không tự chạy N+1 trong cùng lượt.
- Sau bước 20/QC3, bắt buộc dừng để người dùng chọn giọng. Sau khi chọn giọng, vẫn cần nút riêng để phê duyệt bước 21.
- Sau bước 40, không hiển thị nút bước tiếp theo.
- Nút trong ChatGPT phải là control tương tác thật gửi lại `RUN_ID` và bước/hash đúng. Nếu host không hỗ trợ, hiển thị câu xác nhận chính xác. Không hiểu “tiếp tục” chung chung là phê duyệt.

## 8. BLOCKED và sửa chữa
Khi có lỗi: dừng đúng mục/bước hiện tại; hiển thị lỗi, exit code, log, bằng chứng, nguyên nhân đã xác minh/giả thuyết, phương án sửa, rủi ro, cần duyệt hay không và tiêu chí PASS. Không tự failover hoặc đổi folder. Thực hiện sửa từng thao tác một; chạy lại toàn bộ kiểm tra của mục/bước hiện tại. Chỉ PASS mới mở khóa hành động kế tiếp. Nếu sửa đổi làm thay đổi kế hoạch cài đặt, phải xin duyệt lại hash mới.


## 9. An toàn thực thi và kiểm chứng
- Không chạy lệnh production khi chưa có phê duyệt thực sự và chưa bắt đầu đúng item/bước. Không gọi shell/Python trực tiếp bỏ qua wrapper. Xem `EXECUTION_SECURITY.md`.
- Không sandbox OS → BLOCKED thay vì chạy unsafe, kể cả đã duyệt. Windows/macOS cần một executor cô lập được triển khai và nghiệm thu riêng; v1.2.8 hiện chưa có executor đó.
- Một phần mềm đã có vẫn phải chạy kiểm chứng phiên bản/import/smoke test trước khi đánh dấu PASS; không auto-pass từ trường `already_present`.
- Mỗi QC 01–08 phải có report JSON riêng với checks thật và evidence files đã hash. Thiếu hoặc report thay đổi → không PASS.
- Nếu cần bổ sung package sau khi hoàn thành các mục đầu tiên, giữ nguyên prefix đã PASS, ghi danh sách đã sửa, tính hash mới, báo cáo và xin duyệt lại trong cùng RUN_ID. Không sửa mục đã hoàn tất hoặc thay đổi danh mục khi một item còn RUNNING.


## 10. Kiểm soát thời lượng kịch bản theo từng phim
- Trước khi viết V1, không mặc định 7–9 phút. Bắt buộc đọc `references/SCRIPT_DURATION.md` rồi tạo danh mục sự kiện nguồn (bước 16) và bản phân bổ thời lượng/word target riêng phim (bước 17). Nếu người dùng yêu cầu số phút thì dùng số đó, không tự đổi.
- QC3 (bước 20) chạy kiểm tra tài liệu thực qua `qc-mark --gate 3` với `editorial_audit`; tình tiết required bị bỏ sót, trích dẫn không tồn tại, hoặc số từ dự kiến quá ngắn so với mục tiêu đều không được PASS.
- QC4 (bước 24) đo WAV thật qua `tts_duration_audit` trước khi dựng; ngắn/dài bất thường phải đề xuất sửa kịch bản hoặc thời lượng và xin duyệt `reopen-editorial --from-step 16|17` khi cần, không vượt bước.
- Bước 25–39 phải giữ đủ lời kể đã đạt QC4. Đo duration timeline và Final bằng dữ liệu thực, không cắt ngắn theo số phút quen thuộc.
