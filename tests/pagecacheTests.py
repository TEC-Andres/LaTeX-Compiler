from __future__ import annotations
import os
import sys
import tempfile
import shutil

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from services.texmake.auxparser import (
    parseAux, parseNav, parseOut, parseToc,
    detectTotalPages, extractPageLabelMap,
)
from services.texmake.diffengine import DiffEngine, PageDiff
from services.texmake.manifest import BuildManifest
from services.texmake._pagecache import NativeHash, NativeDiff, nativeAvailable


def testNativeAvailable():
    result = nativeAvailable()
    assert isinstance(result, bool)


def testNativeHashBuffer():
    data = b"hello world"
    h1 = NativeHash.buffer(data)
    h2 = NativeHash.buffer(data)
    assert h1 == h2
    assert len(h1) >= 16
    h3 = NativeHash.buffer(b"different")
    assert h1 != h3


def testNativeHashFile():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        f.write(b"test content for hashing")
        path = f.name
    try:
        h1 = NativeHash.file(path)
        h2 = NativeHash.file(path)
        assert h1 == h2
        assert len(h1) >= 16
    finally:
        os.unlink(path)


def testNativeDiffIdentical():
    diff = NativeDiff()
    lines = ["line1\n", "line2\n", "line3\n"]
    result = diff.diff(lines, lines)
    assert result == []


def testNativeDiffDifferent():
    diff = NativeDiff(context=1)
    old = ["a\n", "b\n", "c\n"]
    new = ["a\n", "x\n", "c\n"]
    result = diff.diff(old, new)
    assert len(result) > 0


def testParseAuxLabels():
    content = r"""
\relax
\newlabel{sec:intro}{{1}{1}}
\newlabel{fig:diagram}{{2.1}{3}}
\gdef \@abspage@last{5}
"""
    result = parseAux(content)
    assert "sec:intro" in result.labels
    assert result.labels["sec:intro"].page == 1
    assert "fig:diagram" in result.labels
    assert result.labels["fig:diagram"].page == 3
    assert result.pageCount == 5


def testParseNavBeamer():
    content = r"""
\headcommand {\slideentry {0}{0}{1}{1/1}{}{0}}
\headcommand {\beamer@framepages {1}{1}}
\headcommand {\slideentry {0}{0}{2}{2/2}{}{0}}
\headcommand {\beamer@framepages {2}{2}}
\headcommand {\sectionentry {1}{Introduction}{3}{Introduction}{0}}
\headcommand {\slideentry {1}{0}{1}{3/3}{}{0}}
\headcommand {\beamer@framepages {3}{3}}
\headcommand {\beamer@documentpages {3}}
"""
    result = parseNav(content)
    assert result.pageCount == 3
    assert len(result.framePages) == 3
    assert len(result.slides) == 3
    assert len(result.sections) == 1
    assert result.sections[0].title == "Introduction"
    assert result.sections[0].page == 3


def testParseOut():
    content = r"""
\contentsline {section}{\numberline {1}Introduction}{1}{section.1}
\contentsline {section}{\numberline {2}Methods}{5}{section.2}
"""
    result = parseOut(content)
    assert "Introduction" in result
    assert result["Introduction"] == 1
    assert "Methods" in result
    assert result["Methods"] == 5


def testParseToc():
    content = r"""
\contentsline {section}{\numberline {1}Related Work}{1}{section.1}
"""
    result = parseToc(content)
    assert "Related Work" in result
    assert result["Related Work"] == 1


def testDetectTotalPagesFromAux():
    content = r"\gdef \@abspage@last{12}"
    assert detectTotalPages(content) == 12


def testDetectTotalPagesFromNav():
    aux = ""
    nav = r"\headcommand {\beamer@documentpages {15}}"
    assert detectTotalPages(aux, nav) == 15


def testExtractPageLabelMap():
    auxContent = r"""
\newlabel{eq:energy}{{1}{2}}
\newlabel{eq:mass}{{2}{4}}
"""
    navContent = r"""
\headcommand {\sectionentry {1}{Introduction}{1}{Introduction}{0}}
"""
    result = extractPageLabelMap(auxContent, navContent)
    assert result["eq:energy"] == 2
    assert result["eq:mass"] == 4
    assert result["Introduction"] == 1


def testDiffEngineIdentical():
    engine = DiffEngine()
    content = r"""
\gdef \@abspage@last{3}
\newlabel{sec:intro}{{1}{1}}
"""
    result = engine.diffIntermediates(content, content, content, content)
    assert len(result.dirtyPages) == 0


def testDiffEngineNewPages():
    engine = DiffEngine()
    oldAux = r"\gdef \@abspage@last{3}"
    newAux = r"\gdef \@abspage@last{5}"
    result = engine.diffIntermediates(None, None, oldAux, newAux)
    assert result.totalPagesOld == 3
    assert result.totalPagesNew == 5
    assert 4 in result.addedPages
    assert 5 in result.addedPages


