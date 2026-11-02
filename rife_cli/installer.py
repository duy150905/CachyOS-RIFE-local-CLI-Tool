"""`rife-cli setup` - download rife-ncnn-vulkan (binary + models) for the current OS."""
from __future__ import annotations

import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import common
from .common import RifeCliError

RIFE_TAG = "20221029"
BASE_URL = "https://github.com/nihui/rife-ncnn-vulkan/releases/download"

NAME = "setup"
HELP = "Download rife-ncnn-vulkan (with models) into the rife-cli home folder."


def asset_url() -> str:
    if not common.IS_LINUX:
        raise RifeCliError(f"Unsupported platform: {sys.platform} (this tool targets CachyOS / Linux).")
    # The "ubuntu" asset is a plain glibc binary; it also runs on CachyOS/Arch.
    return f"{BASE_URL}/{RIFE_TAG}/rife-ncnn-vulkan-{RIFE_TAG}-ubuntu.zip"


def add_arguments(p) -> None:
    p.add_argument("--force", action="store_true", help="re-download even if already installed")
    p.add_argument("--url", help="use a different zip (e.g. a newer fork build)")


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(dest, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    sys.stderr.write(f"\r  {done / 1e6:6.1f} / {total / 1e6:.1f} MB")
            sys.stderr.write("\n")
    except OSError as exc:
        raise RifeCliError(f"Download failed: {exc}\n  Check your connection, or download the zip manually "
                           "and extract it to the folder shown by `rife-cli doctor`.")


def run(args) -> int:
    dest = common.rife_home()
    exe = dest / "rife-ncnn-vulkan"
    if exe.is_file() and not args.force:
        print(f"Already installed: {exe}\n(use --force to reinstall)")
        return 0

    url = args.url or asset_url()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "rife.zip"
        _download(url, archive)
        extract_to = tmp_path / "extract"
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract_to)
        except zipfile.BadZipFile:
            raise RifeCliError("The downloaded file is not a valid zip archive.")

        # The zip contains a single top-level folder; find the one holding the executable.
        candidates = [p for p in extract_to.rglob("rife-ncnn-vulkan") if p.is_file()]
        if not candidates:
            raise RifeCliError("rife-ncnn-vulkan executable not found inside the archive.")
        root = candidates[0].parent
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(root), str(dest))

    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"Installed to {dest}")
    missing = common.missing_shared_libs(str(exe))
    if missing:
        print(f"\nWARNING: missing system libraries: {', '.join(missing)}\n"
              f"  Fix: {common.shared_lib_hint(missing)}")
    print("Models: " + ", ".join(common.list_models(str(exe))))
    print("Next: python -m rife_cli doctor --test")
    return 0
