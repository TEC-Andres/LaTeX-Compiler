from __future__ import annotations
import argparse
import os
import sys

from services.texmake import Builder, TexMakeError, TexMakeProject
from utils.texthandler import TextHandler

_TEXMAKE_LISTS = "texmakelists.txt"


def _findTexMakeLists(startDir: str) -> str | None:
    current = os.path.abspath(startDir)
    while True:
        candidate = os.path.join(current, _TEXMAKE_LISTS)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _parseArgs(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="texmake",
        description="Build a LaTeX project from a texmakelists.txt file.",
    )
    parser.add_argument(
        "dir",
        nargs="?",
        default=None,
        help="directory containing texmakelists.txt (defaults to the current directory)",
    )
    parser.add_argument(
        "--target",
        default=None,
        help="build only the given executable target",
    )
    return parser.parse_args(argv)


def _build(listsPath: str, targetName: str | None, ui: TextHandler) -> int:
    sourceDir = os.path.dirname(listsPath)
    try:
        project = TexMakeProject(sourceDir, listsPath).run()
        Builder(project).build(targetName)
    except TexMakeError as e:
        ui.fail("TexMake", str(e))
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    args = _parseArgs(sys.argv[1:])
    startDir = args.dir if args.dir else os.getcwd()
    listsPath = _findTexMakeLists(startDir)
    if listsPath is None:
        print(f":: No {_TEXMAKE_LISTS} found in '{startDir}' or any parent directory")
        sys.exit(0)
    ui = TextHandler()
    sys.exit(_build(listsPath, args.target, ui))