def testDiffEngineLabelChange():
    engine = DiffEngine()
    oldAux = r"""
\gdef \@abspage@last{3}
\newlabel{sec:intro}{{1}{1}}
"""
    newAux = r"""
\gdef \@abspage@last{3}
\newlabel{sec:intro}{{1}{1}}
\newlabel{fig:new}{{2.1}{2}}
"""
    result = engine.diffIntermediates(None, None, oldAux, newAux)
    assert 2 in result.dirtyPages


def testDiffEngineSourceComparison():
    engine = DiffEngine()
    old = {"file1.tex": "content1", "file2.tex": "content2"}
    new = {"file1.tex": "content1", "file2.tex": "changed"}
    changed = engine.diffSources(old, new)
    assert "file2.tex" in changed
    assert "file1.tex" not in changed


def testDiffEngineSourceAddedRemoved():
    engine = DiffEngine()
    old = {"file1.tex": "content1"}
    new = {"file1.tex": "content1", "file3.tex": "content3"}
    changed = engine.diffSources(old, new)
    assert "file3.tex" in changed


def testDiffEngineLineDiff():
    engine = DiffEngine()
    old = "line1\nline2\nline3\n"
    new = "line1\nchanged\nline3\n"
    hunks = engine.computeLineDiff(old, new)
    assert len(hunks) > 0


def testPropagationAnalysis():
    engine = DiffEngine()
    source = r"""
\section{Intro}
Some text here.
\newpage
\section{Methods}
More text.
\newpage
\section{Results}
Final text.
"""
    result = engine.analyzePropagation(source, {2}, 3)
    assert isinstance(result, set)
    assert len(result) > 0


def testManifestCreateSave():
    with tempfile.TemporaryDirectory() as tmpDir:
        manifest = BuildManifest(tmpDir)
        manifest.setPageCount(5)
        manifest.save()
        assert os.path.isfile(manifest.manifestPath)
        manifest2 = BuildManifest(tmpDir)
        assert manifest2.getPageCount() == 5


def testManifestSourceHashing():
    with tempfile.TemporaryDirectory() as tmpDir:
        filePath = os.path.join(tmpDir, "test.tex")
        with open(filePath, "w") as f:
            f.write("test content")
        manifest = BuildManifest(tmpDir)
        manifest.updateSourceHashes([filePath])
        assert not manifest.sourceChanged(filePath)
        with open(filePath, "w") as f:
            f.write("modified content")
        assert manifest.sourceChanged(filePath)


def testManifestSnapshot():
    with tempfile.TemporaryDirectory() as tmpDir:
        cacheDir = os.path.join(tmpDir, "__texcache__")
        os.makedirs(cacheDir)
        with open(os.path.join(cacheDir, "main.aux"), "w") as f:
            f.write("old aux content")
        with open(os.path.join(cacheDir, "main.nav"), "w") as f:
            f.write("old nav content")
        manifest = BuildManifest(tmpDir)
        manifest.snapshotIntermediates("main")
        with open(os.path.join(cacheDir, "main.aux"), "w") as f:
            f.write("new aux content")
        oldContent = manifest.readSnapshot("main", ".aux")
        newContent = manifest.readCurrent("main", ".aux")
        assert oldContent == "old aux content"
        assert newContent == "new aux content"


def testManifestClear():
    with tempfile.TemporaryDirectory() as tmpDir:
        cacheDir = os.path.join(tmpDir, "__texcache__")
        os.makedirs(cacheDir)
        with open(os.path.join(cacheDir, "test.txt"), "w") as f:
            f.write("test")
        manifest = BuildManifest(tmpDir)
        manifest.setPageCount(5)
        manifest.save()
        manifest.clear()
        assert not os.path.isdir(cacheDir)


def testBuildResultSlots():
    from services.texmake.builder import BuildResult
    result = BuildResult()
    assert result.pdfPaths == []
    assert result.pageDiff is None
    assert result.sourcesChanged == []
    assert result.skipped is False


def testPageDiffNeedsFullRecompile():
    diff = PageDiff()
    diff.totalPagesNew = 10
    diff.dirtyPages = {1, 2, 3}
    assert not diff.needsFullRecompile
    diff.dirtyPages = set(range(1, 9))
    assert diff.needsFullRecompile


def testPageDiffPageRange():
    diff = PageDiff()
    diff.dirtyPages = {3, 5, 7}
    assert diff.pageRange == (3, 7)
    diff.dirtyPages = set()
    assert diff.pageRange == (0, 0)


if __name__ == "__main__":
    tests = [value for key, value in sorted(globals().items()) if key.startswith("test")]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"  OK {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAILED {test.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {test.__name__}: {e!r}")
    print(f"{passed}/{len(tests)} tests passed")
    sys.exit(0 if passed == len(tests) else 1)
