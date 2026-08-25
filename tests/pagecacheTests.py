from __future__ import annotations
import os
import sys
import tempfile
import shutil

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from services.texmake.auxparser import (
    parse_aux, parse_nav, parse_out, parse_toc,
    detect_total_pages, extract_page_label_map,
)
from services.texmake.diffengine import DiffEngine, PageDiff
from services.texmake.manifest import BuildManifest
from services.texmake._pagecache import NativeHash, NativeDiff, native_available


def testNativeAvailable():
    result = native_available()
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
    result = parse_aux(content)
    assert "sec:intro" in result.labels
    assert result.labels["sec:intro"].page == 1
    assert "fig:diagram" in result.labels
    assert result.labels["fig:diagram"].page == 3
    assert result.page_count == 5


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
    result = parse_nav(content)
    assert result.page_count == 3
    assert len(result.frame_pages) == 3
    assert len(result.slides) == 3
    assert len(result.sections) == 1
    assert result.sections[0].title == "Introduction"
    assert result.sections[0].page == 3


def testParseOut():
    content = r"""
\contentsline {section}{\numberline {1}Introduction}{1}{section.1}
\contentsline {section}{\numberline {2}Methods}{5}{section.2}
"""
    result = parse_out(content)
    assert "Introduction" in result
    assert result["Introduction"] == 1
    assert "Methods" in result
    assert result["Methods"] == 5


def testParseToc():
    content = r"""
\contentsline {section}{\numberline {1}Related Work}{1}{section.1}
"""
    result = parse_toc(content)
    assert "Related Work" in result
    assert result["Related Work"] == 1


def testDetectTotalPagesFromAux():
    content = r"\gdef \@abspage@last{12}"
    assert detect_total_pages(content) == 12


def testDetectTotalPagesFromNav():
    aux = ""
    nav = r"\headcommand {\beamer@documentpages {15}}"
    assert detect_total_pages(aux, nav) == 15


def testExtractPageLabelMap():
    aux_content = r"""
\newlabel{eq:energy}{{1}{2}}
\newlabel{eq:mass}{{2}{4}}
"""
    nav_content = r"""
\headcommand {\sectionentry {1}{Introduction}{1}{Introduction}{0}}
"""
    result = extract_page_label_map(aux_content, nav_content)
    assert result["eq:energy"] == 2
    assert result["eq:mass"] == 4
    assert result["Introduction"] == 1


def testDiffEngineIdentical():
    engine = DiffEngine()
    content = r"""
\gdef \@abspage@last{3}
\newlabel{sec:intro}{{1}{1}}
"""
    result = engine.diff_intermediates(content, content, content, content)
    assert len(result.dirty_pages) == 0


def testDiffEngineNewPages():
    engine = DiffEngine()
    old_aux = r"\gdef \@abspage@last{3}"
    new_aux = r"\gdef \@abspage@last{5}"
    result = engine.diff_intermediates(None, None, old_aux, new_aux)
    assert result.total_pages_old == 3
    assert result.total_pages_new == 5
    assert 4 in result.added_pages
    assert 5 in result.added_pages


def testDiffEngineLabelChange():
    engine = DiffEngine()
    old_aux = r"""
\gdef \@abspage@last{3}
\newlabel{sec:intro}{{1}{1}}
"""
    new_aux = r"""
\gdef \@abspage@last{3}
\newlabel{sec:intro}{{1}{1}}
\newlabel{fig:new}{{2.1}{2}}
"""
    result = engine.diff_intermediates(None, None, old_aux, new_aux)
    assert 2 in result.dirty_pages


def testDiffEngineSourceComparison():
    engine = DiffEngine()
    old = {"file1.tex": "content1", "file2.tex": "content2"}
    new = {"file1.tex": "content1", "file2.tex": "changed"}
    changed = engine.diff_sources(old, new)
    assert "file2.tex" in changed
    assert "file1.tex" not in changed


def testDiffEngineSourceAddedRemoved():
    engine = DiffEngine()
    old = {"file1.tex": "content1"}
    new = {"file1.tex": "content1", "file3.tex": "content3"}
    changed = engine.diff_sources(old, new)
    assert "file3.tex" in changed


def testDiffEngineLineDiff():
    engine = DiffEngine()
    old = "line1\nline2\nline3\n"
    new = "line1\nchanged\nline3\n"
    hunks = engine.compute_line_diff(old, new)
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
    result = engine.analyze_propagation(source, {2}, 3)
    assert isinstance(result, set)
    assert len(result) > 0


def testManifestCreateSave():
    with tempfile.TemporaryDirectory() as tmpDir:
        manifest = BuildManifest(tmpDir)
        manifest.set_page_count(5)
        manifest.save()
        assert os.path.isfile(manifest.manifestPath)
        manifest2 = BuildManifest(tmpDir)
        assert manifest2.get_page_count() == 5


def testManifestSourceHashing():
    with tempfile.TemporaryDirectory() as tmpDir:
        filePath = os.path.join(tmpDir, "test.tex")
        with open(filePath, "w") as f:
            f.write("test content")
        manifest = BuildManifest(tmpDir)
        manifest.update_source_hashes([filePath])
        assert not manifest.source_changed(filePath)
        with open(filePath, "w") as f:
            f.write("modified content")
        assert manifest.source_changed(filePath)


def testManifestSnapshot():
    with tempfile.TemporaryDirectory() as tmpDir:
        cacheDir = os.path.join(tmpDir, "__texcache__")
        os.makedirs(cacheDir)
        with open(os.path.join(cacheDir, "main.aux"), "w") as f:
            f.write("old aux content")
        with open(os.path.join(cacheDir, "main.nav"), "w") as f:
            f.write("old nav content")
        manifest = BuildManifest(tmpDir)
        manifest.snapshot_intermediates("main")
        with open(os.path.join(cacheDir, "main.aux"), "w") as f:
            f.write("new aux content")
        old_content = manifest.read_snapshot("main", ".aux")
        new_content = manifest.read_current("main", ".aux")
        assert old_content == "old aux content"
        assert new_content == "new aux content"


def testManifestClear():
    with tempfile.TemporaryDirectory() as tmpDir:
        cacheDir = os.path.join(tmpDir, "__texcache__")
        os.makedirs(cacheDir)
        with open(os.path.join(cacheDir, "test.txt"), "w") as f:
            f.write("test")
        manifest = BuildManifest(tmpDir)
        manifest.set_page_count(5)
        manifest.save()
        manifest.clear()
        assert not os.path.isdir(cacheDir)


def testBuildResultSlots():
    from services.texmake.builder import BuildResult
    result = BuildResult()
    assert result.pdf_paths == []
    assert result.page_diff is None
    assert result.sources_changed == []
    assert result.skipped is False


def testPageDiffNeedsFullRecompile():
    diff = PageDiff()
    diff.total_pages_new = 10
    diff.dirty_pages = {1, 2, 3}
    assert not diff.needs_full_recompile
    diff.dirty_pages = set(range(1, 9))
    assert diff.needs_full_recompile


def testPageDiffPageRange():
    diff = PageDiff()
    diff.dirty_pages = {3, 5, 7}
    assert diff.page_range == (3, 7)
    diff.dirty_pages = set()
    assert diff.page_range == (0, 0)


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
