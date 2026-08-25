from __future__ import annotations
import json
import os
import shutil
import time

from ._pagecache import NativeHash

_MANIFEST_FILE = "buildManifest.json"
_CACHE_DIR_NAME = "__texcache__"
_INTERMEDIATE_EXTS = {".aux", ".nav", ".out", ".toc", ".snm", ".log"}
_SNAPSHOT_DIR = "prev"


class BuildManifest:
    """Tracks source file hashes and intermediate file state across builds."""

    def __init__(self, sourceDir: str):
        self.sourceDir = sourceDir
        self.cacheDir = os.path.join(sourceDir, _CACHE_DIR_NAME)
        self.manifestPath = os.path.join(self.cacheDir, _MANIFEST_FILE)
        self.data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.manifestPath, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, json.JSONDecodeError):
            self.data = {"source_hashes": {}, "intermediates": {}, "page_count": 0, "timestamp": 0}

    def save(self) -> None:
        os.makedirs(self.cacheDir, exist_ok=True)
        self.data["timestamp"] = time.time()
        with open(self.manifestPath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def hash_source(self, filePath: str) -> str:
        return NativeHash.file(filePath)

    def source_changed(self, filePath: str) -> bool:
        current = self.hash_source(filePath)
        previous = self.data.get("source_hashes", {}).get(filePath)
        return current != previous

    def any_source_changed(self, filePaths: list[str]) -> bool:
        return any(self.source_changed(p) for p in filePaths)

    def update_source_hashes(self, filePaths: list[str]) -> None:
        if "source_hashes" not in self.data:
            self.data["source_hashes"] = {}
        for path in filePaths:
            self.data["source_hashes"][path] = self.hash_source(path)

    def snapshot_intermediates(self, stem: str) -> str:
        snapshotDir = os.path.join(self.cacheDir, _SNAPSHOT_DIR, stem)
        os.makedirs(snapshotDir, exist_ok=True)
        for ext in _INTERMEDIATE_EXTS:
            src = os.path.join(self.cacheDir, f"{stem}{ext}")
            if os.path.isfile(src):
                dst = os.path.join(snapshotDir, f"{stem}{ext}")
                shutil.copy2(src, dst)
        return snapshotDir

    def read_snapshot(self, stem: str, ext: str) -> str | None:
        path = os.path.join(self.cacheDir, _SNAPSHOT_DIR, stem, f"{stem}{ext}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def read_current(self, stem: str, ext: str) -> str | None:
        path = os.path.join(self.cacheDir, f"{stem}{ext}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def snapshot_exists(self, stem: str) -> bool:
        snapshotDir = os.path.join(self.cacheDir, _SNAPSHOT_DIR, stem)
        return os.path.isdir(snapshotDir) and any(
            f.startswith(stem) for f in os.listdir(snapshotDir)
        )

    def get_page_count(self) -> int:
        return self.data.get("page_count", 0)

    def set_page_count(self, count: int) -> None:
        self.data["page_count"] = count

    def clear(self) -> None:
        if os.path.isdir(self.cacheDir):
            shutil.rmtree(self.cacheDir)
        self.data = {"source_hashes": {}, "intermediates": {}, "page_count": 0, "timestamp": 0}

    def remove_snapshot(self, stem: str) -> None:
        snapshotDir = os.path.join(self.cacheDir, _SNAPSHOT_DIR, stem)
        if os.path.isdir(snapshotDir):
            shutil.rmtree(snapshotDir)
