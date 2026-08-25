from __future__ import annotations
import re

from ._pagecache import NativeDiff
from .auxparser import AuxPageMap, parseAux, parseNav, extractPageLabelMap

_NEWPAGE_COMMANDS = re.compile(
    r"\\(?:newpage|cleardoublepage|clearpage|pagebreak|section\*?\{|chapter\*?\{)",
    re.MULTILINE,
)
_FRAME_COMMANDS = re.compile(r"\\begin\{frame\}", re.MULTILINE)


class PageDiff:
    __slots__ = (
        "dirtyPages", "addedPages", "removedPages",
        "propagated", "totalPagesOld", "totalPagesNew",
        "labelChanges", "sectionChanges",
    )

    def __init__(self) -> None:
        self.dirtyPages: set[int] = set()
        self.addedPages: set[int] = set()
        self.removedPages: set[int] = set()
        self.propagated: bool = False
        self.totalPagesOld: int = 0
        self.totalPagesNew: int = 0
        self.labelChanges: dict[str, tuple[int, int]] = {}
        self.sectionChanges: dict[str, tuple[int, int]] = {}

    @property
    def needsFullRecompile(self) -> bool:
        return self.propagated or len(self.dirtyPages) > self.totalPagesNew * 0.5

    @property
    def pageRange(self) -> tuple[int, int]:
        if not self.dirtyPages:
            return (0, 0)
        return (min(self.dirtyPages), max(self.dirtyPages))

    def __repr__(self) -> str:
        return (
            f"PageDiff(dirty={sorted(self.dirtyPages)}, "
            f"added={sorted(self.addedPages)}, "
            f"propagated={self.propagated})"
        )


class DiffEngine:
    def __init__(self, context: int = 3):
        self._nativeDiff = NativeDiff(context)

    def diffIntermediates(
        self,
        oldNav: str | None,
        newNav: str | None,
        oldAux: str | None,
        newAux: str | None,
    ) -> PageDiff:
        result = PageDiff()

        oldMap = self._extractPageMap(oldNav, oldAux)
        newMap = self._extractPageMap(newNav, newAux)

        result.totalPagesOld = self._getTotalPages(oldNav, oldAux)
        result.totalPagesNew = self._getTotalPages(newNav, newAux)

        if result.totalPagesOld == 0 and result.totalPagesNew == 0:
            return result

        if result.totalPagesNew < result.totalPagesOld:
            removed = set(range(result.totalPagesNew + 1, result.totalPagesOld + 1))
            result.removedPages = removed
            result.dirtyPages = removed
            return result

        if result.totalPagesNew > result.totalPagesOld:
            added = set(range(result.totalPagesOld + 1, result.totalPagesNew + 1))
            result.addedPages = added
            result.dirtyPages = added

        for name, oldPage in oldMap.items():
            newPage = newMap.get(name)
            if newPage is None:
                if oldPage <= result.totalPagesNew:
                    result.dirtyPages.add(oldPage)
            elif newPage != oldPage:
                result.labelChanges[name] = (oldPage, newPage)
                result.dirtyPages.add(newPage)
                if oldPage != newPage:
                    result.dirtyPages.add(oldPage)

        for name, newPage in newMap.items():
            if name not in oldMap:
                result.dirtyPages.add(newPage)

        if oldNav and newNav:
            navDiff = self._diffNavEntries(oldNav, newNav)
            if navDiff:
                result.dirtyPages.update(navDiff)

        return result

    def analyzePropagation(
        self,
        sourceContent: str,
        dirtyPages: set[int],
        pageCount: int,
    ) -> set[int]:
        boundaries = self._findPageBoundaries(sourceContent, pageCount)
        if not boundaries:
            return dirtyPages

        expanded: set[int] = set()
        for page in dirtyPages:
            boundary = self._findBoundaryForPage(boundaries, page)
            if boundary is not None:
                nextBoundary = self._findNextBoundary(boundaries, boundary)
                if nextBoundary is not None:
                    hasPropagation = self._checkPropagation(
                        sourceContent, page, nextBoundary
                    )
                    if hasPropagation:
                        for p in range(page, nextBoundary + 1):
                            expanded.add(p)
                        continue
            expanded.add(page)

        return expanded

    def diffSources(self, oldSources: dict[str, str], newSources: dict[str, str]) -> set[str]:
        changed: set[str] = set()
        allFiles = set(oldSources) | set(newSources)
        for path in allFiles:
            old = oldSources.get(path)
            new = newSources.get(path)
            if old != new:
                changed.add(path)
        return changed

    def computeLineDiff(self, oldText: str, newText: str) -> list[tuple[int, int, int, int]]:
        oldLines = oldText.splitlines(keepends=True)
        newLines = newText.splitlines(keepends=True)
        return self._nativeDiff.diff(oldLines, newLines)

    def diffAuxFiles(self, oldAux: str, newAux: str) -> list[tuple[int, int, int, int]]:
        return self.computeLineDiff(oldAux, newAux)

    def _extractPageMap(self, nav: str | None, aux: str | None) -> dict[str, int]:
        combined: dict[str, int] = {}
        if aux:
            auxMap = extractPageLabelMap(aux)
            combined.update(auxMap)
        if nav:
            navMap = extractPageLabelMap(aux or "", nav)
            for key, val in navMap.items():
                if key not in combined:
                    combined[key] = val
        return combined

    @staticmethod
    def _getTotalPages(nav: str | None, aux: str | None) -> int:
        from .auxparser import detectTotalPages
        return detectTotalPages(aux or "", nav)

    def _diffNavEntries(self, oldNav: str, newNav: str) -> set[int]:
        oldEntries = set(re.findall(r"\\slideentry\s*\{[^}]+\}", oldNav))
        newEntries = set(re.findall(r"\\slideentry\s*\{[^}]+\}", newNav))

        affected: set[int] = set()
        if oldEntries != newEntries:
            oldSlides = parseNav(oldNav)
            newSlides = parseNav(newNav)
            oldSlidePages = {s.page for s in oldSlides.slides}
            newSlidePages = {s.page for s in newSlides.slides}
            affected = oldSlidePages.symmetric_difference(newSlidePages)
        return affected

    @staticmethod
    def _findPageBoundaries(source: str, pageCount: int) -> list[int]:
        boundaries: list[int] = []
        lines = source.split("\n")
        currentPage = 1
        for line in lines:
            if _NEWPAGE_COMMANDS.search(line):
                currentPage += 1
                if currentPage <= pageCount:
                    boundaries.append(currentPage)
            elif _FRAME_COMMANDS.search(line):
                currentPage += 1
                if currentPage <= pageCount:
                    boundaries.append(currentPage)
        return boundaries

    @staticmethod
    def _findBoundaryForPage(boundaries: list[int], page: int) -> int | None:
        for b in boundaries:
            if b >= page:
                return b
        return boundaries[-1] if boundaries else None

    @staticmethod
    def _findNextBoundary(boundaries: list[int], current: int) -> int | None:
        for b in boundaries:
            if b > current:
                return b
        return None

    @staticmethod
    def _checkPropagation(source: str, page: int, nextBoundary: int) -> bool:
        lines = source.split("\n")
        currentPage = 1
        inBoundaryRange = False
        for line in lines:
            if _FRAME_COMMANDS.search(line) or _NEWPAGE_COMMANDS.search(line):
                currentPage += 1
            if currentPage == page:
                inBoundaryRange = True
            elif currentPage >= nextBoundary:
                break
            if inBoundaryRange:
                if re.search(r"\\label\{", line):
                    return True
                if re.search(r"\\(?:addtocontents|addtocounter|setcounter)", line):
                    return True
        return False
