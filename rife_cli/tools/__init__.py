"""Registry of workflow tools.

To add a new tool: create rife_cli/tools/<name>.py exposing
    NAME: str, HELP: str, add_arguments(parser), run(args) -> int
and append the module to TOOLS below. It then shows up as `rife-cli <name>`.
"""
from .. import doctor, installer
from . import interpolate

TOOLS = [interpolate, installer, doctor]
