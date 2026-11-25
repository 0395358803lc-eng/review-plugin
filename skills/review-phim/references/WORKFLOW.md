# Quy trình chuẩn: 11 giai đoạn · 40 bước

## Khởi động — đã chọn thư mục trước khi vào 40 bước
Trước khi preflight và trước bước 01, luồng Production bắt buộc đã hoàn thành: chọn máy chủ → chọn `VIDEO_ROOT` (thư mục phim) → chọn `LOGO_ROOT` (thư mục logo hoặc xác nhận không dùng) → xác minh hai thư mục → khảo sát/cấu hình/cài đặt trong phạm vi đã chọn. Không hỏi hai thư mục sau preflight. Ngay sau khi chọn máy chủ và hai thư mục, tạo WORKSPACE tự động rồi mới bind, khảo sát và cài đặt. Không có lựa chọn chế độ hoạt động. Tất cả đầu ra của 40 bước phải nằm trong `VIDEO_ROOT/WORKSPACE/runs/<RUN_ID>/`; `LOGO_ROOT` chỉ đọc. Phim gốc và logo gốc không bị sửa.

Sau preflight PASS, dừng chờ người dùng phê duyệt bước 01. Với từng bước N, chỉ thực thi sau khi người dùng phê duyệt riêng bước N và chỉ khi bước N PASS mới hiển thị nút duyệt bước N+1. Thực hiện **đúng thứ tự 01–40**. Không chạy song song, không gộp lệnh qua nhiều bước, không chuẩn bị trước artefact của bước sau. Mỗi bước chỉ PASS sau khi đủ đầu ra và bằng chứng trong `VIDEO_ROOT/WORKSPACE`. Các bước 09/16/20/24/28/32/36/39 còn phải có QC report được đăng ký bằng `qc-mark` trước khi PASS. RUNNING/PARTIAL/BLOCKED/STALE không cho phép sang bước kế. Khi lỗi, dừng, hiển thị đề xuất sửa, sửa trong `VIDEO_ROOT`, xác minh lại bước hiện tại trước khi tiếp tục. Điểm dừng chọn giọng trước bước 21 là bắt buộc.

Mỗi bước ghi báo cáo có: mục tiêu, đầu vào đã xác minh, thao tác theo thứ tự, đầu ra thực tế, bằng chứng, phép kiểm tra, trạng thái và lỗi/giới hạn. Không đánh dấu PASS chỉ vì lệnh kết thúc với exit code 0.

## Giai đoạn 1 — Tiếp nhận và chuẩn bị (01–06)
01. Xác nhận lại `VIDEO_ROOT` và `LOGO_ROOT` đã chọn ở đầu lượt. Xác minh video nguồn hợp lệ trong `VIDEO_ROOT`, logo hợp lệ trong `LOGO_ROOT` (hoặc không dùng logo theo xác nhận). Nếu nhiều file mơ hồ, hỏi chọn. Không lấy đường dẫn từ lần trước hoặc thư mục khác.
02. Kiểm tra nguồn bằng ffprobe: streams, duration, fps/timebase, kích thước, audio/subtitle tracks, VFR/CFR và fingerprint (size, mtime, SHA256 nếu khả thi). Chỉ đọc nguồn; bảo toàn file gốc.
03. Xác minh/hoàn thiện workspace riêng cho run hiện tại **bên trong `VIDEO_ROOT/WORKSPACE`**, ví dụ `VIDEO_ROOT/WORKSPACE/runs/<run_id>/`; tạo inputs manifest, state, logs, reports và thư mục artefact. Không mở/tìm checkpoint cũ, không ghi đè dữ liệu cũ hoặc phim gốc.
04. Xác minh runtime thực tế dùng cho lượt này: Python/venv, FFmpeg/FFprobe, OpenCV, PySceneDetect, MoviePy, NumPy, SoundFile, Pillow, PyTorch và phiên bản thực tế. Mọi venv/output/log/cache đều ở trong `VIDEO_ROOT`.
05. Kiểm tra Faster-Whisper Large-v3 Turbo/Small, CTranslate2 và VieNeu-TTS; xác minh model cache, revision/hash/license khi biết, API/preset có thật và khả năng load. Cache phải nằm trong `VIDEO_ROOT/WORKSPACE`; không mặc định giọng sản xuất.
06. Chạy smoke test thực tế theo thứ tự: decode/encode nhỏ, import/infer ASR, load TTS và audio test kỹ thuật ngắn, scene detection và đọc/ghi workspace. Ghi lỗi, RAM/VRAM, thời gian. Không qua bước nếu công cụ thiết yếu chưa chạy. Kết quả TTS ở đây không phải lựa chọn giọng sản xuất.

