"""`rife-cli interpolate` - AI frame interpolation (RIFE) as one command.

Pipeline: probe -> extract frames -> RIFE (x2 per pass) -> encode (+ original audio).
"""
from __future__ import annotations

import shlex
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

from .. import common
from ..common import RifeCliError

NAME = "interpolate"
HELP = "Make a video smoother by AI frame interpolation (RIFE), e.g. 30fps -> 60fps."

QUALITY_CODECS = {"libx264", "libx265"}


def add_arguments(p) -> None:
    p.add_argument("-i", "--input", required=True, help="input video")
    p.add_argument("-o", "--output", help="output video (default: <input>_x<N>.mp4)")
    p.add_argument("-x", "--multiplier", type=int, choices=(2, 4, 8), default=2,
                   help="frame-rate multiplier (4 = two RIFE passes, 8 = three)")
    p.add_argument("-m", "--model", default="rife-v4.6",
                   help="RIFE model name or path (try rife-anime for animation)")
    p.add_argument("--loop", action="store_true",
                   help="make the result loop seamlessly (interpolates last->first frame)")
    p.add_argument("--target-fps", help="resample the final video to this fps, e.g. 60")
    p.add_argument("--frame-format", choices=("png", "jpg"), default="png",
                   help="temp frame format; jpg uses ~5x less disk, slightly lossy")
    p.add_argument("--codec", default="libx264", help="ffmpeg video codec")
    p.add_argument("--crf", type=int, default=18, help="quality for libx264/libx265 (lower = better)")
    p.add_argument("--preset", default="slow", help="encoder preset for libx264/libx265")
    p.add_argument("--pix-fmt", default="yuv420p", help="output pixel format")
    p.add_argument("--extra-encode-args", default="", help="extra ffmpeg output args, quoted string")
    p.add_argument("--no-audio", action="store_true", help="drop the audio track")
    p.add_argument("-g", "--gpu", default=None, help="GPU id(s) for RIFE, e.g. 0 or 0,1 (-1 = CPU)")
    p.add_argument("-j", "--threads", default="1:1:1", help="RIFE load:proc:save threads")
    p.add_argument("--uhd", action="store_true", help="RIFE UHD mode (better for 4K, slower)")
    p.add_argument("--workdir", help="folder for temporary frames (default: next to the output)")
    p.add_argument("--keep-temp", action="store_true", help="do not delete temporary frames")
    p.add_argument("-y", "--overwrite", action="store_true", help="overwrite the output file")
    p.add_argument("--force", action="store_true", help="continue even if disk space looks too small")


def _frames(directory: Path, ext: str):
    return sorted(directory.glob(f"*.{ext}"))


def _dir_size(directory: Path) -> int:
    return sum(f.stat().st_size for f in directory.iterdir() if f.is_file())


def _step(n: int, total: int, text: str) -> None:
    print(f"\n[{n}/{total}] {text}", flush=True)


def default_output(src: Path, multiplier: int) -> Path:
    return src.with_name(f"{src.stem}_x{multiplier}.mp4")


