from __future__ import annotations
from typing import Any, Callable, TypeVar, List
import json
import os
import threading

from services._updater import UpdaterService


TEXLIB_MANIFEST = "https://raw.githubusercontent.com/example/texlib/main/manifest.json"


class TexLib:
    def __init__(self):
        self.threads = []
        self._localVersion: str | None = None
        self._onlineVersion: str | None = None

    @property
    def getAvailableThreads(self) -> list:
        self.threads = threading.enumerate()
        return self.threads

    def getLocalVersion(self) -> str | None:
        if self._localVersion is not None:
            return self._localVersion
        manifestPath = os.path.join(os.path.dirname(__file__), "..", "texlib-manifest.json")
        if os.path.exists(manifestPath):
            with open(manifestPath) as f:
                data = json.load(f)
                self._localVersion = data.get("version")
        return self._localVersion

    def getOnlineVersion(self) -> str | None:
        if self._onlineVersion is not None:
            return self._onlineVersion
        try:
            import requests
            response = requests.get(TEXLIB_MANIFEST, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self._onlineVersion = data.get("version")
                return self._onlineVersion
        except Exception:
            return None
        return None

    def isUpToDate(self) -> bool:
        local = self.getLocalVersion()
        online = self.getOnlineVersion()
        if local is None or online is None:
            return False
        return local == online

    def updateTexLib(self) -> None:
        manifestUrl = TEXLIB_MANIFEST
        try:
            import requests
            response = requests.get(manifestUrl, timeout=10)
            response.raise_for_status()
            manifest = response.json()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch texlib manifest: {e}")

        packages = manifest.get("packages", [])
        if not packages:
            print("No texlib packages to update.")
            return

        baseUrl = manifest.get("baseUrl", "")
        destDir = os.path.join(os.path.dirname(__file__), "..", "texlib-packages")
        os.makedirs(destDir, exist_ok=True)

        updater = UpdaterService()
        updater.updatePackages(packages, baseUrl, destDir)

        if "version" in manifest:
            manifestPath = os.path.join(os.path.dirname(__file__), "..", "texlib-manifest.json")
            with open(manifestPath, "w") as f:
                json.dump({"version": manifest["version"]}, f)
            self._localVersion = manifest["version"]
