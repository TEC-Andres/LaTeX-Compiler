from __future__ import annotations
import re

from ._pagecache import NativeDiff
from .auxparser import AuxPageMap, parse_aux, parse_nav, extract_page_label_map

_NEWPAGE_COMMANDS = re.compile(
    r"\\(?:newpage|cleardoublepage|clearpage|pagebreak|section\*?\{|chapter\*?\{)",
    re.MULTILINE,
)
_FRAME_COMMANDS = re.compile(r"\\begin\{frame\}", re.MULTILINE)


class PageDiff:
    """Result of comparing two builds' page-level state."""

    __slots__ = (
        "dirty_pages", "added_pages", "removed_pages",
        "propagated", "total_pages_old", "total_pages_new",
        "label_changes", "section_changes",
    )

    def __init__(self) -> None:
        self.dirty_pages: set[int] = set()
        self.added_pages: set[int] = set()
        self.removed_pages: set[int] = set()
        self.propagated: bool = False
        self.total_pages_old: int = 0
        self.total_pages_new: int = 0
        self.label_changes: dict[str, tuple[int, int]] = {}
        self.section_changes: dict[str, tuple[int, int]] = {}

    @property
    def needs_full_recompile(self) -> bool:
        return self.propagated or len(self.dirty_pages) > self.total_pages_new * 0.5

    @property
    def page_range(self) -> tuple[int, int]:
        if not self.dirty_pages:
            return (0, 0)
        return (min(self.dirty_pages), max(self.dirty_pages))

    def __repr__(self) -> str:
        return (
            f"PageDiff(dirty={sorted(self.dirty_pages)}, "
            f"added={sorted(self.added_pages)}, "
            f"propagated={self.propagated})"
        )


