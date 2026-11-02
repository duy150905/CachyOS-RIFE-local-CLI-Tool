# rife-cli

Video workflows for **CachyOS (Arch Linux)** built on `ffmpeg` and AI tools.
Each workflow is a subcommand (`rife-cli <tool>`); the first one is **RIFE frame interpolation**.
Needs Python 3.9+ only; no pip dependencies.

## Install

You need Python 3.9+, ffmpeg and a Vulkan-capable GPU (NVIDIA / AMD / Intel). No CUDA or PyTorch.

```bash
yay -S --needed python ffmpeg git vulkan-icd-loader vulkan-tools
yay -S vulkan-radeon     # AMD  (or: nvidia-utils for NVIDIA, vulkan-intel for Intel)
git clone https://github.com/duy150905/CachyOS-RIFE-local-CLI-Tool.git && cd CachyOS-RIFE-local-CLI-Tool
python -m rife_cli setup && python -m rife_cli doctor --test
```

`doctor` detects missing system libraries and prints the matching `yay -S` command.
Instead of `setup` you can install rife-ncnn-vulkan from the AUR: `yay -S rife-ncnn-vulkan-bin`.
For a `rife-cli` command instead of `python -m rife_cli`: `yay -S python-pipx && pipx install .`

## Usage

```bash
python -m rife_cli interpolate -i video.mp4                       # 30 -> 60 fps
python -m rife_cli interpolate -i anime.mp4 -m rife-anime         # animation model
python -m rife_cli interpolate -i clip.mp4 -x 4 --target-fps 60   # 4x then resample
python -m rife_cli interpolate -i wallpaper.mp4 --loop            # seamless loop
python -m rife_cli interpolate -i big.mp4 --frame-format jpg --workdir /mnt/data/tmp
```

Output fps = input fps x multiplier. Audio is kept unless `--no-audio`. See `interpolate -h` for all options.
Temporary frames need roughly 3x the size of the extracted frames for x2; the tool checks free space first.

## Adding tools

See [docs/adding-a-tool.md](docs/adding-a-tool.md). Tests use a fake RIFE binary, so CI needs no GPU (runs in an Arch container).

MIT licensed. Uses [rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan) (MIT), downloaded at setup time.
