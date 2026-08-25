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
    __slots__ = ("section", "subsection", "slide", "page", "totalPages", "label", "hoffset")

    def __init__(self, section: int, subsection: int, slide: int,
                 page: int, totalPages: int, label: str, hoffset: int):
        self.section = section
        self.subsection = subsection
        self.slide = slide
        self.page = page
        self.totalPages = totalPages
        self.label = label
        self.hoffset = hoffset

    def __repr__(self) -> str:
        return f"SlideEntry(section={self.section}, slide={self.slide}, page={self.page})"


class SectionEntry:
    __slots__ = ("number", "title", "page", "titleCopy", "beamer")

    def __init__(self, number: int, title: str, page: int, titleCopy: str, beamer: int):
        self.number = number
        self.title = title
        self.page = page
        self.titleCopy = titleCopy
        self.beamer = beamer

    def __repr__(self) -> str:
        return f"SectionEntry({self.number}, {self.title!r}, page={self.page})"


class AuxPageMap:
    __slots__ = ("labels", "slides", "sections", "framePages", "totalPages", "pageCount")

    def __init__(self) -> None:
        self.labels: dict[str, LabelInfo] = {}
        self.slides: list[SlideEntry] = []
        self.sections: list[SectionEntry] = []
        self.framePages: list[tuple[int, int]] = []
        self.totalPages: int = 0
        self.pageCount: int = 0

    def __repr__(self) -> str:
        return (
            f"AuxPageMap(labels={len(self.labels)}, slides={len(self.slides)}, "
            f"sections={len(self.sections)}, pages={self.pageCount})"
        )


def parseAux(content: str) -> AuxPageMap:
    result = AuxPageMap()
    for m in _NEWLABEL_RE.finditer(content):
        name = m.group(1)
        value = m.group(2)
        page = int(m.group(3))
        anchor = m.group(4) if m.group(4) else ""
        result.labels[name] = LabelInfo(name, value, page, anchor)
    m = _ABSPAGE_RE.search(content)
    if m:
        result.pageCount = int(m.group(1))
        result.totalPages = result.pageCount
    return result


def parseNav(content: str) -> AuxPageMap:
    result = AuxPageMap()
    for m in _FRAMEPAGES_RE.finditer(content):
        result.framePages.append((int(m.group(1)), int(m.group(2))))
    for m in _SLIDEENTRY_RE.finditer(content):
        result.slides.append(SlideEntry(
            section=int(m.group(1)),
            subsection=int(m.group(2)),
            slide=int(m.group(3)),
            page=int(m.group(4)),
            totalPages=int(m.group(5)),
            label=m.group(6),
            hoffset=int(m.group(7)),
        ))
    for m in _SECTIONENTRY_RE.finditer(content):
        result.sections.append(SectionEntry(
            number=int(m.group(1)),
            title=m.group(2),
            page=int(m.group(3)),
            titleCopy=m.group(4),
            beamer=int(m.group(5)),
        ))
    m = _DOCUMENTPAGES_RE.search(content)
    if m:
        result.pageCount = int(m.group(1))
    elif result.framePages:
        last = result.framePages[-1]
        result.pageCount = last[1]
    return result


def parseOut(content: str) -> dict[str, int]:
    pages: dict[str, int] = {}
    for m in re.finditer(r"\\contentsline\s*\{[^}]*\}\{\\numberline\s*\{([^}]*)\}([^}]*)\}\{(\d+)\}", content):
        pages[m.group(2).strip()] = int(m.group(3))
    return pages


def parseToc(content: str) -> dict[str, int]:
    pages: dict[str, int] = {}
    for m in re.finditer(r"\\contentsline\s*\{[^}]*\}\{\\numberline\s*\{([^}]*)\}([^}]*)\}\{(\d+)\}", content):
        pages[m.group(2).strip()] = int(m.group(3))
    return pages


def detectTotalPages(auxContent: str, navContent: str | None = None) -> int:
    if navContent:
        m = _DOCUMENTPAGES_RE.search(navContent)
        if m:
            return int(m.group(1))
    m = _ABSPAGE_RE.search(auxContent)
    if m:
        return int(m.group(1))
    return 0


def extractPageLabelMap(auxContent: str, navContent: str | None = None) -> dict[str, int]:
    result: dict[str, int] = {}
    aux = parseAux(auxContent)
    for name, info in aux.labels.items():
        result[name] = info.page
    if navContent:
        nav = parseNav(navContent)
        for section in nav.sections:
            result[section.title] = section.page
    return result
