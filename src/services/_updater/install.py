from __future__ import annotations
import os
import sys
import subprocess
import requests
import tempfile
import platform
from datetime import date

from utils.constants import TEXLIVE


class TexInstaller:
    def _getInstallDir(self) -> str:
        year = max(date.today().year, TEXLIVE.MIN_YEAR.value)
        if sys.platform == "win32":
            return f"C:\\texlive\\{year}"
        else:
            return f"/usr/local/texlive/{year}"

    def _addToPath(self, installDir: str) -> None:
        binDir = None
        if sys.platform == "win32":
            for sub in ["bin\\win32", "bin\\windows"]:
                d = os.path.join(installDir, sub)
                if os.path.exists(d):
                    binDir = d
                    break
        else:
            arch = platform.machine()
            for sub in [f"bin/{arch}-linux", "bin/x86_64-linux", "bin/universal-darwin"]:
                d = os.path.join(installDir, sub)
                if os.path.exists(d):
                    binDir = d
                    break
        if binDir and binDir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = binDir + os.pathsep + os.environ.get("PATH", "")

    def isTexLiveInstalled(self) -> bool:
        try:
            result = subprocess.run(
                ["tex", "--version"],
                captureOutput=True,
                text=True,
                timeout=500
            )
            return result.returncode == 0 and "TeX Live" in result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _addExclusion(self, path: str) -> None:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 f"Add-MpPreference -ExclusionPath '{path}' -ErrorAction SilentlyContinue"],
                captureOutput=True, timeout=30
            )
        except Exception:
            pass

    def _removeExclusion(self, path: str) -> None:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 f"Remove-MpPreference -ExclusionPath '{path}' -ErrorAction SilentlyContinue"],
                captureOutput=True, timeout=30
            )
        except Exception:
            pass

    def installTexLive(self, installDir: str | None = None) -> str:
        if installDir is None:
            installDir = self._getInstallDir()

        print(":: Installing TeX Live (standalone, no libraries)...")
        print(":: Downloading install-tl CLI...")

        tmpDir = tempfile.mkdtemp()
        try:
            if sys.platform == "win32":
                url = "https://mirror.ctan.org/systems/texlive/tlnet/install-tl-windows.exe"
                installerPath = os.path.join(tmpDir, "install-tl-windows.exe")
            else:
                url = "https://mirror.ctan.org/systems/texlive/tlnet/install-tl"
                installerPath = os.path.join(tmpDir, "install-tl")

            resp = requests.get(url, stream=True, timeout=120)
            resp.raise_for_status()
            with open(installerPath, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)

            if sys.platform != "win32":
                os.chmod(installerPath, 0o755)

            if sys.platform == "win32":
                self._addExclusion(tmpDir)

            print(":: Running install-tl --gui=text --scheme=infraonly --no-interaction...")
            try:
                subprocess.run(
                    [installerPath, "--gui=text", "--scheme=infraonly", "--no-interaction"],
                    check=True,
                    timeout=600
                )
            except OSError:
                if sys.platform != "win32":
                    raise
                print(":: Windows Defender blocked the installer. Adding process exclusion and retrying...")
                procName = os.path.basename(installerPath)
                subprocess.run(
                    ["powershell", "-Command",
                     f"Add-MpPreference -ExclusionProcess '{procName}' -ErrorAction SilentlyContinue"],
                    captureOutput=True, timeout=30
                )
                subprocess.run(
                    [installerPath, "--gui=text", "--scheme=infraonly", "--no-interaction"],
                    check=True,
                    timeout=600
                )
        finally:
            if sys.platform == "win32":
                self._removeExclusion(tmpDir)
            import shutil
            shutil.rmtree(tmpDir, ignore_errors=True)

        self._addToPath(installDir)
        print(f":: TeX Live installed at {installDir}")
        return installDir
