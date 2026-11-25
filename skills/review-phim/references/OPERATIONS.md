# Vận hành Review-Phim — phạm vi thư mục là bắt buộc

## 1. Thứ tự khởi động duy nhất
1. Liệt kê máy chủ Remote Desktop Commander và chờ người dùng chọn.
2. Ngay sau khi chọn máy, nhận `VIDEO_ROOT` và `LOGO_ROOT` (hoặc xác nhận không dùng logo).
3. Xác minh hai thư mục và file đầu vào trên đúng máy.
4. Chỉ sau đó mới khảo sát phần cứng/phần mềm, đề xuất cấu hình và cài đặt.
5. Khi preflight đạt, chạy 40 bước và 8 QC.

Không được đảo thành khảo sát/cài đặt trước rồi mới hỏi thư mục. Không hỏi thêm profile hoặc yêu cầu người dùng tạo JSON.

## 2. Ranh giới đọc/ghi
- `VIDEO_ROOT`: thư mục phim người dùng chọn. Đây là gốc ghi duy nhất.
- `LOGO_ROOT`: thư mục logo người dùng chọn. Chỉ đọc file ảnh; không tạo/sửa/xóa/ghi file trong đó.
- Phim nguồn trong `VIDEO_ROOT` cũng chỉ đọc. File mới phải ghi vào workspace con.
- Mọi workspace, state, manifest, log, report, temp, cache, model cache, venv, portable binary, proxy, timeline, audio, phụ đề, thumbnail và final phải nằm dưới `VIDEO_ROOT`.
- Đường dẫn ví dụ: `VIDEO_ROOT/.review-phim/runs/<run_id>/` cho công việc; `VIDEO_ROOT/.review-phim/runtime/` cho venv/công cụ/cache được phép dùng chung sau khi xác minh lại.
- Không ghi vào thư mục home, Desktop, Documents, Downloads, `/tmp`, thư mục hệ thống, thư mục cha/kề, ổ đĩa khác hoặc sandbox. Không tạo workspace ở cạnh video folder.
- Chỉ truy vấn OS/hardware và đọc thông tin phiên bản phần mềm hệ thống ở chế độ read-only. Không cài global, sửa PATH/registry, cài driver/CUDA hệ thống hoặc dùng package manager hệ thống.
- Mọi tiến trình phải đặt working directory, output path, `TEMP`, `TMP`, `PIP_CACHE_DIR`, `HF_HOME`, `TORCH_HOME`, `XDG_CACHE_HOME` và cache liên quan bên trong `VIDEO_ROOT/.review-phim/`. Nếu ứng dụng không cho đổi cache/temp và có nguy cơ ghi ngoài phạm vi, dừng BLOCKED.
- `VIDEO_ROOT` và `LOGO_ROOT` nên là hai thư mục riêng, không lồng nhau. Nếu trùng/lồng nhau gây mơ hồ quyền ghi, hỏi người dùng chọn lại để giữ logo folder read-only.

## 3. Khảo sát sau khi đã chọn thư mục
Trên đúng máy đã chọn, kiểm tra theo thứ tự:
1. OS, phiên bản, kiến trúc, shell.
2. CPU, cores, RAM tổng/trống.
3. GPU, VRAM, driver/CUDA (chỉ đọc).
4. Dung lượng trống trên volume chứa `VIDEO_ROOT` và quyền ghi trong chính thư mục này.
5. Python/pip/venv; chỉ dùng global runtime ở chế độ đọc, không sửa.
6. FFmpeg/FFprobe/encoder/decoder; smoke test output trong workspace.
7. PyTorch/CTranslate2/Faster-Whisper/VieNeu-TTS và API/preset thực tế.
8. OpenCV/PySceneDetect/Pillow/SoundFile/MoviePy và module timeline/render.
9. Model/cache hiện có: chỉ đọc metadata; nếu tải model mới, lưu trong `VIDEO_ROOT/.review-phim/cache/`.

Ghi `environment_report.json` trong workspace của lượt hiện tại. Mỗi mục là `present`, `missing`, `incompatible`, `failed` hoặc `unverified`, có version và bằng chứng. Không lấy profile cũ làm bằng chứng.

## 4. Cấu hình và cài đặt
Trình bày tóm tắt cấu hình máy, thành phần đã có/thiếu, cấu hình đề xuất, danh sách cài theo thứ tự, dung lượng/thời gian/rủi ro. Không cài lại thành phần đã tương thích.

Thứ tự tham khảo, điều chỉnh theo OS và phần cứng nhưng luôn từng mục một:
1. Python runtime/venv bên trong `VIDEO_ROOT` nếu cần.
2. FFmpeg/FFprobe portable bên trong `VIDEO_ROOT` nếu chưa có bản dùng được.
3. PyTorch/CUDA package phù hợp trong venv nếu dùng GPU; driver hệ thống không được tự cài.
4. NumPy và thư viện nền.
5. CTranslate2/Faster-Whisper.
6. VieNeu-TTS.
7. OpenCV/PySceneDetect/Pillow/SoundFile/MoviePy.
8. Module timeline/render và helper.
9. Smoke test từng thành phần.

Cài từng thành phần một: RUNNING → cài trong phạm vi → kiểm tra version/import/API → test → lưu log/evidence → PASS. Chỉ PASS mới sang thành phần tiếp theo. Không cài global hoặc chạy pip hàng loạt. Nếu không thể cài trong thư mục đã chọn, BLOCKED và đề xuất cách xử lý; không tự mở rộng phạm vi.

## 5. Smoke test
- Python/venv: interpreter, import cơ bản.
- FFmpeg: decode đoạn nhỏ, encode test, ffprobe output.
- GPU: chỉ thử nếu driver/runtime tương thích; không tự thay đổi driver.
- ASR: load model và nhận dạng đoạn ngắn; cache trong VIDEO_ROOT.
- TTS: load engine, liệt kê preset thực tế, tạo audio test kỹ thuật ngắn.
- Vision/scene: đọc ảnh và detect scene trên clip ngắn.
- Workspace: ghi/đọc file test bên trong workspace; không ghi vào `LOGO_ROOT` hoặc ngoài `VIDEO_ROOT`.

## 6. Cấu trúc workspace
Tạo trong `VIDEO_ROOT`:
`VIDEO_ROOT/.review-phim/runs/<run_id>/{inputs,logs,reports,asr,frames,understanding,script,tts,timeline,preview,postproduction,delivery,youtube}`.

`VIDEO_ROOT/.review-phim/runtime/` có thể chứa venv, portable tools, temp và cache. Mỗi lần Production tạo run/state mới; không tìm checkpoint cũ để resume. Nếu dùng lại runtime trong cùng thư mục, phải kiểm tra version/API và smoke test lại trước khi dùng.

## 7. Điểm dừng
- Chọn máy chủ.
- Chọn hai thư mục ngay sau khi chọn máy.
- BLOCKED khi lỗi.
- Chọn giọng trước bước 21.

Không có điểm dừng duyệt một installation plan riêng cho những cài đặt an toàn, local và đã nằm trong yêu cầu của người dùng. Vẫn phải trình bày đề xuất; cần hỏi trước nếu phát sinh chi phí, tải lớn, ghi đè/xóa, hoặc yêu cầu thay đổi hệ thống/ngoài thư mục (mặc định không thực hiện).