## Giai đoạn 2 — Âm thanh và transcript (07–09)
07. Dùng FFmpeg giải mã đúng audio track lời thoại sang mono PCM 16 kHz; xác nhận track, timebase và độ dài. Ghi file trung gian trong workspace.
08. Faster-Whisper nhận dạng toàn bộ phim; chia chunk có overlap, VAD, word timestamps nếu phù hợp, dịch offset về timeline nguồn, bỏ trùng có căn cứ, giữ confidence/flags. Xuất JSON, TXT timed, SRT/VTT. Kiểm tra coverage, khoảng im lặng, timestamp hợp lệ, xử lý đủ chunk trong lượt hiện tại.
09. ChatGPT dịch toàn bộ transcript sang ngôn ngữ lời kể (mặc định Việt) theo batch; giữ ID/start/end/source text, đánh dấu chưa rõ/tên riêng/quảng cáo; kiểm tra đủ ID, không mất dòng, không gán timestamp từ nguồn thành timestamp từng từ tiếng Việt. Xuất song ngữ và báo cáo. QC1.

## Giai đoạn 3 — Hình ảnh (10–12)
10. Trích ảnh toàn phim theo mặc định 5 giây/ảnh, giữ timestamp thực, index và kích thước; kiểm tra coverage; không nhầm intro/credit với nội dung phim. Nếu user chỉ yêu cầu trích xuất, dừng tại đây.
11. ChatGPT nhìn tất cả ảnh qua bảng đủ rõ hoặc ảnh riêng; mô tả từng frame ID, vai trò nhân vật theo chứng cứ cốt truyện, hành động, bối cảnh, chữ liên quan, điểm chưa rõ. Lưu batch coverage.
12. Đối chiếu từng ảnh với cả hai transcript theo thời gian, lập visual_transcript_timeline và mạch truyện. Không tự động coi ảnh cạnh lời thoại là chứng minh người nói. QC2 tạm.

## Giai đoạn 4 — Hiệu đính hiểu phim (13–16)
13. Khoanh vùng lời thoại thiếu, confidence thấp, tên sai, hình ảnh/mạch truyện mâu thuẫn, cao trào và sự kiện chưa rõ.
14. Nhận dạng lại vùng đó bằng model phù hợp, chỉnh VAD/ngôn ngữ/chunk, giữ kết quả riêng, không ghi đè nguồn.
15. Trích ảnh bổ sung mặc định 1 giây/ảnh; vùng rất ngắn có thể mật hơn. ChatGPT đọc bảng có phụ đề đủ rõ, kiểm chứng thứ tự và đối chiếu lời thoại.
16. Xây dựng dossier đã hiệu đính: nhân vật, quan hệ, sự kiện, nguyên nhân/hậu quả, động cơ có căn cứ, cao trào, kết, chủ đề, timestamp chứng cứ và danh sách chưa rõ. QC2; không gọi là phụ đề hiệu đính hoàn toàn nếu chỉ xác minh vùng.

