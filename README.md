# rife-cli

Bộ quy trình xử lý video chạy trên **CachyOS (Arch Linux)**, dựa trên `ffmpeg` và các công cụ AI.
Mỗi quy trình là một lệnh con (`rife-cli <tool>`); hiện có nội suy khung hình bằng **RIFE**.
Chỉ cần Python 3.9+, không phải `pip install` thư viện nào.

*English: see [README.en.md](README.en.md).*

## Cài đặt

Cần: **Python 3.9+**, **ffmpeg**, GPU hỗ trợ **Vulkan** (NVIDIA, AMD, Intel đều được; không cần CUDA hay PyTorch).

```bash
yay -S --needed python ffmpeg git vulkan-icd-loader vulkan-tools
# cài thêm driver Vulkan đúng với GPU của bạn:
#   AMD:    yay -S vulkan-radeon
#   NVIDIA: yay -S nvidia-utils        (CachyOS Hello / chwd thường đã cài sẵn)
#   Intel:  yay -S vulkan-intel
git clone https://github.com/duy150905/CachyOS-RIFE-local-CLI-Tool.git
cd CachyOS-RIFE-local-CLI-Tool
python -m rife_cli setup                # tải rife-ncnn-vulkan (kèm model)
python -m rife_cli doctor --test        # kiểm tra, gồm chạy thử trên GPU
```

`vulkaninfo --summary` phải liệt kê GPU của bạn. `rife-cli doctor` cũng tự phát hiện thiếu thư viện
(vd. `libvulkan.so.1`) và in đúng lệnh `yay -S` cần chạy. Bản build Linux của rife-ncnn-vulkan là
binary glibc chuẩn nên chạy được trên CachyOS; CI cũng kiểm thử trên container Arch.

Thay cho `python -m rife_cli setup`, có thể cài rife-ncnn-vulkan từ AUR: `yay -S rife-ncnn-vulkan-bin`
(file nằm ở `/usr/bin` và `/usr/share/rife-ncnn-vulkan`, `rife-cli` tự tìm thấy ở đó).

Tuỳ chọn: để có lệnh `rife-cli` thay cho `python -m rife_cli`, cài `yay -S python-pipx` rồi chạy
`pipx install .` (hoặc dùng venv, do PEP 668 chặn `pip install` trực tiếp).

## Dùng nhanh

```bash
# 30fps -> 60fps
python -m rife_cli interpolate -i video.mp4

# hoạt hình + chỉ định file ra
python -m rife_cli interpolate -i anime.mp4 -o anime_60.mp4 -m rife-anime

# x4 (hai lượt RIFE), 48fps -> 192fps rồi hạ về 60fps
python -m rife_cli interpolate -i clip.mp4 -x 4 --target-fps 60

# video nền lặp vô hạn: nối mượt từ khung cuối về khung đầu
python -m rife_cli interpolate -i wallpaper.mp4 --loop

# tiết kiệm ổ đĩa: khung tạm dạng jpg, thư mục tạm ở ổ khác
python -m rife_cli interpolate -i big.mp4 --frame-format jpg --workdir /mnt/data/tmp
```

Âm thanh gốc được giữ (bỏ bằng `--no-audio`). Tốc độ khung đầu ra = fps gốc × hệ số (30→60, 24→48...).
Chạy `python -m rife_cli interpolate -h` để xem toàn bộ tuỳ chọn.

### Chọn model

| Model | Phù hợp |
|---|---|
| `rife-v4.6` (mặc định) | phim, video đời thực, nói chung |
| `rife-anime` | anime / hoạt hình |
| `rife-UHD` hoặc thêm `--uhd` | video 4K |

Liệt kê model đã cài: `python -m rife_cli doctor`.

## Cách hoạt động

```
video ──ffprobe──> fps
      ──ffmpeg───> khung PNG ──rife-ncnn-vulkan (x2 mỗi lượt)──> khung PNG ──ffmpeg──> video + âm thanh gốc
```

Khung tạm nằm cạnh file đầu ra (không đặt trong `/tmp` vì CachyOS/Arch mặc định mount `/tmp` bằng tmpfs (RAM)) và được xoá sau khi xong.
Dung lượng tạm xấp xỉ **3× tổng dung lượng khung gốc** cho x2 (vd. 884 khung 1080p PNG ~ 4,5 GB); chương trình sẽ báo nếu không đủ chỗ.

## Xử lý sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| `ffmpeg not found` | cài ffmpeg (xem trên) hoặc đặt biến `RIFE_CLI_FFMPEG` |
| `rife-ncnn-vulkan not found` | `python -m rife_cli setup` (hoặc `yay -S rife-ncnn-vulkan-bin`), hoặc đặt `RIFE_NCNN_VULKAN=/đường/dẫn/exe` |
| `doctor --test` lỗi Vulkan / không thấy GPU | `yay -S vulkan-icd-loader vulkan-tools` + `vulkan-radeon` / `nvidia-utils` / `vulkan-intel`, rồi `vulkaninfo --summary`. Máy hybrid (iGPU + dGPU): chọn GPU bằng `-g 0` hoặc `-g 1` |
| `error while loading shared libraries: libvulkan.so.1` | `yay -S vulkan-icd-loader` |
| `pip install` báo `externally-managed-environment` | `yay -S python-pipx` rồi `pipx install .`, hoặc `python -m venv .venv`; hoặc bỏ qua, dùng `python -m rife_cli` |
| Hình bị méo/ghosting ở cảnh chuyển động nhanh | thử model khác (`rife-v4.6` ↔ `rife-anime`), đây là giới hạn chung của nội suy |
| Video gốc là VFR | chương trình sẽ cảnh báo; chuyển sang CFR trước: `ffmpeg -i in.mp4 -vf fps=30 cfr.mp4` |

Biến môi trường: `RIFE_CLI_HOME` (nơi lưu công cụ tải về), `RIFE_CLI_MODELS` (thư mục chứa model), `RIFE_CLI_FFMPEG`, `RIFE_CLI_FFPROBE`, `RIFE_NCNN_VULKAN`.

## Thêm tool mới vào repo

Xem [docs/adding-a-tool.md](docs/adding-a-tool.md): mỗi tool chỉ là một file Python nhỏ trong `rife_cli/tools/`.

## Phát triển

```bash
python -m unittest discover -s tests -v
```

CI chạy trên container Arch Linux (nền tảng của CachyOS).

## Ghi công & giấy phép

MIT. Dùng [rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan) (MIT) của nihui, bản triển khai ncnn của [RIFE](https://github.com/hzwer/ECCV2022-RIFE); và [FFmpeg](https://ffmpeg.org).
Các file này không được đóng gói sẵn trong repo, `rife-cli setup` tải trực tiếp từ GitHub Releases của họ.
