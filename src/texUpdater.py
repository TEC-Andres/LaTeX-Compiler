"""
The following file is to be run as a standalone script to update TeX Live. It checks for the 
latest version of TeX Live, compares it with the local version, and if an update is available, 
it downloads and installs the update. The script also handles elevation on Windows to ensure 
that it has the necessary permissions to perform the update.

Usage:
    python texUpdater.py

This script is designed to be run in an environment where TeX Live is installed and accessible via 
the command line. It will print the current local version, the latest online version, and whether an 
update is needed. If an update is performed, it will also print the new local version after the 
update.

Note:
- The script requires an internet connection to check for the latest version and download updates.
- On Windows, the script will attempt to elevate permissions if it is not run as an administrator.
- The script uses the 'requests' library to fetch online data. Ensure that this library is installed 
in your Python environment.
- The script assumes that the TeX Live directory structure is standard and that the 'tlmgr' command 
is available in the system PATH.
- The script will pause at the end, waiting for user input before exiting, to allow the user to 
review the output.
"""

from __future__ import annotations
import ctypes
import sys
import time

from dependencies import texlive
from services._updater import UpdaterService
from utils.texthandler import TextHandler


def _elevate() -> None:
    if sys.platform != "win32":
        return
    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except AttributeError:
        return
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, " ".join(sys.argv), None, 1
    )
    sys.exit()


def _progressSteps(ui: TextHandler, category: str, steps: int, interval: float) -> None:
    for pct in range(0, 100, max(1, 100 // steps)):
        ui.loadingPercentage(category, pct)
        time.sleep(interval)
    ui.loadingPercentage(category, 99)


if __name__ == "__main__":
    _elevate()
    begin = time.time()
    ui = TextHandler()

    localVer = texlive.getLocalTexVersion()
    ui.info("Info", f"TeX Live directory: {texlive.getTexLiveDir()}")
    ui.info("Info", f"Local TeX Live version: {localVer}")
    ui.info("Info", f"Online TeX Live version: {texlive.getOnlineTexVersion()}")

    if localVer is None:
        ui.info("Setup", "TeX Live not detected. Installing standalone version...")
        installer = UpdaterService()

        _progressSteps(ui, "Installing TeX Live", 10, 0.15)
        installer.installTexLive()
        ui.loadingPercentage("Installing TeX Live", 100, success=True, successMsg="TeX Live base installed")

        texliveDir = texlive.getTexLiveDir()
        if texliveDir:
            ui.info("Setup", "Installing all libraries via remote updater...")
            installer.installRemotePackages(texliveDir, ui)
            ui.loadingPercentage("Libraries", 100, success=True, successMsg="All libraries installed")

            ui.info("Setup", "Running post-install steps (mktexlsr, fmtutil-sys, updmap-sys)...")
            texlive._runPostInstall(texliveDir)
            ui.ok("Setup", "Post-install steps completed")

        ui.ok("Setup", "Installation complete")
        ui.info("Info", f"Local TeX Live version: {texlive.getLocalTexVersion()}")
    else:
        ui.info("Status", f"Is TeX Live up to date? {texlive.isTexLiveUpToDate()}")
        ui.info("Status", "Updating TeX Live...")
        _progressSteps(ui, "Updating", 15, 0.1)
        texlive.updateTexLive()
        ui.loadingPercentage("Updating", 100, success=True, successMsg="TeX Live updated")
        ui.info("Info", f"Local TeX Live version after update: {texlive.getLocalTexVersion()}")
        ui.info("Status", f"Is TeX Live up to date after update? {texlive.isTexLiveUpToDate()}")

    end = time.time()
    ui.info("Info", f"Execution time: {end - begin:.2f} seconds")
    input("Press Enter to exit...")
