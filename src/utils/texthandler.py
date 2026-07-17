# src/utils/texthandler.py
import os
import sys
import ctypes
from functools import wraps
from typing import Any, Callable

from .constants import TERMINAL

class TerminalType:
    def __init__(self):
        self.isTTY = sys.stdout.isatty()
        self.isANSI = self.enableANSI()
        self.colorDepth = self.detectColorDepth()

    def enableANSI(self):
        """
        Enables ANSI escape processing when running on Windows.
        """
        if not self.isTTY:
            return False
        if os.name != "nt":
            return True

        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(TERMINAL.TTY.value)
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = TERMINAL.VIRTUALTERMINALPROCESSING.value
            return bool(
                kernel32.SetConsoleMode(
                    handle,
                    mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                )
            )
        except Exception:
            return False

    def detectColorDepth(self):
        """
        Returns:
            TERMINAL.TRUECOLOR.value -> True color
            TERMINAL._256COLOR.value -> 256 colors
            TERMINAL.BASICCOLORS.value -> basic colors
            0 -> no colors
        """
        if not self.isANSI:
            return 0
        if (
            os.environ.get("COLORTERM") in
            ("truecolor", "24bit")
        ):
            return TERMINAL.TRUECOLOR.value
        if "256color" in os.environ.get("TERM", ""):
            return TERMINAL._256COLOR.value
        if "WT_SESSION" in os.environ:
            return TERMINAL.TRUECOLOR.value
        return TERMINAL.BASICCOLORS.value


class TextHandler:
    def __init__(self):
        self.terminal = TerminalType()

    @staticmethod
    def _templateNote(func: Callable[..., Any]):
        @wraps(func)
        def wrapper(*args, **kwargs):
            self = args[0]
            if self.terminal.colorDepth == TERMINAL.TRUECOLOR.value:
                _gray = "\033[38;2;148;148;148m"
                _white = "\033[38;2;255;255;255m"

            elif self.terminal.colorDepth == TERMINAL._256COLOR.value:
                _gray = "\033[38;5;248m"
                _white = "\033[38;5;255m"

            elif self.terminal.colorDepth == TERMINAL.BASICCOLORS.value:
                _gray = "\033[90m"
                _white = "\033[97m"

            else:
                _gray = _white = ""

            _color, _label = func(*args, **kwargs)

            padding = TERMINAL.PADDING.value - len(_label)
            padded = " " * (padding // 2) + _label + " " * (padding - padding // 2)
            category = args[1] if len(args) > 1 else kwargs.get('category', '')
            text = args[2] if len(args) > 2 else kwargs.get('text', '')
            print(
                f"{_gray}[{_color}{padded}{_gray}] "
                f"{category} "
                f"{_white}{text}"
                f"\033[0m"
            )

        return wrapper

    @_templateNote
    def fail(self, category: str, text: str):
        match self.terminal.colorDepth:
            case TERMINAL.TRUECOLOR.value:
                _red = "\033[38;2;237;67;55m"
            case TERMINAL._256COLOR.value:
                _red = "\033[38;5;196m"
            case TERMINAL.BASICCOLORS.value:
                _red = "\033[31m"
            case _:
                _red = ""

        _label = "FAILED"
        return _red, _label

    @_templateNote
    def ok(self, category: str, text: str):
        match self.terminal.colorDepth:
            case TERMINAL.TRUECOLOR.value:
                _green = "\033[38;2;22;171;57m"
            case TERMINAL._256COLOR.value:
                _green = "\033[38;5;46m"
            case TERMINAL.BASICCOLORS.value:
                _green = "\033[32m"
            case _:
                _green = ""

        _label = "OK"
        return _green, _label

    @_templateNote
    def warn(self, category: str, text: str):
        match self.terminal.colorDepth:
            case TERMINAL.TRUECOLOR.value:
                _yellow = "\033[38;2;238;210;2m"
            case TERMINAL._256COLOR.value:
                _yellow = "\033[38;5;226m"
            case TERMINAL.BASICCOLORS.value:
                _yellow = "\033[33m"
            case _:
                _yellow = ""

        _label = "WARN"
        return _yellow, _label
    
    @_templateNote
    def info(self, category: str, text: str):
        match self.terminal.colorDepth:
            case TERMINAL.TRUECOLOR.value:
                _blue = "\033[38;2;0;122;204m"
            case TERMINAL._256COLOR.value:
                _blue = "\033[38;5;27m"
            case TERMINAL.BASICCOLORS.value:
                _blue = "\033[34m"
            case _:
                _blue = ""

        _label = "INFO"
        return _blue, _label
    
    def loadingPercentage(self, category: str, percent: int, success: bool = True, successMsg: str = "", errorMsg: str = ""):
        if self.terminal.colorDepth == TERMINAL.TRUECOLOR.value:
            _gray = "\033[38;2;148;148;148m"
            _white = "\033[38;2;255;255;255m"
            _green = "\033[38;2;22;171;57m"
            _red = "\033[38;2;237;67;55m"

        elif self.terminal.colorDepth == TERMINAL._256COLOR.value:
            _gray = "\033[38;5;248m"
            _white = "\033[38;5;255m"
            _green = "\033[38;5;46m"
            _red = "\033[38;5;196m"

        elif self.terminal.colorDepth == TERMINAL.BASICCOLORS.value:
            _gray = "\033[90m"
            _white = "\033[97m"
            _green = "\033[32m"
            _red = "\033[31m"

        else:
            _gray = _white = _green = _red = ""

        clear = " " * 40

        if percent < 100:
            _label = "LOAD"
            _color = _white
        elif success:
            _label = "OK"
            _color = _green
        else:
            _label = "FAILED"
            _color = _red

        padding = TERMINAL.PADDING.value - len(_label)
        padded = " " * (padding // 2) + _label + " " * (padding - padding // 2)

        if percent < 100:
            print(
                f"\r{_gray}[{_color}{padded}{_gray}] {category} {percent:3d}%{clear}",
                end="", flush=True
            )
        else:
            _msg = successMsg if success else errorMsg
            _extra = f" {_white}{_msg}" if _msg else ""
            print(
                f"\r{_gray}[{_color}{padded}{_gray}] {category}{_extra}{clear}"
                f"\033[0m"
            )