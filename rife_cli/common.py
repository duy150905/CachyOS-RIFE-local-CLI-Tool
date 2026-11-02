"""Shared helpers: locating external tools, running commands, probing videos."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

IS_LINUX = sys.platform.startswith("linux")


class RifeCliError(RuntimeError):
    """An expected, user-facing error (printed without a traceback)."""


# --------------------------------------------------------------------------- platform
def linux_release() -> dict:
    """Parsed /etc/os-release ({} when unavailable)."""
    if not IS_LINUX:
        return {}
    info: dict = {}
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if "=" in line and not line.lstrip().startswith("#"):
                        key, value = line.rstrip("\n").split("=", 1)
                        info[key] = value.strip().strip('"').strip("'")
            break
        except OSError:
            continue
    return info


def platform_label() -> str:
    """Human-readable OS name for `rife-cli doctor`."""
    import platform
    name = linux_release().get("PRETTY_NAME") or "Linux"
    return f"{name} ({platform.machine()})"


# --------------------------------------------------------------------------- paths
def home_dir() -> Path:
    """Where rife-cli stores downloaded tools. Override with $RIFE_CLI_HOME."""
    env = os.environ.get("RIFE_CLI_HOME")
    if env:
        return Path(env).expanduser()
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "rife-cli"


def rife_home() -> Path:
    return home_dir() / "rife-ncnn-vulkan"


# --------------------------------------------------------------------------- tool lookup
def _from_env(env_var: str) -> Optional[str]:
    value = os.environ.get(env_var)
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_file():
        raise RifeCliError(f"${env_var} points to '{value}', which is not a file.")
    return str(path)


def find_tool(name: str, env_var: Optional[str] = None, extra_dirs: Iterable[Path] = ()) -> Optional[str]:
    if env_var:
        found = _from_env(env_var)
        if found:
            return found
    found = shutil.which(name)
    if found:
        return found
    for d in extra_dirs:
        cand = Path(d) / name
        if cand.is_file():
            return str(cand)
    return None


def ffmpeg_install_hint() -> str:
    return "yay -S ffmpeg"


def vulkan_install_hint() -> str:
    """How to get a working Vulkan driver on CachyOS."""
    return ("yay -S vulkan-icd-loader vulkan-tools  plus the driver for your GPU: "
            "vulkan-radeon (AMD) | nvidia-utils (NVIDIA) | vulkan-intel (Intel)")


def find_ffmpeg() -> Optional[str]:
    return find_tool("ffmpeg", "RIFE_CLI_FFMPEG", [home_dir() / "bin"])


def find_ffprobe() -> Optional[str]:
    ff = find_ffmpeg()
    sibling = [Path(ff).parent] if ff else []
    return find_tool("ffprobe", "RIFE_CLI_FFPROBE", sibling + [home_dir() / "bin"])


def require_ffmpeg() -> tuple:
    ffmpeg, ffprobe = find_ffmpeg(), find_ffprobe()
    if not ffmpeg or not ffprobe:
        raise RifeCliError(
            "ffmpeg/ffprobe not found in PATH.\n"
            f"  Install it with:  {ffmpeg_install_hint()}\n"
            "  or set $RIFE_CLI_FFMPEG / $RIFE_CLI_FFPROBE to the executables."
        )
    return ffmpeg, ffprobe


def _system_rife_dirs() -> List[Path]:
    # /usr/share/rife-ncnn-vulkan is where the AUR package rife-ncnn-vulkan-bin puts the models.
    return [rife_home(), Path.cwd() / "rife-ncnn-vulkan", Path("/usr/share/rife-ncnn-vulkan"),
            Path("/usr/local/share/rife-ncnn-vulkan"), Path("/opt/rife-ncnn-vulkan")]


def find_rife() -> Optional[str]:
    return find_tool("rife-ncnn-vulkan", "RIFE_NCNN_VULKAN", _system_rife_dirs())


def require_rife() -> str:
    rife = find_rife()
    if not rife:
        raise RifeCliError(
            "rife-ncnn-vulkan not found.\n"
            "  Run:  python -m rife_cli setup     (downloads it)\n"
            "  or:   yay -S rife-ncnn-vulkan-bin  (AUR)\n"
            "  or set $RIFE_NCNN_VULKAN to the executable."
        )
    return rife


def missing_shared_libs(exe: str) -> List[str]:
    """Shared libraries `exe` needs but the system lacks (e.g. libvulkan.so.1)."""
    ldd = shutil.which("ldd")
    if not ldd:
        return []
    try:
        res = capture([ldd, exe])
    except OSError:
        return []
    return sorted({line.split("=>")[0].strip() for line in (res.stdout + res.stderr).splitlines()
                   if "not found" in line})


def shared_lib_hint(libs: Sequence[str]) -> str:
    pkgs = {"libvulkan": "vulkan-icd-loader", "libgomp": "gcc-libs", "libstdc++": "gcc-libs",
            "libgcc_s": "gcc-libs"}
    needed = sorted({pkg for lib in libs for prefix, pkg in pkgs.items() if lib.startswith(prefix)})
    return "yay -S " + " ".join(needed or ["vulkan-icd-loader"])


# --------------------------------------------------------------------------- models
def model_search_dirs(rife_exe: Optional[str] = None) -> List[Path]:
    dirs: List[Path] = []
    env = os.environ.get("RIFE_CLI_MODELS")
    if env:
        dirs.append(Path(env).expanduser())
    if rife_exe:
        exe = Path(rife_exe)
        for base in {exe.parent, exe.resolve().parent}:
            dirs += [base, base / "models"]
    dirs += _system_rife_dirs()
    seen, unique = set(), []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _is_model(path: Path) -> bool:
    return path.is_dir() and (path / "flownet.param").is_file()


def list_models(rife_exe: Optional[str] = None) -> List[str]:
    names = set()
    for d in model_search_dirs(rife_exe):
        if d.is_dir():
            names.update(c.name for c in d.iterdir() if _is_model(c))
    return sorted(names)


def find_model(name: str, rife_exe: Optional[str] = None) -> Path:
    direct = Path(name).expanduser()
    if _is_model(direct):
        return direct.resolve()
    for d in model_search_dirs(rife_exe):
        if _is_model(d / name):
            return (d / name).resolve()
    available = ", ".join(list_models(rife_exe)) or "none found"
    raise RifeCliError(f"RIFE model '{name}' not found. Available: {available}.\n"
                       "  Try `python -m rife_cli setup` or set $RIFE_CLI_MODELS.")


# --------------------------------------------------------------------------- running
def run_checked(cmd: Sequence[str], what: str) -> None:
    """Run a command, letting its output (progress bars) go straight to the terminal."""
    try:
        proc = subprocess.run(list(cmd))
    except FileNotFoundError:
        raise RifeCliError(f"Cannot execute '{cmd[0]}'.")
    except PermissionError:
        raise RifeCliError(f"No permission to execute '{cmd[0]}' (try: chmod +x).")
    if proc.returncode != 0:
        raise RifeCliError(f"{what} failed (exit code {proc.returncode}).")


def capture(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, errors="replace")


# --------------------------------------------------------------------------- probing
def parse_rate(text: Optional[str]) -> Optional[Fraction]:
    if not text:
        return None
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def format_fps(rate: Fraction) -> str:
    if rate.denominator == 1:
        return str(rate.numerator)
    return f"{float(rate):.3f}".rstrip("0").rstrip(".")


class VideoInfo:
    def __init__(self, avg: Fraction, real: Optional[Fraction], width: int, height: int,
                 duration: Optional[float], has_audio: bool):
        self.fps, self.real_fps = avg, real
        self.width, self.height = width, height
        self.duration, self.has_audio = duration, has_audio

    @property
    def is_vfr(self) -> bool:
        return self.real_fps is not None and abs(float(self.fps - self.real_fps)) > 0.01


def probe(ffprobe: str, path: Path) -> VideoInfo:
    res = capture([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    if res.returncode != 0:
        raise RifeCliError(f"ffprobe could not read '{path}':\n{res.stderr.strip()}")
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise RifeCliError(f"No video stream found in '{path}'.")
    avg = parse_rate(video.get("avg_frame_rate")) or parse_rate(video.get("r_frame_rate"))
    if avg is None:
        raise RifeCliError("Could not determine the frame rate of the input video.")
    duration = video.get("duration") or data.get("format", {}).get("duration")
    return VideoInfo(
        avg=avg,
        real=parse_rate(video.get("r_frame_rate")),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        duration=float(duration) if duration not in (None, "N/A") else None,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def ffmpeg_supports(ffmpeg: str, option: str) -> bool:
    res = capture([ffmpeg, "-hide_banner", "-h", "full"])
    return option in (res.stdout + res.stderr)
