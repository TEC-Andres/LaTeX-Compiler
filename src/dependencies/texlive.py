from __future__ import annotations
from typing import Any, Callable, TypeVar, List
import os
import re
import subprocess
import sys
import requests
from datetime import date

from utils.constants import TEXLIVE
from services._updater import UpdaterService

class TexLive:
    def __init__(self, name: str, version: str, description: str, website: str):
        self.name = name
        self.version = version
        self.description = description
        self.website = website

    def getTexLiveDir(self) -> str | None:
        """
        getTexLiveDir: Returns the path to the TeX Live installation directory if it exists, otherwise returns None.
        """
        if sys.platform == "win32" or sys.platform.startswith("win"):
            baseDirs = [
                "C:\\texlive",
                "C:\\Program Files\\texlive",
                "C:\\Program Files (x86)\\texlive"
            ]
        elif sys.platform == "darwin" or sys.platform.startswith("linux"):
            baseDirs = [
                "/usr/local/texlive",
                "/usr/share/texlive",
                "/opt/texlive"
            ]
        else:
            return None

        for baseDir in baseDirs:
            for year in range(date.today().year, TEXLIVE.MIN_YEAR.value - 1, -1):
                candidate = os.path.join(baseDir, str(year))
                if os.path.exists(candidate):
                    return candidate
        return None
    
    def getLocalTexVersion(self) -> str | None:
        """
        getLocalTexVersion: Returns the version string from `tex --version` (e.g. "TeX Live 2025").
        """
        try:
            result = subprocess.run(
                ["tex", "--version"],
                capture_output=True,
                text=True,
                timeout=500
            )
            if result.returncode != 0:
                return None
            match = re.search(r"TeX Live \d{4}", result.stdout)
            return match.group(0) if match else None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
    
    def getOnlineTexVersion(self) -> str | None:
        """
        getOnlineTexVersion: Returns the latest online version string (e.g. "TeX Live 2026").
        """
        try:
            response = requests.get("https://www.tug.org/texlive/")
            if response.status_code == 200:
                match = re.search(r"TeX Live (\d{4})", response.text)
                if match:
                    return match.group(0)
        except Exception as e:
            raise ConnectionRefusedError(f"Failed to connect to the TeX Live website: {e}")

    def isTexLiveUpToDate(self) -> bool:
        """
        isTexLiveUpToDate: Checks if the local TeX Live installation is up to date with the latest online version.
        """
        localVersion = self.getLocalTexVersion()
        onlineVersion = self.getOnlineTexVersion()

        if localVersion is None or onlineVersion is None:
            return False

        return localVersion == onlineVersion
    
    def updateTexLive(self) -> None:
        """
        updateTexLive: Updates TeX Live, handling cross-release upgrades.
        """
        localVer = self.getLocalTexVersion()
        onlineVer = self.getOnlineTexVersion()

        if localVer == onlineVer:
            print("TeX Live is already up to date.")
            return

        if localVer and onlineVer and localVer != onlineVer:
            self._runCrossReleaseUpgrade(onlineVer)
            texliveDir = self.getTexLiveDir()
            if texliveDir:
                print("Upgrading all packages to the new release via multi-threaded updater...")
                UpdaterService().updateTexLive(texliveDir)
                print("Running post-install steps...")
                self._runPostInstall(texliveDir)
            return

        self._runTlmgr(["update", "--self"])

    def _runCrossReleaseUpgrade(self, onlineVer: str) -> None:
        year = re.search(r"(\d{4})", onlineVer)
        if not year:
            return
        targetVersion = year.group(1)

        print(f"Cross-release upgrade detected: updating tlmgr for TeX Live {targetVersion}...")

        if sys.platform == "win32" or sys.platform.startswith("win"):
            updaterExe = "update-tlmgr-latest.exe"
            updaterUrl = f"https://mirror.ctan.org/systems/texlive/tlnet/{updaterExe}"
            updaterPath = os.path.join(os.environ.get("TEMP", "C:\\Temp"), updaterExe)

            resp = requests.get(updaterUrl, stream=True, timeout=60)
            resp.raise_for_status()
            with open(updaterPath, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)

            subprocess.run([updaterPath, "--update"], check=True, timeout=300)
        else:
            updaterSh = "update-tlmgr-latest.sh"
            updaterUrl = f"https://mirror.ctan.org/systems/texlive/tlnet/{updaterSh}"
            updaterPath = f"/tmp/{updaterSh}"

            resp = requests.get(updaterUrl, stream=True, timeout=60)
            resp.raise_for_status()
            with open(updaterPath, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)
            os.chmod(updaterPath, 0o755)

            subprocess.run(
                ["sudo", "sh", updaterPath, "--update"],
                check=True, timeout=300
            )

    def _runPostInstall(self, texliveDir: str) -> None:
        binDir = None
        if sys.platform == "win32":
            for sub in ["windows", "win32"]:
                d = os.path.join(texliveDir, "bin", sub)
                if os.path.exists(d):
                    binDir = d
                    break
        else:
            for sub in ["x86_64-linux", "universal-darwin"]:
                d = os.path.join(texliveDir, "bin", sub)
                if os.path.exists(d):
                    binDir = d
                    break
        if not binDir:
            binDir = os.path.join(texliveDir, "bin")
        if binDir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = binDir + os.pathsep + os.environ.get("PATH", "")

        cacheDir = os.path.join(texliveDir, "texmf-var", "fonts", "cache")
        os.makedirs(cacheDir, exist_ok=True)

        steps = [("mktexlsr", []), ("fmtutil-sys", ["--all"]), ("updmap-sys", [])]
        fallback = [("fmtutil-user", ["--all"]), ("updmap-user", [])]

        for exeName, args in steps:
            exe = exeName + ".exe" if sys.platform == "win32" else exeName
            exePath = os.path.join(binDir, exe)
            if os.path.exists(exePath):
                try:
                    subprocess.run([exePath] + args, check=True, timeout=300)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    fallbackName = exeName.replace("-sys", "-user")
                    fallbackExe = fallbackName + ".exe" if sys.platform == "win32" else fallbackName
                    fallbackPath = os.path.join(binDir, fallbackExe)
                    if os.path.exists(fallbackPath):
                        try:
                            subprocess.run([fallbackPath] + args, check=True, timeout=300)
                        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                            pass

    def _runTlmgr(self, args: list[str]) -> None:
        if sys.platform == "win32" or sys.platform.startswith("win"):
            subprocess.run(
                ["tlmgr"] + args,
                check=True, timeout=600, shell=True
            )
        elif sys.platform in ("darwin", "linux") or sys.platform.startswith("linux"):
            subprocess.run(
                ["sudo", "tlmgr"] + args,
                check=True, timeout=600
            )
        else:
            raise OSError("Unsupported operating system for TeX Live update.")
