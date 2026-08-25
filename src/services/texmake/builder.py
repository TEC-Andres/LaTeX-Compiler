from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess

from .errors import TexMakeCompileError
from .interpreter import Target, TexMakeProject

_MAX_PASSES = 3
_DEFAULT_OUTPUT_DIR = "__release__"
_CACHE_DIR_NAME = "__texcache__"
_ENGINE_CACHE_FILE = "engineCache.json"
_VERSION_BANNER_RE = re.compile(r"Version (\d+)\.(\d+)")
_RERUN_PATTERNS = ("Rerun to get cross-references right", "Label(s) may have changed")


def _parseBannerVersion(output: str) -> tuple[int, ...]:
    match = _VERSION_BANNER_RE.search(output)
    if not match:
        return ()
    return (int(match.group(1)), int(match.group(2)))


class Builder:
    """Compiles the executable targets of a resolved TexMakeProject."""

    def __init__(self, project: TexMakeProject):
        self.project = project

    def build(self, targetName: str | None = None) -> list[str]:
        targets = [target for target in self.project.targets.values() if target.kind == "executable"]
        if targetName:
            targets = [target for target in targets if target.name == targetName]
            if not targets:
                raise TexMakeCompileError(f"unknown executable target '{targetName}'")
        pdfPaths: list[str] = []
        for target in targets:
            pdfPaths.append(self._buildTarget(target))
        return pdfPaths

    def _resolveEngine(self) -> str:
        engineExe = shutil.which(self.project.engine)
        if not engineExe:
            raise TexMakeCompileError(f"engine '{self.project.engine}' not found in PATH")
        return engineExe

    def _checkEngineVersion(self, output: str) -> None:
        if not self.project.minVersion:
            return
        actual = _parseBannerVersion(output)
        if actual and actual < self.project.minVersion:
            required = ".".join(str(part) for part in self.project.minVersion)
            raise TexMakeCompileError(
                f"engine '{self.project.engine}' version {'.'.join(str(p) for p in actual)} "
                f"is older than required {required}"
            )

    def _computeEngineHash(self, engineExe: str) -> str:
        minVersionStr = ".".join(str(p) for p in self.project.minVersion) if self.project.minVersion else ""
        payload = f"{self.project.engine}|{engineExe}|{minVersionStr}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _readEngineCache(self, cacheDir: str) -> str | None:
        cachePath = os.path.join(cacheDir, _ENGINE_CACHE_FILE)
        try:
            with open(cachePath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("engine_hash")
        except (OSError, json.JSONDecodeError, KeyError):
            return None

    def _writeEngineCache(self, cacheDir: str, engineExe: str, engineHash: str) -> None:
        cachePath = os.path.join(cacheDir, _ENGINE_CACHE_FILE)
        data = {
            "engine_hash": engineHash,
            "engine": self.project.engine,
            "engine_exe": engineExe,
            "min_version": list(self.project.minVersion) if self.project.minVersion else None,
        }
        with open(cachePath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _buildTarget(self, target: Target) -> str:
        engineExe = self._resolveEngine()
        if not target.mainFile:
            raise TexMakeCompileError(f"target '{target.name}' has no main file")
        sourceDir = self.project.sourceDir
        mainPath = target.mainFile if os.path.isabs(target.mainFile) else os.path.join(sourceDir, target.mainFile)
        if not os.path.isfile(mainPath):
            raise TexMakeCompileError(f"main file '{mainPath}' not found")
        mainName = os.path.relpath(mainPath, sourceDir).replace(os.sep, "/")
        stem = os.path.splitext(os.path.basename(mainName))[0]
        cacheDir = os.path.join(sourceDir, _CACHE_DIR_NAME)
        os.makedirs(cacheDir, exist_ok=True)
        logPath = os.path.join(cacheDir, f"{stem}.log")
        pdfPath = os.path.join(cacheDir, f"{stem}.pdf")
        outputDirArg = f"-output-directory={cacheDir.replace(os.sep, '/')}"
        engineHash = self._computeEngineHash(engineExe)
        cachedHash = self._readEngineCache(cacheDir)
        cacheValid = (cachedHash == engineHash)
        for passNum in range(_MAX_PASSES):
            proc = subprocess.run(
                [engineExe, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                 outputDirArg, mainName],
                cwd=sourceDir,
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise TexMakeCompileError(self._extractError(logPath), logPath)
            if passNum == 0:
                if cacheValid:
                    self._writeEngineCache(cacheDir, engineExe, engineHash)
                else:
                    self._checkEngineVersion(proc.stdout)
                    self._writeEngineCache(cacheDir, engineExe, engineHash)
            if passNum + 1 >= _MAX_PASSES:
                break
            logContent = self._readIfExists(logPath) or ""
            if not any(pattern in logContent for pattern in _RERUN_PATTERNS):
                break
        if not os.path.isfile(pdfPath):
            raise TexMakeCompileError(f"engine succeeded but produced no pdf at '{pdfPath}'", logPath)
        outputDir = target.outputDir or os.path.join(self.project.sourceDir, _DEFAULT_OUTPUT_DIR)
        os.makedirs(outputDir, exist_ok=True)
        pdfDest = os.path.join(outputDir, os.path.basename(pdfPath))
        if os.path.abspath(pdfDest) != os.path.abspath(pdfPath):
            shutil.move(pdfPath, pdfDest)
        return pdfDest

    @staticmethod
    def _readIfExists(path: str) -> str | None:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return None

    @staticmethod
    def _extractError(logPath: str) -> str:
        if not os.path.isfile(logPath):
            return "engine failed without producing a log"
        try:
            with open(logPath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return f"engine failed (could not read '{logPath}')"
        for i, line in enumerate(lines):
            if line.startswith("!"):
                detail = line.strip()
                for extra in lines[i + 1:i + 4]:
                    stripped = extra.strip()
                    if stripped and not stripped.startswith("l."):
                        detail = f"{detail} {stripped}"
                        break
                return f"{detail} (see '{logPath}')"
        fileLineError = re.compile(r"^[\w./\\-]+\.(?:tex|ltx):\d+:")
        for line in lines:
            if fileLineError.match(line):
                detail = line.strip()
                return f"{detail} (see '{logPath}')"
        return f"engine failed (see '{logPath}')"