# Adding a new tool

Every workflow is a small module in `rife_cli/tools/`. Example: a video upscaler.

```python
# rife_cli/tools/upscale.py
from .. import common

NAME = "upscale"
HELP = "Upscale a video with Real-ESRGAN."

def add_arguments(p):
    p.add_argument("-i", "--input", required=True)
    p.add_argument("-o", "--output")

def run(args) -> int:
    ffmpeg, ffprobe = common.require_ffmpeg()
    ...                      # use common.run_checked([...], "what failed")
    return 0
```

Register it in `rife_cli/tools/__init__.py`:

```python
from . import interpolate, upscale
TOOLS = [interpolate, upscale, installer, doctor]
```

It is then available as `python -m rife_cli upscale ...` and shows up in `--help`.
Raise `common.RifeCliError("message")` for expected problems; it is printed without a traceback.
Add a test in `tests/` (use a fake executable so CI needs no GPU), then open a PR.

Ideas: `upscale` (Real-ESRGAN), `dedupe` (remove duplicate frames), `loop`,
`stabilize`, `denoise`, `compress` (HEVC/AV1 presets).
