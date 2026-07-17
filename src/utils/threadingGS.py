# src/utils/threadingGS.py
from __future__ import annotations
import os


class ThreadingGS:
    def __init__(self):
        cores = os.cpu_count() or 4
        self._max_threads = 128

        envDownload = os.environ.get("TEXLIVE_DOWNLOAD_THREADS")
        if envDownload is not None:
            self._download_threads = max(1, int(envDownload))
        else:
            self._download_threads = min(64, cores * 4)

        envExtract = os.environ.get("TEXLIVE_EXTRACT_THREADS")
        if envExtract is not None:
            self._extract_threads = max(1, int(envExtract))
        else:
            self._extract_threads = max(1, cores)

        self._available_threads = self._download_threads

    @property
    def availableThreads(self) -> int:
        return self._available_threads

    @availableThreads.setter
    def availableThreads(self, num_threads: int) -> None:
        if num_threads < 1:
            raise ValueError("Number of threads must be at least 1.")
        if num_threads > self._max_threads:
            raise ValueError(
                f"Number of threads cannot exceed the maximum system recommendation ({self._max_threads})."
            )
        self._available_threads = num_threads
        self._download_threads = num_threads

    @property
    def downloadThreads(self) -> int:
        return self._download_threads

    @downloadThreads.setter
    def downloadThreads(self, num_threads: int) -> None:
        if num_threads < 1:
            raise ValueError("Number of download threads must be at least 1.")
        if num_threads > self._max_threads:
            raise ValueError(
                f"Number of download threads cannot exceed {self._max_threads}."
            )
        self._download_threads = num_threads
        self._available_threads = num_threads

    @property
    def extractThreads(self) -> int:
        return self._extract_threads

    @extractThreads.setter
    def extractThreads(self, num_threads: int) -> None:
        if num_threads < 1:
            raise ValueError("Number of extraction threads must be at least 1.")
        if num_threads > self._max_threads:
            raise ValueError(
                f"Number of extraction threads cannot exceed {self._max_threads}."
            )
        self._extract_threads = num_threads