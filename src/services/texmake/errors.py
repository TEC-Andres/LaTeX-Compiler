from __future__ import annotations


class TexMakeError(Exception):
    """Base class for all texmake errors."""


class TexMakeSyntaxError(TexMakeError):
    """Raised when a texmakelists.txt file cannot be parsed or executed."""

    def __init__(self, message: str, line: int | None = None, filePath: str | None = None):
        self.message = message
        self.line = line
        self.filePath = filePath
        location = ""
        if filePath:
            location = filePath
        if line is not None:
            location = f"{location}:{line}" if location else f"line {line}"
        super().__init__(f"{location}: {message}" if location else message)


class TexMakeCompileError(TexMakeError):
    """Raised when the TeX engine fails to produce the expected output."""

    def __init__(self, message: str, logPath: str | None = None):
        self.message = message
        self.logPath = logPath
        super().__init__(message)