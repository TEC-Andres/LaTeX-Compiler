from __future__ import annotations
import os
import sys
import tarfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter

from utils.threadingGS import ThreadingGS
from .install import TexInstaller


class DownloadProgress:
    def __init__(self, name: str, totalSize: int):
        self.name = name
        self.totalSize = totalSize
        self.downloaded = 0
        self.startTime = time.time()
        self.speed = 0.0
        self.percent = 0
        self.finished = False
        self.error: str | None = None
        self._lock = threading.Lock()

    def update(self, chunkSize: int) -> None:
        with self._lock:
            self.downloaded += chunkSize
            self.percent = int(self.downloaded * 100 / self.totalSize) if self.totalSize > 0 else 0
            elapsed = time.time() - self.startTime
            self.speed = self.downloaded / elapsed if elapsed > 0 else 0

    @staticmethod
    def _formatSize(bytesVal: int) -> str:
        for unit in ['B', 'KiB', 'MiB', 'GiB']:
            if bytesVal < 1024:
                return f"{bytesVal:.1f} {unit}"
            bytesVal /= 1024
        return f"{bytesVal:.1f} GiB"

    @staticmethod
    def _formatSpeed(bytesPerSec: float) -> str:
        for unit in ['B/s', 'KiB/s', 'MiB/s', 'GiB/s']:
            if bytesPerSec < 1024:
                return f"{bytesPerSec:.2f} {unit}"
            bytesPerSec /= 1024
        return f"{bytesPerSec:.2f} GiB/s"


