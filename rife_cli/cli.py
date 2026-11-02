from __future__ import annotations

import argparse
import sys

from . import __version__
from .common import RifeCliError
from .tools import TOOLS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rife-cli",
        description="Video workflows for CachyOS built on ffmpeg and AI tools.")
    parser.add_argument("--version", action="version", version=f"rife-cli {__version__}")
    sub = parser.add_subparsers(dest="tool", metavar="<tool>")
    for tool in TOOLS:
        sp = sub.add_parser(tool.NAME, help=tool.HELP, description=tool.HELP,
                            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        tool.add_arguments(sp)
        sp.set_defaults(_run=tool.run)
    return parser


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):  # never crash on odd console encodings
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "_run", None):
        parser.print_help()
        return 0
    try:
        return int(args._run(args) or 0)
    except RifeCliError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
