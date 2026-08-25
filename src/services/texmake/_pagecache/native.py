from __future__ import annotations
import ctypes
import ctypes.util
import hashlib
import os
import struct
import sys

_NATIVE_AVAILABLE = False
_lib: ctypes.CDLL | None = None


class _Hunk(ctypes.Structure):
    _fields_ = [
        ("old_start", ctypes.c_int32),
        ("old_end", ctypes.c_int32),
        ("new_start", ctypes.c_int32),
        ("new_end", ctypes.c_int32),
    ]


class _DiffResult(ctypes.Structure):
    _fields_ = [
        ("hunks", ctypes.POINTER(_Hunk)),
        ("count", ctypes.c_int32),
        ("capacity", ctypes.c_int32),
    ]


def _findLibrary() -> ctypes.CDLL | None:
    if sys.platform == "win32":
        names = ["pagecache.dll", "libpagecache.dll"]
    elif sys.platform == "darwin":
        names = ["libpagecache.dylib"]
    else:
        names = ["libpagecache.so"]

    searchPaths = [
        os.path.dirname(os.path.abspath(__file__)),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."),
    ]

    for name in names:
        for base in searchPaths:
            candidate = os.path.join(base, name)
            if os.path.isfile(candidate):
                try:
                    return ctypes.CDLL(candidate)
                except OSError:
                    continue

    systemPath = ctypes.util.find_library("pagecache")
    if systemPath:
        try:
            return ctypes.CDLL(systemPath)
        except OSError:
            pass

    return None


def _initNative() -> None:
    global _NATIVE_AVAILABLE, _lib
    if _lib is not None:
        return
    lib = _findLibrary()
    if lib is None:
        _lib = None
        _NATIVE_AVAILABLE = False
        return

    lib.pagecache_hash_buffer.restype = ctypes.c_uint64
    lib.pagecache_hash_buffer.argtypes = [ctypes.c_char_p, ctypes.c_size_t]

    lib.pagecache_hash_file.restype = ctypes.c_uint64
    lib.pagecache_hash_file.argtypes = [ctypes.c_char_p]

    lib.pagecache_diff_new.restype = ctypes.POINTER(_DiffResult)
    lib.pagecache_diff_new.argtypes = [ctypes.c_int32]

    lib.pagecache_diff_free.restype = None
    lib.pagecache_diff_free.argtypes = [ctypes.POINTER(_DiffResult)]

    lib.pagecache_diff_lines.restype = ctypes.POINTER(_DiffResult)
    lib.pagecache_diff_lines.argtypes = [
        ctypes.POINTER(ctypes.c_char_p), ctypes.c_int32,
        ctypes.POINTER(ctypes.c_char_p), ctypes.c_int32,
        ctypes.c_int32,
    ]

    lib.pagecache_diff_count.restype = ctypes.c_int32
    lib.pagecache_diff_count.argtypes = [ctypes.POINTER(_DiffResult)]

    lib.pagecache_diff_get.restype = _Hunk
    lib.pagecache_diff_get.argtypes = [ctypes.POINTER(_DiffResult), ctypes.c_int32]

    lib.pagecache_diff_total_lines_removed.restype = ctypes.c_int32
    lib.pagecache_diff_total_lines_removed.argtypes = [ctypes.POINTER(_DiffResult)]

    lib.pagecache_diff_total_lines_added.restype = ctypes.c_int32
    lib.pagecache_diff_total_lines_added.argtypes = [ctypes.POINTER(_DiffResult)]

    lib.pagecache_diff_touches_page_range.restype = ctypes.c_int32
    lib.pagecache_diff_touches_page_range.argtypes = [
        ctypes.POINTER(_DiffResult),
        ctypes.POINTER(ctypes.c_int32),
        ctypes.c_int32,
        ctypes.c_int32,
        ctypes.c_int32,
    ]

    _lib = lib
    _NATIVE_AVAILABLE = True


_initNative()


def nativeAvailable() -> bool:
    return _NATIVE_AVAILABLE


class NativeHash:
    @staticmethod
    def file(path: str) -> str:
        if _NATIVE_AVAILABLE and _lib and os.path.isfile(path):
            try:
                result = _lib.pagecache_hash_file(path.encode("utf-8"))
                if result != 0:
                    return format(result, "016x")
            except (OSError, ctypes.ArgumentError):
                pass
        return hashlib.file_digest(open(path, "rb"), "sha256").hexdigest()

    @staticmethod
    def buffer(data: bytes) -> str:
        if _NATIVE_AVAILABLE and _lib:
            try:
                result = _lib.pagecache_hash_buffer(data, len(data))
                return format(result, "016x")
            except (OSError, ctypes.ArgumentError):
                pass
        return hashlib.sha256(data).hexdigest()


class NativeDiff:
    def __init__(self, context: int = 3):
        self.context = context

    def diff(self, oldLines: list[str], newLines: list[str]) -> list[tuple[int, int, int, int]]:
        if _NATIVE_AVAILABLE and _lib:
            try:
                return self._nativeDiff(oldLines, newLines)
            except (OSError, ctypes.ArgumentError, ValueError):
                pass
        return self._pythonDiff(oldLines, newLines)

    def _nativeDiff(self, oldLines: list[str], newLines: list[str]) -> list[tuple[int, int, int, int]]:
        oldArr = (ctypes.c_char_p * len(oldLines))()
        newArr = (ctypes.c_char_p * len(newLines))()
        for i, line in enumerate(oldLines):
            oldArr[i] = line.encode("utf-8")
        for i, line in enumerate(newLines):
            newArr[i] = line.encode("utf-8")

        result = _lib.pagecache_diff_lines(
            oldArr, len(oldLines),
            newArr, len(newLines),
            self.context,
        )

        count = _lib.pagecache_diff_count(result)
        hunks = []
        for i in range(count):
            h = _lib.pagecache_diff_get(result, i)
            hunks.append((h.old_start, h.old_end, h.new_start, h.new_end))

        _lib.pagecache_diff_free(result)
        return hunks

    @staticmethod
    def _pythonDiff(oldLines: list[str], newLines: list[str]) -> list[tuple[int, int, int, int]]:
        import difflib
        sm = difflib.SequenceMatcher(None, oldLines, newLines)
        hunks = []
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            hunks.append((i1, i2, j1, j2))
        return hunks