class UpdaterService(TexInstaller):
    def __init__(self):
        self._threadingGS = ThreadingGS()

    def updatePackages(self, packages: list[dict], baseUrl: str, destDir: str) -> None:
        os.makedirs(destDir, exist_ok=True)

        pkgs = []
        for p in packages:
            url = p.get('url', f"{baseUrl}/{p['name']}.tar.xz")
            pkgs.append({**p, 'url': url})

        print(":: Retrieving packages...")

        self._downloadAll(pkgs, destDir)

        barLen = 30
        totalSize = sum(p.get('size', 0) for p in pkgs)
        sizeStr = DownloadProgress._formatSize(totalSize)
        print(f" Total ({len(pkgs)}/{len(pkgs)}) {sizeStr:>8}                         [{'#' * barLen}] 100%")

    def updateTexLive(self, texliveDir: str) -> None:
        tlpdbPath = os.path.join(texliveDir, "tlpkg", "texlive.tlpdb")
        if not os.path.exists(tlpdbPath):
            print(":: No TeX Live package database found.")
            return

        packages = self._parsePackages(tlpdbPath)
        if not packages:
            print(":: No packages found in TeX Live database.")
            return

        baseUrl = "https://mirror.ctan.org/systems/texlive/tlnet/archive"
        destDir = os.path.join(texliveDir, "tlpkg", "archive")
        os.makedirs(destDir, exist_ok=True)

        print(":: Proceed with installation? [Y/n] y")
        print(":: Retrieving and installing packages...")

        pkgs = []
        for p in packages:
            url = f"{baseUrl}/{p['name']}.tar.xz"
            pkgs.append({**p, 'url': url})

        self._downloadAll(pkgs, destDir, texliveDir)

    def installRemotePackages(self, texliveDir: str, ui=None) -> None:
        print(":: Downloading remote package database...")
        resp = requests.get(
            "https://mirror.ctan.org/systems/texlive/tlnet/tlpkg/texlive.tlpdb",
            timeout=120
        )
        resp.raise_for_status()
        remoteTlpdb = resp.text

        packages = self._parseTlpdb(remoteTlpdb)
        if not packages:
            print(":: No packages found in remote database.")
            return

        print(f":: {len(packages)} packages available. Installing...")

        destDir = os.path.join(texliveDir, "tlpkg", "archive")
        os.makedirs(destDir, exist_ok=True)

        baseUrl = "https://mirror.ctan.org/systems/texlive/tlnet/archive"
        pkgs = []
        for p in packages:
            url = f"{baseUrl}/{p['name']}.tar.xz"
            pkgs.append({**p, 'url': url})

        self._downloadAll(pkgs, destDir, texliveDir, ui)

        print(":: Registering packages in TeX Live Package Database...")
        tlpdbPath = os.path.join(texliveDir, "tlpkg", "texlive.tlpdb")
        with open(tlpdbPath, "w", encoding="utf-8") as f:
            f.write(remoteTlpdb)

    def _parseTlpdb(self, content: str) -> list[dict]:
        packages = []
        currentPkg: dict | None = None
        for line in content.splitlines():
            line = line.rstrip('\n')
            if not line:
                currentPkg = None
                continue
            if currentPkg is None:
                currentPkg = {}
                packages.append(currentPkg)

            if line.startswith("name ") and ' ' in line:
                currentPkg['name'] = line.split(' ', 1)[1]
            elif line.startswith("containersize ") and ' ' in line:
                try:
                    currentPkg['size'] = int(line.split(' ', 1)[1])
                except ValueError:
                    pass
            elif line.startswith("category ") and ' ' in line:
                cat = line.split(' ', 1)[1]
                currentPkg['category'] = cat

        result = []
        for pkg in packages:
            name = pkg.get('name')
            size = pkg.get('size', 0)
            if name and size > 0:
                result.append({'name': name, 'size': size})
        return result

    def _parsePackages(self, tlpdbPath: str) -> list[dict]:
        with open(tlpdbPath, "r", encoding="utf-8") as f:
            return self._parseTlpdb(f.read())

    def _downloadAll(self, packages: list[dict], destDir: str, installDir: str | None = None, ui=None) -> None:
        totalCount = len(packages)
        progressList = [DownloadProgress(p['name'], p['size']) for p in packages]
        totalProgress = DownloadProgress("Total", sum(p['size'] for p in packages))

        try:
            termHeight = os.get_terminal_size().lines
        except OSError:
            termHeight = 24
        scrollBottom = max(termHeight - 2, 3)

        reported: set[str] = set()
        failedCount = 0

        sys.stdout.write(f"\033[1;{scrollBottom}r")
        sys.stdout.write(f"\033[H")

        if ui:
            for p in packages:
                ui.info(p['name'], f"Installing {p['name']} library")

        sys.stdout.write(f"\033[{scrollBottom + 1};0H")
        sys.stdout.write("---------------------------------------------\033[K")
        barLine = self._buildTotalBar(totalProgress, 0, totalCount)
        sys.stdout.write(f"\033[{scrollBottom + 2};0H{barLine}\033[K")
        sys.stdout.write(f"\033[{scrollBottom};0H")
        sys.stdout.flush()

        running = True
        displayThread = threading.Thread(
            target=self._displayLoop,
            args=(progressList, totalProgress, totalCount, lambda: running, ui, reported, scrollBottom, installDir),
            daemon=True
        )
        displayThread.start()

        downloadThreads = self._threadingGS.downloadThreads

        # Phase 1: Download all packages (I/O-bound, high concurrency)
        with requests.Session() as session:
            adapter = HTTPAdapter(pool_connections=downloadThreads, pool_maxsize=downloadThreads)
            session.mount('https://', adapter)
            session.mount('http://', adapter)

            with ThreadPoolExecutor(max_workers=downloadThreads) as executor:
                futureMap = {}
                for i, pkg in enumerate(packages):
                    future = executor.submit(
                        self._downloadOne, pkg, destDir,
                        progressList[i], totalProgress, session
                    )
                    futureMap[future] = pkg['name']

                for future in as_completed(futureMap):
                    if future.exception():
                        failedCount += 1
                        totalProgress.name = f"Total ({failedCount} failed)"

        # Phase 2: Extract all packages (CPU-bound, controlled concurrency)
        if installDir:
            extractThreads = self._threadingGS.extractThreads
            with ThreadPoolExecutor(max_workers=extractThreads) as executor:
                futureMap = {}
                for i, pkg in enumerate(packages):
                    if not progressList[i].error:
                        future = executor.submit(
                            self._extractOne, pkg, destDir, installDir
                        )
                        futureMap[future] = pkg['name']

                for future in as_completed(futureMap):
                    name = futureMap[future]
                    try:
                        future.result()
                        if ui:
                            sys.stdout.write(f"\033[{scrollBottom};0H")
                            ui.ok(name, f"Successfully installed {name} package")
                    except Exception as e:
                        failedCount += 1
                        totalProgress.name = f"Total ({failedCount} failed)"
                        for p in progressList:
                            if p.name == name:
                                p.error = str(e)
                        if ui:
                            sys.stdout.write(f"\033[{scrollBottom};0H")
                            ui.fail(name, f"Installation failed for {name}: {e}")

        running = False
        displayThread.join(timeout=3)

        for p in progressList:
            if p.finished and p.name not in reported:
                reported.add(p.name)
                sys.stdout.write(f"\033[{scrollBottom};0H")
                if ui:
                    if p.error:
                        ui.fail(p.name, f"Installation failed for {p.name}: {p.error}")
                    else:
                        label = "installed" if installDir else "downloaded"
                        ui.ok(p.name, f"Successfully {label} {p.name} package")

        finalBar = self._buildTotalBar(totalProgress, len(reported), totalCount)
        sys.stdout.write(f"\033[{scrollBottom + 2};0H{finalBar}\033[K")
        sys.stdout.write(f"\033[{scrollBottom};0H")
        sys.stdout.write("\033[r")
        sys.stdout.flush()

    def _downloadOne(self, pkg: dict, destDir: str,
                     progress: DownloadProgress, totalProgress: DownloadProgress,
                     session: requests.Session) -> str:
        url = pkg['url']
        destPath = os.path.join(destDir, f"{pkg['name']}.tar.xz")
        try:
            alreadyCached = os.path.exists(destPath)
            if alreadyCached:
                progress.downloaded = progress.totalSize
                progress.percent = 100
                totalProgress.update(progress.totalSize)
            else:
                response = session.get(url, stream=True, timeout=60)
                response.raise_for_status()
                with open(destPath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            progress.update(len(chunk))
                            totalProgress.update(len(chunk))

            progress.finished = True
            progress.error = None
            return destPath
        except Exception as e:
            progress.error = str(e)
            raise

    def _extractOne(self, pkg: dict, destDir: str, installDir: str) -> None:
        destPath = os.path.join(destDir, f"{pkg['name']}.tar.xz")
        donePath = os.path.join(destDir, f"{pkg['name']}.done")
        if not os.path.exists(donePath):
            with tarfile.open(destPath, 'r:xz') as tar:
                tar.extractall(path=installDir)
            with open(donePath, 'w') as f:
                f.write("")

    def _displayLoop(self, progressList: list[DownloadProgress],
                     totalProgress: DownloadProgress, totalCount: int,
                     running: callable, ui, reported: set[str],
                     scrollBottom: int, installDir: str | None = None) -> None:
        while running():
            time.sleep(0.5)

            newCompleted = [p for p in progressList if p.finished and p.name not in reported]
            for p in newCompleted:
                reported.add(p.name)
                if ui:
                    sys.stdout.write(f"\033[{scrollBottom};0H")
                    if p.error:
                        ui.fail(p.name, f"Installation failed for {p.name}: {p.error}")
                    else:
                        label = "downloaded" if installDir else "installed"
                        ui.ok(p.name, f"Successfully {label} {p.name} package")

            if not ui:
                continue

            barLine = self._buildTotalBar(totalProgress, len(reported), totalCount)
            sys.stdout.write(f"\033[{scrollBottom + 2};0H{barLine}\033[K")
            sys.stdout.write(f"\033[{scrollBottom};0H")
            sys.stdout.flush()

    @staticmethod
    def _buildTotalBar(totalProgress: DownloadProgress, completedCount: int, totalCount: int) -> str:
        barLen = 30
        pct = int(completedCount * 100 / totalCount) if totalCount > 0 else 0
        filled = int(barLen * pct / 100)
        bar = '#' * filled + '-' * (barLen - filled)
        sizeStr = DownloadProgress._formatSize(totalProgress.totalSize)
        speed = totalProgress.speed if completedCount < totalCount else 0.0
        speedStr = DownloadProgress._formatSpeed(speed)
        elapsed = time.time() - totalProgress.startTime
        timeStr = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        return (f" Total ({completedCount}/{totalCount}) "
                f"{sizeStr:>8} {speedStr:>10} {timeStr} [{bar}] {pct:3d}%")