## Giai đoạn 5 — Kịch bản (17–20)
17. ChatGPT viết V1 bằng ngôi thứ ba từ dossier, dùng logic kể chuyện sáu bước (`EDITORIAL.md`); giữ mạch nhân quả, hook có thật, tránh đọc phụ đề máy móc. Không áp thời lượng cố định; điều chỉnh theo yêu cầu.
18. Tìm nguồn web: giới thiệu chính thức, tóm tắt, bài phân tích đáng tin bằng ngôn ngữ phù hợp; xác nhận đúng phim/phiên bản/năm. Lưu URL, ngày, đoạn căn cứ, tình trạng đọc được/bị chặn. Nếu không có web, báo chưa hoàn thành phần đối chiếu.
19. Đối chiếu nguồn ngoài với phim; sửa lỗi, bổ sung tình tiết xác thực; ưu tiên phim gốc khi mâu thuẫn, đánh dấu chưa giải quyết. Không lấy bài báo thay kịch bản chính thức.
20. Trau chuốt V2: nhịp, tên riêng, ngôi kể, chuyển tiếp, hook/kết, lược lặp, chuẩn bị văn bản thuần TTS; giữ V1 và audit nguồn. QC3.

## Giai đoạn 6 — Giọng đọc (21–24)
**Dừng bắt buộc trước bước 21:** sau bước 20/QC3, lưu kết quả của lượt hiện tại. Kiểm tra VieNeu-TTS trên chính máy đã chọn, lấy danh sách preset thực tế bằng API của phiên bản đã cài. Hiển thị danh sách giọng khả dụng và hỏi người dùng chọn giọng/cách đọc. Không tạo giọng sản xuất, không thực hiện bước 21–40 trước khi nhận lựa chọn rõ ràng. Không mặc định Trúc Ly hoặc tái dùng giọng của phim/kênh khác.
21. Chia V2 theo đoạn/câu và giới hạn engine thực; lưu ID và nguyên văn; chuẩn hóa phát âm riêng nhưng giữ nội dung.
22. TTS dùng đúng preset do người dùng chọn tại điểm dừng, trên thiết bị đã xác minh. Nếu preset không khả dụng, BLOCKED, hiển thị đề xuất sửa/các preset thực tế và chờ lựa chọn; không tự thay giọng. Lưu WAV từng đoạn/master, gap phù hợp, timeline chính xác. Kiểm tra tín hiệu, NaN, clipping, sample rate/duration.
23. ASR ngược bằng Large-v3 Turbo và Small (hoặc model thay thế đã được duyệt), đối chiếu từ/cụm, chuẩn hóa số và dấu câu; phân biệt ASR lỗi với TTS lỗi.
24. Tạo lại đoạn có dấu hiệu sai, so sánh bản cũ/mới, chọn bản có bằng chứng tốt hơn; lưu candidate, báo cáo sai khác, ghép Final, cập nhật word/paragraph timeline. QC4. Không coi ASR là nghe trực tiếp.

## Giai đoạn 7 — Timeline hình ảnh (25–28)
25. Chia lời đọc Final theo đơn vị ngữ nghĩa nhỏ; căn bằng timestamp từ, interpolate vùng không khớp và gắn cờ; đủ nội dung, timeline liên tục.
26. Phát hiện ranh giới cảnh qua FFmpeg hoặc PySceneDetect đã kiểm tra; proxy/threshold linh hoạt, không coi detector là chính xác tuyệt đối. Tạo database shot + mô tả/ảnh.
27. ChatGPT chọn cảnh cho từng đơn vị bằng hiểu biết phim và ảnh chứng cứ; ưu tiên hành động trực tiếp > phản ứng > nguyên nhân/bối cảnh > chuyển tiếp > minh họa chung. Không chọn bằng keyword-only hoặc ngẫu nhiên.
28. Tính source in/out, review in/out theo frame, speed/transition; kiểm tra clip hợp lệ, liên tục, độ dài, reuse, cross-cut; xuất JSON/CSV và HTML preview. QC5.