class DiffEngine:
    """Compares intermediate files between builds to detect page-level changes."""

    def __init__(self, context: int = 3):
        self._native_diff = NativeDiff(context)

    def diff_intermediates(
        self,
        old_nav: str | None,
        new_nav: str | None,
        old_aux: str | None,
        new_aux: str | None,
    ) -> PageDiff:
        result = PageDiff()

        old_map = self._extract_page_map(old_nav, old_aux)
        new_map = self._extract_page_map(new_nav, new_aux)

        result.total_pages_old = self._get_total_pages(old_nav, old_aux)
        result.total_pages_new = self._get_total_pages(new_nav, new_aux)

        if result.total_pages_old == 0 and result.total_pages_new == 0:
            return result

        if result.total_pages_new < result.total_pages_old:
            removed = set(range(result.total_pages_new + 1, result.total_pages_old + 1))
            result.removed_pages = removed
            result.dirty_pages = removed
            return result

        if result.total_pages_new > result.total_pages_old:
            added = set(range(result.total_pages_old + 1, result.total_pages_new + 1))
            result.added_pages = added
            result.dirty_pages = added

        for name, old_page in old_map.items():
            new_page = new_map.get(name)
            if new_page is None:
                if old_page <= result.total_pages_new:
                    result.dirty_pages.add(old_page)
            elif new_page != old_page:
                result.label_changes[name] = (old_page, new_page)
                result.dirty_pages.add(new_page)
                if old_page != new_page:
                    result.dirty_pages.add(old_page)

        for name, new_page in new_map.items():
            if name not in old_map:
                result.dirty_pages.add(new_page)

        if old_nav and new_nav:
            nav_diff = self._diff_nav_entries(old_nav, new_nav)
            if nav_diff:
                result.dirty_pages.update(nav_diff)

        return result

    def analyze_propagation(
        self,
        source_content: str,
        dirty_pages: set[int],
        page_count: int,
    ) -> set[int]:
        """If a change doesn't cross \\newpage, it's isolated. Otherwise propagate."""
        boundaries = self._find_page_boundaries(source_content, page_count)
        if not boundaries:
            return dirty_pages

        expanded: set[int] = set()
        for page in dirty_pages:
            boundary = self._find_boundary_for_page(boundaries, page)
            if boundary is not None:
                next_boundary = self._find_next_boundary(boundaries, boundary)
                if next_boundary is not None:
                    has_propagation = self._check_propagation(
                        source_content, page, next_boundary
                    )
                    if has_propagation:
                        for p in range(page, next_boundary + 1):
                            expanded.add(p)
                        continue
            expanded.add(page)

        return expanded

    def diff_sources(self, old_sources: dict[str, str], new_sources: dict[str, str]) -> set[str]:
        """Compare source file contents, return set of changed file paths."""
        changed: set[str] = set()
        all_files = set(old_sources) | set(new_sources)
        for path in all_files:
            old = old_sources.get(path)
            new = new_sources.get(path)
            if old != new:
                changed.add(path)
        return changed

    def compute_line_diff(self, old_text: str, new_text: str) -> list[tuple[int, int, int, int]]:
        """Compute line-level diff between two text contents using native diff."""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        return self._native_diff.diff(old_lines, new_lines)

    def diff_aux_files(self, old_aux: str, new_aux: str) -> list[tuple[int, int, int, int]]:
        """Compute line-level diff between two .aux file contents."""
        return self.compute_line_diff(old_aux, new_aux)

    def _extract_page_map(self, nav: str | None, aux: str | None) -> dict[str, int]:
        combined: dict[str, int] = {}
        if aux:
            aux_map = extract_page_label_map(aux)
            combined.update(aux_map)
        if nav:
            nav_map = extract_page_label_map(aux or "", nav)
            for key, val in nav_map.items():
                if key not in combined:
                    combined[key] = val
        return combined

    @staticmethod
    def _get_total_pages(nav: str | None, aux: str | None) -> int:
        from .auxparser import detect_total_pages
        return detect_total_pages(aux or "", nav)

    def _diff_nav_entries(self, old_nav: str, new_nav: str) -> set[int]:
        old_entries = set(re.findall(r"\\slideentry\s*\{[^}]+\}", old_nav))
        new_entries = set(re.findall(r"\\slideentry\s*\{[^}]+\}", new_nav))

        affected: set[int] = set()
        if old_entries != new_entries:
            old_slides = parse_nav(old_nav)
            new_slides = parse_nav(new_nav)
            old_slide_pages = {s.page for s in old_slides.slides}
            new_slide_pages = {s.page for s in new_slides.slides}
            affected = old_slide_pages.symmetric_difference(new_slide_pages)
        return affected

    @staticmethod
    def _find_page_boundaries(source: str, page_count: int) -> list[int]:
        boundaries: list[int] = []
        lines = source.split("\n")
        current_page = 1
        for line in lines:
            if _NEWPAGE_COMMANDS.search(line):
                current_page += 1
                if current_page <= page_count:
                    boundaries.append(current_page)
            elif _FRAME_COMMANDS.search(line):
                current_page += 1
                if current_page <= page_count:
                    boundaries.append(current_page)
        return boundaries

    @staticmethod
    def _find_boundary_for_page(boundaries: list[int], page: int) -> int | None:
        for b in boundaries:
            if b >= page:
                return b
        return boundaries[-1] if boundaries else None

    @staticmethod
    def _find_next_boundary(boundaries: list[int], current: int) -> int | None:
        for b in boundaries:
            if b > current:
                return b
        return None

    @staticmethod
    def _check_propagation(source: str, page: int, next_boundary: int) -> bool:
        lines = source.split("\n")
        current_page = 1
        in_boundary_range = False
        for line in lines:
            if _FRAME_COMMANDS.search(line) or _NEWPAGE_COMMANDS.search(line):
                current_page += 1
            if current_page == page:
                in_boundary_range = True
            elif current_page >= next_boundary:
                break
            if in_boundary_range:
                if re.search(r"\\label\{", line):
                    return True
                if re.search(r"\\(?:addtocontents|addtocounter|setcounter)", line):
                    return True
        return False