def run(args) -> int:
    ffmpeg, ffprobe = common.require_ffmpeg()
    rife = common.require_rife()
    model_dir = common.find_model(args.model, rife)

    src = Path(args.input).expanduser().resolve()
    if not src.is_file():
        raise RifeCliError(f"Input file not found: {src}")
    out = Path(args.output).expanduser().resolve() if args.output else default_output(src, args.multiplier)
    if out == src:
        raise RifeCliError("Output must be a different file from the input.")
    if out.exists() and not args.overwrite:
        raise RifeCliError(f"{out} already exists (use -y to overwrite).")
    out.parent.mkdir(parents=True, exist_ok=True)

    info = common.probe(ffprobe, src)
    passes = {2: 1, 4: 2, 8: 3}[args.multiplier]
    out_rate: Fraction = info.fps * args.multiplier
    ext = args.frame_format

    print(f"Input : {src.name}  {info.width}x{info.height} @ {common.format_fps(info.fps)} fps")
    print(f"Output: {out.name}  @ {common.format_fps(out_rate)} fps"
          + (f" -> resampled to {args.target_fps} fps" if args.target_fps else ""))
    print(f"Model : {model_dir.name}   passes: {passes}   loop: {'yes' if args.loop else 'no'}")
    if info.is_vfr:
        print("WARNING: variable frame rate detected; timing may drift. Consider converting to a "
              "constant frame rate first.")

    base = Path(args.workdir).expanduser().resolve() if args.workdir else out.parent
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".rife-cli-", dir=str(base)))
    try:
        _extract(ffmpeg, src, work / "in", ext)
        final_dir = _interpolate(rife, model_dir, work, passes, ext, args)
        _encode(ffmpeg, final_dir, ext, src, out, out_rate, info, args)
    finally:
        if args.keep_temp:
            print(f"\nTemporary files kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    size_mb = out.stat().st_size / 1e6
    print(f"\nDone! {out}  ({size_mb:.1f} MB)")
    return 0


def _extract(ffmpeg: str, src: Path, dest: Path, ext: str) -> None:
    _step(1, 3, "Extracting frames...")
    dest.mkdir(parents=True)
    cmd = [ffmpeg, "-hide_banner", "-v", "warning", "-stats", "-i", str(src), "-map", "0:v:0"]
    # Keep original timestamps 1:1 (no duplicated/dropped frames). Flag name depends on ffmpeg version.
    cmd += ["-fps_mode", "passthrough"] if common.ffmpeg_supports(ffmpeg, "fps_mode") else ["-vsync", "0"]
    if ext == "jpg":
        cmd += ["-q:v", "2"]
    cmd.append(str(dest / f"%08d.{ext}"))
    common.run_checked(cmd, "Frame extraction")
    if not _frames(dest, ext):
        raise RifeCliError("No frames were extracted.")


def _interpolate(rife: str, model_dir: Path, work: Path, passes: int, ext: str, args) -> Path:
    _step(2, 3, f"Interpolating frames with RIFE ({passes} pass{'es' if passes > 1 else ''})...")
    cur = work / "in"
    n_in = len(_frames(cur, ext))

    # Disk check: peak usage is roughly in * (2^p + 2^(p-1)).
    need = int(_dir_size(cur) * (2 ** passes + 2 ** (passes - 1)) * 1.05)
    free = shutil.disk_usage(str(work)).free
    print(f"  {n_in} frames; need ~{need / 1e9:.1f} GB temp space, {free / 1e9:.1f} GB free")
    if free < need and not args.force:
        raise RifeCliError("Not enough free disk space. Use --frame-format jpg, --workdir on a bigger "
                           "drive, or --force to try anyway.")

    for p in range(1, passes + 1):
        nxt = work / f"pass{p}"
        nxt.mkdir()
        if args.loop:  # append a copy of the first frame so RIFE also blends last -> first
            shutil.copyfile(_frames(cur, ext)[0], cur / f"{n_in + 1:08d}.{ext}")
        sent = n_in + (1 if args.loop else 0)

        cmd = [rife, "-i", str(cur), "-o", str(nxt), "-m", str(model_dir), "-f", ext, "-j", args.threads]
        if args.gpu is not None:
            cmd += ["-g", str(args.gpu)]
        if args.uhd:
            cmd.append("-u")
        print(f"  pass {p}/{passes}: {sent} -> {2 * sent} frames", flush=True)
        common.run_checked(cmd, "RIFE")

        produced = len(_frames(nxt, ext))
        if produced == 0:
            raise RifeCliError("RIFE produced no frames (see its output above).")
        if produced != 2 * sent:
            if args.loop:
                raise RifeCliError(f"RIFE produced {produced} frames, expected {2 * sent}; "
                                   "cannot build a seamless loop.")
            print(f"  WARNING: expected {2 * sent} frames, got {produced}.")
        if args.loop:  # drop the two frames that belong to the helper copy
            for idx in range(2 * n_in + 1, produced + 1):
                try:
                    (nxt / f"{idx:08d}.{ext}").unlink()
                except FileNotFoundError:
                    pass
            produced = len(_frames(nxt, ext))
        shutil.rmtree(cur, ignore_errors=True)  # free disk before the next pass
        cur, n_in = nxt, produced
    return cur


def _encode(ffmpeg: str, frames: Path, ext: str, src: Path, out: Path, rate: Fraction, info, args) -> None:
    _step(3, 3, "Encoding video...")
    use_audio = info.has_audio and not args.no_audio
    cmd = [ffmpeg, "-hide_banner", "-v", "warning", "-stats", "-y",
           "-framerate", str(rate), "-i", str(frames / f"%08d.{ext}")]
    if use_audio:
        cmd += ["-i", str(src), "-map", "0:v:0", "-map", "1:a:0"]
    if args.target_fps:
        cmd += ["-vf", f"fps={args.target_fps}"]
    cmd += ["-c:v", args.codec]
    if args.codec in QUALITY_CODECS:
        cmd += ["-crf", str(args.crf), "-preset", args.preset]
    cmd += ["-pix_fmt", args.pix_fmt]
    if args.codec == "libx265" and out.suffix.lower() in (".mp4", ".mov", ".m4v"):
        cmd += ["-tag:v", "hvc1"]  # lets Apple devices play HEVC
    if use_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd.append("-an")
    if out.suffix.lower() in (".mp4", ".mov", ".m4v"):
        cmd += ["-movflags", "+faststart"]
    if args.extra_encode_args:
        cmd += shlex.split(args.extra_encode_args)
    cmd.append(str(out))
    common.run_checked(cmd, "Video encoding")
