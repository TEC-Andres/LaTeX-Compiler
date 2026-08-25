from __future__ import annotations
import os
import shutil
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from services.texmake import Builder, TexMakeProject, TexMakeSyntaxError
from services.texmake.parser import parse


def _writeProject(files: dict[str, str]) -> str:
    tmpDir = tempfile.mkdtemp(prefix="texmakeTest_")
    for relPath, content in files.items():
        absPath = os.path.join(tmpDir, relPath)
        os.makedirs(os.path.dirname(absPath), exist_ok=True)
        with open(absPath, "w", encoding="utf-8") as f:
            f.write(content)
    return tmpDir


def _runProject(files: dict[str, str]) -> TexMakeProject:
    tmpDir = _writeProject(files)
    return TexMakeProject(tmpDir, os.path.join(tmpDir, "texmakelists.txt")).run()


def testParserCommentsAndQuotes() -> None:
    root = parse("# a comment\nset(NAME \"my project\")\nset(EMPTY) # trailing\n")
    commands = [node for node in root.children if node.kind == "command"]
    assert len(commands) == 2, commands
    assert commands[0].args == ["set", "NAME", "my project"], commands[0].args
    assert commands[1].args == ["set", "EMPTY"], commands[1].args


def testParserMultiline() -> None:
    root = parse("set(A 1\n  2\n  3)\n")
    commands = [node for node in root.children if node.kind == "command"]
    assert commands[0].args == ["set", "A", "1", "2", "3"], commands[0].args


def testParserUnbalancedFails() -> None:
    try:
        parse("set(A 1\n")
        assert False, "expected TexMakeSyntaxError"
    except TexMakeSyntaxError:
        pass


def testParserBlockMismatchFails() -> None:
    try:
        parse("foreach(x 1 2)\nendwhile\n")
        assert False, "expected TexMakeSyntaxError"
    except TexMakeSyntaxError:
        pass


def testVariableExpansion() -> None:
    project = _runProject({
        "texmakelists.txt": 'set(OUT "${TEXMAKE_SOURCE_DIR}/__release__")\nset(COMBINED "a;${OUT}")\n',
    })
    assert project.variables["OUT"].endswith("__release__"), project.variables["OUT"]
    assert project.variables["COMBINED"] == f"a;{project.variables['OUT']}", project.variables["COMBINED"]


def testIfElse() -> None:
    project = _runProject({
        "texmakelists.txt": (
            "set(MODE release)\n"
            "if(MODE STREQUAL \"release\")\n"
            "  set(RESULT \"r\")\n"
            "elseif(MODE STREQUAL \"debug\")\n"
            "  set(RESULT \"d\")\n"
            "else()\n"
            "  set(RESULT \"o\")\n"
            "endif()\n"
            "if(NOT DEFINED RESULT)\n"
            "  set(RESULT \"x\")\n"
            "endif()\n"
        ),
    })
    assert project.variables["RESULT"] == "r", project.variables["RESULT"]


def testForeach() -> None:
    project = _runProject({
        "texmakelists.txt": (
            "set(FILES one;two;three)\n"
            "foreach(f ${FILES})\n"
            "  set(COLLECTED \"${COLLECTED};${f}\")\n"
            "endforeach()\n"
        ),
    })
    collected = project.variables["COLLECTED"].split(";")
    assert collected == ["", "one", "two", "three"], collected


def testMacro() -> None:
    project = _runProject({
        "texmakelists.txt": (
            "macro(makeDir name)\n"
            "  set(OUT_${name} \"dir/${name}\")\n"
            "endmacro()\n"
            "makeDir(a)\n"
            "makeDir(b)\n"
        ),
    })
    assert project.variables["OUT_a"] == "dir/a", project.variables
    assert project.variables["OUT_b"] == "dir/b", project.variables


def testGlob() -> None:
    project = _runProject({
        "texmakelists.txt": (
            "file(GLOB TEX_FILES tex/*.tex)\n"
            "file(GLOB_RECURSE ALL_TEX tex/*.tex)\n"
        ),
        "tex/a.tex": "% a",
        "tex/b.tex": "% b",
        "tex/nested/c.tex": "% c",
    })
    globFiles = project.variables["TEX_FILES"].split(";")
    assert len(globFiles) == 2, globFiles
    allFiles = project.variables["ALL_TEX"].split(";")
    assert len(allFiles) == 3, allFiles


