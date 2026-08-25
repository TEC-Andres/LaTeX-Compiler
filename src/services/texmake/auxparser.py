from __future__ import annotations
import re

_NEWLABEL_RE = re.compile(
    r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}\{(\d+)\}"
    r"(?:\{[^}]*\}\{[^}]*\}\{([^}]*)\})?"
)
_FRAMEPAGES_RE = re.compile(r"\\beamer@framepages\s*\{(\d+)\}\{(\d+)\}")
_SLIDEENTRY_RE = re.compile(
    r"\\slideentry\s*\{(\d+)\}\{(\d+)\}\{(\d+)\}\{(\d+)/(\d+)\}\{([^}]*)\}\{(\d+)\}"
)
_SECTIONENTRY_RE = re.compile(
    r"\\sectionentry\s*\{(\d+)\}\{([^}]+)\}\{(\d+)\}\{([^}]+)\}\{(\d+)\}"
)
_SECTIONPAGES_RE = re.compile(r"\\beamer@sectionpages\s*\{(\d+)\}\{(\d+)\}")
_SUBSECTIONPAGES_RE = re.compile(r"\\beamer@subsectionpages\s*\{(\d+)\}\{(\d+)\}")
_DOCUMENTPAGES_RE = re.compile(r"\\beamer@documentpages\s*\{(\d+)\}")
_ABSPAGE_RE = re.compile(r"\\gdef\s+\\@abspage@last\{(\d+)\}")
_TOC_SECTION_RE = re.compile(
    r"\\beamer@sectionintoc\s*\{(\d+)\}\{([^}]+)\}\{(\d+)\}\{(\d+)\}\{(\d+)\}"
)
_PGFMARK_RE = re.compile(r"\\pgfsyspdfmark\s*\{([^}]+)\}\{(\d+)\}\{(\d+)\}")


class LabelInfo:
    __slots__ = ("name", "value", "page", "anchor")

    def __init__(self, name: str, value: str, page: int, anchor: str = ""):
        self.name = name
        self.value = value
        self.page = page
        self.anchor = anchor

    def __repr__(self) -> str:
        return f"LabelInfo({self.name!r}, page={self.page})"


class SlideEntry:
    __slots__ = ("section", "subsection", "slide", "page", "total_pages", "label", "hoffset")

    def __init__(self, section: int, subsection: int, slide: int,
                 page: int, total_pages: int, label: str, hoffset: int):
        self.section = section
        self.subsection = subsection
        self.slide = slide
        self.page = page
        self.total_pages = total_pages
        self.label = label
        self.hoffset = hoffset

    def __repr__(self) -> str:
        return f"SlideEntry(section={self.section}, slide={self.slide}, page={self.page})"


class SectionEntry:
    __slots__ = ("number", "title", "page", "title_copy", "beamer")

    def __init__(self, number: int, title: str, page: int, title_copy: str, beamer: int):
        self.number = number
        self.title = title
        self.page = page
        self.title_copy = title_copy
        self.beamer = beamer

    def __repr__(self) -> str:
        return f"SectionEntry({self.number}, {self.title!r}, page={self.page})"


class AuxPageMap:
    """Parsed page-level metadata extracted from .aux/.nav files."""

    def __init__(self) -> None:
        self.labels: dict[str, LabelInfo] = {}
        self.slides: list[SlideEntry] = []
        self.sections: list[SectionEntry] = []
        self.frame_pages: list[tuple[int, int]] = []
        self.total_pages: int = 0
        self.page_count: int = 0

    def __repr__(self) -> str:
        return (
            f"AuxPageMap(labels={len(self.labels)}, slides={len(self.slides)}, "
            f"sections={len(self.sections)}, pages={self.page_count})"
        )


def parse_aux(content: str) -> AuxPageMap:
    """Parse a .aux file and extract label-to-page mappings."""
    result = AuxPageMap()
    for m in _NEWLABEL_RE.finditer(content):
        name = m.group(1)
        value = m.group(2)
        page = int(m.group(3))
        anchor = m.group(4) if m.group(4) else ""
        result.labels[name] = LabelInfo(name, value, page, anchor)
    m = _ABSPAGE_RE.search(content)
    if m:
        result.page_count = int(m.group(1))
        result.total_pages = result.page_count
    return result


def parse_nav(content: str) -> AuxPageMap:
    """Parse a .nav file (beamer) and extract slide/frame/section mappings."""
    result = AuxPageMap()
    for m in _FRAMEPAGES_RE.finditer(content):
        result.frame_pages.append((int(m.group(1)), int(m.group(2))))
    for m in _SLIDEENTRY_RE.finditer(content):
        result.slides.append(SlideEntry(
            section=int(m.group(1)),
            subsection=int(m.group(2)),
            slide=int(m.group(3)),
            page=int(m.group(4)),
            total_pages=int(m.group(5)),
            label=m.group(6),
            hoffset=int(m.group(7)),
        ))
    for m in _SECTIONENTRY_RE.finditer(content):
        result.sections.append(SectionEntry(
            number=int(m.group(1)),
            title=m.group(2),
            page=int(m.group(3)),
            title_copy=m.group(4),
            beamer=int(m.group(5)),
        ))
    m = _DOCUMENTPAGES_RE.search(content)
    if m:
        result.page_count = int(m.group(1))
    elif result.frame_pages:
        last = result.frame_pages[-1]
        result.page_count = last[1]
    return result


def parse_out(content: str) -> dict[str, int]:
    """Parse a .out file and extract bookmark page mappings."""
    pages: dict[str, int] = {}
    for m in re.finditer(r"\\contentsline\s*\{[^}]*\}\{\\numberline\s*\{([^}]*)\}([^}]*)\}\{(\d+)\}", content):
        pages[m.group(2).strip()] = int(m.group(3))
    return pages


def parse_toc(content: str) -> dict[str, int]:
    """Parse a .toc file and extract section page mappings."""
    pages: dict[str, int] = {}
    for m in re.finditer(r"\\contentsline\s*\{[^}]*\}\{\\numberline\s*\{([^}]*)\}([^}]*)\}\{(\d+)\}", content):
        pages[m.group(2).strip()] = int(m.group(3))
    return pages


def detect_total_pages(aux_content: str, nav_content: str | None = None) -> int:
    """Extract total page count from available intermediate files."""
    if nav_content:
        m = _DOCUMENTPAGES_RE.search(nav_content)
        if m:
            return int(m.group(1))
    m = _ABSPAGE_RE.search(aux_content)
    if m:
        return int(m.group(1))
    return 0


def extract_page_label_map(aux_content: str, nav_content: str | None = None) -> dict[str, int]:
    """Extract a combined mapping of label/section names to page numbers."""
    result: dict[str, int] = {}
    aux = parse_aux(aux_content)
    for name, info in aux.labels.items():
        result[name] = info.page
    if nav_content:
        nav = parse_nav(nav_content)
        for section in nav.sections:
            result[section.title] = section.page
    return result
