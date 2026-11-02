"""`rife-cli doctor` - check that every dependency is available."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from . import common

NAME = "doctor"
HELP = "Check ffmpeg, rife-ncnn-vulkan, models and (optionally) run a GPU smoke test."


def add_arguments(p) -> None:
    p.add_argument("--test", action="store_true",
                   help="run RIFE on two generated frames to prove the GPU works")
    p.add_argument("--model", default="rife-v4.6", help="model used by --test")


def _line(ok: bool, label: str, detail: str) -> None:
    print(f"  [{'ok' if ok else '!!'}] {label:<22} {detail}")


def run(args) -> int:
    problems = 0
    print(f"rife-cli home: {common.home_dir()}")
    print(f"Python {sys.version.split()[0]} on {common.platform_label()}\n")

    ffmpeg, ffprobe = common.find_ffmpeg(), common.find_ffprobe()
    for label, path in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        if path:
            ver = common.capture([path, "-version"]).stdout.splitlines()[:1]
            _line(True, label, f"{path}  ({ver[0] if ver else '?'})")
        else:
            _line(False, label, f"missing -> {common.ffmpeg_install_hint()}")
            problems += 1

    rife = common.find_rife()
    if rife:
        _line(True, "rife-ncnn-vulkan", rife)
    else:
        _line(False, "rife-ncnn-vulkan", "missing -> python -m rife_cli setup  (or: yay -S rife-ncnn-vulkan-bin)")
        problems += 1

    if rife:
        missing = common.missing_shared_libs(rife)
        if missing:
            _line(False, "shared libraries", f"missing {', '.join(missing)} -> {common.shared_lib_hint(missing)}")
            problems += 1

    models = common.list_models(rife)
    if models:
        _line(True, "models", ", ".join(models))
    else:
        _line(False, "models", "none found -> python -m rife_cli setup")
        problems += 1

    vulkaninfo = shutil.which("vulkaninfo")
    if vulkaninfo:
        out = common.capture([vulkaninfo, "--summary"]).stdout
        gpus = [l.split("=", 1)[1].strip() for l in out.splitlines() if "deviceName" in l and "=" in l]
        if gpus:
            _line(True, "Vulkan GPUs", "; ".join(gpus))
        else:
            _line(False, "Vulkan GPUs", f"none reported -> {common.vulkan_install_hint()}")
            problems += 1
    else:
        _line(True, "Vulkan GPUs", f"vulkaninfo not installed (skipped; use --test, or: {common.vulkan_install_hint()})")

    if args.test:
        if problems:
            print("\nFix the problems above before running --test.")
            return 1
        problems += _smoke_test(ffmpeg, rife, args.model)

    print("\nAll good." if not problems else f"\n{problems} problem(s) found.")
    return 1 if problems else 0


def _smoke_test(ffmpeg: str, rife: str, model: str) -> int:
    print("\nSmoke test: interpolating 2 generated frames...")
    model_dir = common.find_model(model, rife)
    with tempfile.TemporaryDirectory(prefix="rife-cli-doctor-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "in").mkdir()
        (tmp_path / "out").mkdir()
        common.run_checked([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=256x144:rate=2",
                            "-frames:v", "2", str(tmp_path / "in" / "%08d.png")], "ffmpeg")
        common.run_checked([rife, "-i", str(tmp_path / "in"), "-o", str(tmp_path / "out"),
                            "-m", str(model_dir)], "rife-ncnn-vulkan")
        produced = len(list((tmp_path / "out").glob("*.png")))
    ok = produced == 4
    _line(ok, "RIFE inference", f"{produced} frames produced (expected 4)")
    return 0 if ok else 1
