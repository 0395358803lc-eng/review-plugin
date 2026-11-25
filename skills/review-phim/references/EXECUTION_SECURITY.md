# Execution Security — Review-Phim 1.2.8

## Mục tiêu
Không cho chạy lệnh shell khi chưa duyệt kế hoạch cài đặt hoặc chưa duyệt đúng bước; không chấp nhận việc tự khai báo đường dẫn ghi thay cho sandbox OS; mọi file host được tạo trong `VIDEO_ROOT/WORKSPACE`.

## Các lớp cổng
1. Remote Desktop Commander phải chỉ tới `link_id` + `deviceId` đã khóa. `server_binding.py` verify machine fingerprint, VIDEO_ROOT, LOGO_ROOT, WORKSPACE và RUN_ID.
2. `workflow_state.py` xác nhận `phase` và trạng thái: install cần approval plan đúng hash và item RUNNING; preflight chỉ khi plan approved và tất cả items PASS; step N chỉ khi approval riêng consumed và N RUNNING; repair chỉ khi blocker còn mở và các trường hợp rủi ro đã duyệt blocker_id.
3. So lại SHA256 file `installation_plan.json` với giá trị đã ghi; bất kỳ thay đổi nào (kể cả thay whitespace) đều chặn thao tác tiếp theo cho tới khi đăng ký lại và duyệt.
4. Linux: lệnh thực thi qua trusted system bubblewrap, mount read-only root `/` và chỉ bind rw `WORKSPACE`, unshare mount namespace và tiến trình. Nếu bubblewrap vắng/hỏng hoặc namespace không khởi tạo được, BLOCKED.
5. Windows/macOS: **không có executor sandbox đáng tin trong phiên bản này**. `run-command` từ chối thực thi `OS_WRITE_SANDBOX_UNAVAILABLE`. Cần thiết kế và nghiệm thu sandbox cấp OS riêng; tuyệt đối không fallback shell trực tiếp.

## Lệnh mẫu trên Linux (sau khi có binding và approval)
```bash
python3 "$VIDEO_ROOT/WORKSPACE/tools/server_binding.py" run-command \
  --binding-file "$VIDEO_ROOT/WORKSPACE/runs/$RUN_ID/server_binding.json" \
  --run-id "$RUN_ID" --device-id "$DEVICE_ID" --link-id "$LINK_ID" \
  --video-root "$VIDEO_ROOT" --logo-root "$LOGO_ROOT" \
  --phase step --step 7 --cwd "$VIDEO_ROOT/WORKSPACE" \
  --write-path "$VIDEO_ROOT/WORKSPACE/runs/$RUN_ID/asr/audio.wav" \
  -- ffmpeg -i "$VIDEO_ROOT/movie.mp4" -ac 1 -ar 16000 "$VIDEO_ROOT/WORKSPACE/runs/$RUN_ID/asr/audio.wav"
```

## Thiếu và giới hạn bảo đảm
- Thực thi với helper copied trên server, không phải dịch vụ bảo vệ bất biến; đối tượng có quyền admin hoặc cố tình gọi raw shell qua connector có thể bypass. Đây là chính sách cho tác nhân, không phải ranh giới bảo mật chống chủ máy ác ý.
- Không thể tự xác minh chữ ký sự kiện UI khi nhận `--user-approved`. Tác nhân phải lấy token phê duyệt từ thông điệp của người dùng và khớp RUN_ID/hash/bước trước khi gọi.
- QC report kiểm tra định dạng và hash evidence, nhưng các check `passed` là do quy trình QC thực hiện, chưa thay thế kiểm toán độc lập nguồn video.
- Mọi lệnh đọc thông tin trước phê duyệt nên dùng công cụ read-only có đối chiếu deviceId; không chạy shell trực tiếp.
