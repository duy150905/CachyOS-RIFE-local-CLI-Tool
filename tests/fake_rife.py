"""Stand-in for rife-ncnn-vulkan: writes 2 output frames per input frame. No GPU needed."""
import argparse
import shutil
import sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("-i")
ap.add_argument("-o")
ap.add_argument("-m")
ap.add_argument("-f", default="png")
ap.add_argument("-g")
ap.add_argument("-j")
ap.add_argument("-u", action="store_true")
a = ap.parse_args()

frames = sorted(Path(a.i).glob("*.*"))
if not frames or not Path(a.o).is_dir():
    sys.exit("fake rife: bad input/output dir")
for k, f in enumerate(frames, start=1):
    shutil.copyfile(f, Path(a.o) / f"{2 * k - 1:08d}.{a.f}")
    shutil.copyfile(f, Path(a.o) / f"{2 * k:08d}.{a.f}")