## Giai đoạn 8 — Dựng và kiểm duyệt (29–32)
29. Dựng thử đoạn hook, lấy ảnh đầu/giữa/cuối, đối chiếu lời kể, sửa sai rồi mới dựng rộng.
30. Render proxy toàn timeline bằng codec khả dụng; kiểm tra số frame mỗi clip, concat, audio duration, giải mã. Không trộn thoại gốc lấn lời đọc; giữ nguồn.
31. ChatGPT kiểm tra trực quan clip bị cờ: cross-cut, reuse, timing, sai nhân vật, chữ quảng cáo, nhảy cảnh; ghi retain/revise/verify và lý do. Lấy ảnh nguồn bổ sung nếu cần.
32. Kiểm tra mọi clip còn lại; chỉnh điểm cắt có căn cứ, render lại bản V2 riêng, kiểm tra lại ảnh đầu/giữa/cuối của các clip đã chỉnh; QC6. Nếu có thể xem/nghe liên tục, kiểm tra thêm và ghi đúng phương pháp. Không tuyên bố làm khi chỉ nhìn still.

## Giai đoạn 9 — Hậu kỳ (33–36)
33. Tạo phụ đề theo lời kể Final, timecode từ ASR căn chỉnh; SRT/ASS và cue manifest; không chồng lấn, dễ đọc, đủ nguyên văn.
34. Kiểm tra loại subtitle (rời/ghi cứng); remove stream hoặc crop/mask/inpaint được phép và kiểm chứng; xử lý cả chữ dọc/ngang ở vùng khác; không xóa chữ bối cảnh/logo/credit nhầm. Kiểm tra trước/sau; báo phần hình mất. Giữ kích thước/tỷ lệ theo yêu cầu hoặc thông số phù hợp.
35. Tạo/nhận nhạc nền riêng có quyền sử dụng, nhẹ, không lời; có thể dùng hòa âm nguyên bản tổng hợp bằng code, không dùng bản nhạc nhận diện được nếu chưa có quyền. Giữ stem riêng, fade.
36. Cân giọng/nhạc, đo LUFS/true peak, duck, chống clipping; lưu narration master, music original/ducked, mix; đủ thời lượng. QC7. Nếu không nghe được thì ghi rõ.

## Giai đoạn 10 — Xuất và logo (37–39)
37. Render chất lượng nguồn hoặc yêu cầu đầu ra đã nêu, frame-count chính xác, codec/GPU đã kiểm tra. Tách layer, giữ tệp timeline và log.
38. ffprobe/giải mã đầy đủ, xác minh tổng frame/audio, cue midpoint và các điểm nối có phụ đề; sửa nháy bằng reset PTS/đặt tpad trước ASS hoặc render subtitle toàn timeline; kiểm tra lại sau sửa. Khảo sát phụ đề sót, báo mức độ bao phủ. Chốt Final kỹ thuật, không ghi đè bản trước.
39. Dùng đúng file ảnh logo từ `LOGO_ROOT` đã xác minh ở đầu lượt, giữ tỷ lệ/alpha, mặc định góc trên trái và kích thước tương đối; kiểm tra mẫu đầu/giữa/cuối. Logo nguồn chỉ đọc; mọi bản render có logo phải nằm trong `VIDEO_ROOT`. Không thêm logo giả khi thiếu. Chỉ skip logo nếu user nói rõ không dùng logo; nếu file mất hoặc sai, BLOCKED và đề xuất sửa đầu vào, không dùng logo khác. QC8.

## Giai đoạn 11 — Bộ nội dung YouTube (40)
40. Chuẩn bị tiêu đề thu hút nhưng đúng phim, vài phương án; thumbnail 16:9, đúng dấu tiếng Việt, kiểm tra hiển thị; mô tả, CTA trung tính nếu chưa biết tên kênh, hashtag liên quan, thông tin phim đã kiểm chứng, ghi spoiler/quyền tư liệu phù hợp. Dùng ảnh được phép hoặc sáng tạo riêng. Lưu text/thumbnail và nguồn trong `VIDEO_ROOT`. Không đăng tự động; chỉ xuất bản khi user yêu cầu rõ và có kết nối, kiểm tra quyền và lựa chọn kênh. Không hứa tránh Content ID hoặc đảm bảo kiếm tiền. Giao final + stems + metadata + báo cáo.