def testTargetGraph() -> None:
    project = _runProject({
        "texmakelists.txt": (
            "set(RELEASE_OUTPUT_DIR \"${TEXMAKE_SOURCE_DIR}/__release__\")\n"
            "file(GLOB LIB_SOURCES lib/*.tex)\n"
            "add_library(MyLib ${LIB_SOURCES})\n"
            "add_executable(App src/main.tex)\n"
            "target_link_libraries(App PRIVATE MyLib)\n"
            "set_target_properties(App PROPERTIES\n"
            "    RUNTIME_OUTPUT_DIRECTORY \"${RELEASE_OUTPUT_DIR}\"\n"
            "    RUNTIME_OUTPUT_DIRECTORY_RELEASE \"${RELEASE_OUTPUT_DIR}\"\n"
            ")\n"
        ),
        "lib/a.tex": "% a",
        "lib/b.tex": "% b",
        "src/main.tex": "% main",
    })
    app = project.targets["App"]
    assert app.kind == "executable", app.kind
    assert app.mainFile == "src/main.tex", app.mainFile
    assert app.libraries == ["MyLib"], app.libraries
    assert app.outputDir.endswith("__release__"), app.outputDir
    sources = app.allSources(project)
    assert len(sources) == 3, sources


def testMinimumRequiredEngine() -> None:
    project = _runProject({
        "texmakelists.txt": "texmake_minimum_required(XeLaTeX VERSION 3.14159)\n",
    })
    assert project.engine == "xelatex", project.engine
    assert project.minVersion == (3, 14159), project.minVersion


def testMinimumRequiredUnsupportedEngineFails() -> None:
    try:
        _runProject({"texmakelists.txt": "texmake_minimum_required(volatile VERSION 1.0)\n"})
        assert False, "expected TexMakeSyntaxError"
    except TexMakeSyntaxError:
        pass


def testUnknownCommandFails() -> None:
    try:
        _runProject({"texmakelists.txt": "make_believe(1)\n"})
        assert False, "expected TexMakeSyntaxError"
    except TexMakeSyntaxError:
        pass


def testIncrementalCommand() -> None:
    project = _runProject({"texmakelists.txt": "incremental()\n"})
    assert project.incremental is True


def testCleanCommand() -> None:
    project = _runProject({"texmakelists.txt": "clean()\n"})
    assert project.clean is True


def testIncrementalAndCleanTogether() -> None:
    project = _runProject({"texmakelists.txt": "incremental()\nclean()\n"})
    assert project.incremental is True
    assert project.clean is True


def testDefaultsAreFalse() -> None:
    project = _runProject({"texmakelists.txt": "set(X 1)\n"})
    assert project.incremental is False
    assert project.clean is False


def testBuilderEndToEnd() -> None:
    if not shutil.which("pdflatex"):
        print("  (skipped: pdflatex not available)")
        return
    tmpDir = _writeProject({
        "texmakelists.txt": (
            "texmake_minimum_required(pdflatex VERSION 3.14159)\n"
            "project(E2E)\n"
            "add_executable(Main main.tex)\n"
            "set_target_properties(Main PROPERTIES RUNTIME_OUTPUT_DIRECTORY \"${TEXMAKE_SOURCE_DIR}/out\")\n"
        ),
        "main.tex": "\\documentclass{article}\n\\begin{document}\nHello \\TeX.\n\\end{document}\n",
    })
    project = TexMakeProject(tmpDir, os.path.join(tmpDir, "texmakelists.txt")).run()
    pdfPaths = Builder(project).build()
    assert len(pdfPaths) == 1, pdfPaths
    assert os.path.isfile(pdfPaths[0]), pdfPaths[0]
    assert not os.path.isfile(os.path.join(tmpDir, "main.pdf")), "engine pdf must not land next to texmakelists.txt"
    assert os.path.isfile(os.path.join(tmpDir, "__texcache__", "main.aux")), "aux must land in __texcache__"
    assert os.path.isfile(os.path.join(tmpDir, "__texcache__", "main.log")), "log must land in __texcache__"


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