from __future__ import annotations
import glob as globModule
import os
import re

from .errors import TexMakeSyntaxError
from .parser import Node, parse

_ENGINES = {"pdflatex", "xelatex", "lualatex"}
_TRUE_VALUES = {"1", "true", "on", "yes", "y", "nonzero"}
_FALSE_VALUES = {"", "0", "false", "off", "no", "n", "ignore", "notfound", "none"}
_VAR_RE = re.compile(r"\$\{([^}]+)\}")
_MAX_WHILE_ITERATIONS = 10000
_MAX_EXPANSION_DEPTH = 10


class Target:
    """A library or executable target registered by add_library/add_executable."""

    def __init__(self, name: str, kind: str, line: int):
        self.name = name
        self.kind = kind
        self.line = line
        self.mainFile: str | None = None
        self.sources: list[str] = []
        self.libraries: list[str] = []
        self.outputDir: str | None = None

    def allSources(self, project: "TexMakeProject") -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        def _add(path: str) -> None:
            if path and path not in seen:
                seen.add(path)
                result.append(path)

        if self.kind == "executable" and self.mainFile:
            _add(self.mainFile if os.path.isabs(self.mainFile) else os.path.join(project.sourceDir, self.mainFile))
        for source in self.sources:
            _add(source)
        for libName in self.libraries:
            lib = project.targets.get(libName)
            if lib:
                for source in lib.allSources(project):
                    _add(source)
        return result


class TexMakeProject:
    """Interprets a texmakelists.txt file and holds the resolved build graph."""

    def __init__(self, sourceDir: str, filePath: str):
        self.sourceDir = sourceDir
        self.filePath = filePath
        self.variables: dict[str, str] = {"TEXMAKE_SOURCE_DIR": sourceDir}
        self.macros: dict[str, tuple[list[str], Node]] = {}
        self.targets: dict[str, Target] = {}
        self.engine = "pdflatex"
        self.minVersion: tuple[int, ...] | None = None
        self.projectName: str | None = None
        self.incremental: bool = False
        self.clean: bool = False
        self._definitions: set[str] = set()

    def run(self, definitions: dict[str, str] | None = None) -> "TexMakeProject":
        self._definitions: set[str] = set()
        if definitions:
            self.variables.update(definitions)
            self._definitions = set(definitions.keys())
        with open(self.filePath, "r", encoding="utf-8") as f:
            root = parse(f.read(), self.filePath)
        self._executeNode(root)
        return self

    def expand(self, text: str, locals: dict[str, str] | None = None, depth: int = 0) -> str:
        if depth > _MAX_EXPANSION_DEPTH:
            raise TexMakeSyntaxError("variable expansion nested too deeply", filePath=self.filePath)

        def _replace(match: re.Match) -> str:
            name = match.group(1)
            if locals and name in locals:
                value = locals[name]
            else:
                value = self.variables.get(name, "")
            return self.expand(value, locals, depth + 1) if value else ""

        return _VAR_RE.sub(_replace, text)

    def _executeNode(self, node: Node, locals: dict[str, str] | None = None) -> None:
        if node.kind == "root":
            for child in node.children:
                self._executeNode(child, locals)
        elif node.kind == "command":
            self._executeCommand(node, locals)
        elif node.kind == "if":
            self._executeIf(node, locals)
        elif node.kind == "foreach":
            self._executeForeach(node, locals)
        elif node.kind == "while":
            self._executeWhile(node, locals)
        elif node.kind in ("macro", "function"):
            params = [self.expand(param) for param in node.args[1:]]
            self.macros[node.args[0]] = (params, node)
        else:
            raise TexMakeSyntaxError(f"unexpected '{node.kind}'", node.line, self.filePath)

    def _executeCommand(self, node: Node, locals: dict[str, str] | None) -> None:
        name = node.args[0]
        if name in self.macros:
            self._executeMacroCall(name, node.args[1:], locals, node)
            return
        args = node.args[1:]
        if name == "texmake_minimum_required":
            self._cmdMinimumRequired(node, args, locals)
        elif name == "project":
            self._cmdProject(node, args, locals)
        elif name == "set":
            self._cmdSet(node, args, locals)
        elif name == "unset":
            self._cmdUnset(node, args)
        elif name == "file":
            self._cmdFile(node, args, locals)
        elif name == "add_library":
            self._cmdAddLibrary(node, args, locals)
        elif name == "target_link_libraries":
            self._cmdTargetLinkLibraries(node, args, locals)
        elif name == "add_executable":
            self._cmdAddExecutable(node, args, locals)
        elif name == "set_target_properties":
            self._cmdSetTargetProperties(node, args, locals)
        elif name == "incremental":
            self._cmdIncremental(node)
        elif name == "clean":
            self._cmdClean(node)
        else:
            raise TexMakeSyntaxError(f"unknown command '{name}'", node.line, self.filePath)

    def _cmdMinimumRequired(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if not args:
            raise TexMakeSyntaxError("texmake_minimum_required() expects an engine and/or VERSION", node.line, self.filePath)
        expanded = [self.expand(arg, locals) for arg in args]
        engineArg: str | None = None
        versionArg: str | None = None
        i = 0
        while i < len(expanded):
            if expanded[i].upper() == "VERSION":
                if i + 1 >= len(expanded):
                    raise TexMakeSyntaxError("texmake_minimum_required(): missing version after VERSION", node.line, self.filePath)
                versionArg = expanded[i + 1]
                i += 2
            else:
                engineArg = expanded[i]
                i += 1
        if engineArg:
            engine = engineArg.lower()
            if engine not in _ENGINES:
                raise TexMakeSyntaxError(f"unsupported engine '{engineArg}' (expected one of {sorted(_ENGINES)})", node.line, self.filePath)
            self.engine = engine
            self.variables["TEXMAKE_ENGINE"] = engine
        if versionArg:
            parts = versionArg.split(".")
            try:
                self.minVersion = tuple(int(part) for part in parts)
            except ValueError:
                raise TexMakeSyntaxError(f"invalid version '{versionArg}'", node.line, self.filePath)

    def _cmdProject(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if not args:
            raise TexMakeSyntaxError("project() expects a name", node.line, self.filePath)
        name = self.expand(args[0], locals)
        if not name:
            raise TexMakeSyntaxError("project() expects a non-empty name", node.line, self.filePath)
        self.projectName = name
        self.variables["TEXMAKE_PROJECT_NAME"] = name

    def _cmdSet(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if not args:
            raise TexMakeSyntaxError("set() expects a variable name", node.line, self.filePath)
        varName = self.expand(args[0], locals)
        value = ";".join(self.expand(arg, locals) for arg in args[1:])
        if varName not in self._definitions:
            self.variables[varName] = value

    def _cmdUnset(self, node: Node, args: list[str]) -> None:
        if not args:
            raise TexMakeSyntaxError("unset() expects a variable name", node.line, self.filePath)
        self.variables.pop(args[0], None)

    def _cmdFile(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if len(args) < 3:
            raise TexMakeSyntaxError("file() expects GLOB|GLOB_RECURSE, a variable name and patterns", node.line, self.filePath)
        mode = args[0].upper()
        if mode not in ("GLOB", "GLOB_RECURSE"):
            raise TexMakeSyntaxError(f"unsupported file() mode '{args[0]}'", node.line, self.filePath)
        varName = args[1]
        results: list[str] = []
        for arg in args[2:]:
            for pattern in self.expand(arg, locals).split(";"):
                if not pattern:
                    continue
                absPattern = pattern if os.path.isabs(pattern) else os.path.join(self.sourceDir, pattern)
                if mode == "GLOB":
                    results.extend(globModule.glob(absPattern))
                else:
                    results.extend(self._globRecurse(absPattern))
        self.variables[varName] = ";".join(sorted(set(results)))

    @staticmethod
    def _globRecurse(pattern: str) -> list[str]:
        if "**" not in pattern:
            marker = pattern.find("*")
            if marker != -1:
                slash = pattern.rfind("/", 0, marker)
                if slash == -1:
                    pattern = f"**/{pattern}"
                else:
                    pattern = f"{pattern[:slash + 1]}**/{pattern[slash + 1:]}"
        return globModule.glob(pattern, recursive=True)

    def _resolveSourceList(self, args: list[str], locals: dict[str, str] | None) -> list[str]:
        sources: list[str] = []
        for arg in args:
            for item in self.expand(arg, locals).split(";"):
                if not item:
                    continue
                sources.append(item if os.path.isabs(item) else os.path.join(self.sourceDir, item))
        return sources

    def _cmdAddLibrary(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if not args:
            raise TexMakeSyntaxError("add_library() expects a name", node.line, self.filePath)
        name = args[0]
        if name in self.targets:
            raise TexMakeSyntaxError(f"target '{name}' already defined", node.line, self.filePath)
        target = Target(name, "library", node.line)
        target.sources = self._resolveSourceList(args[1:], locals)
        self.targets[name] = target

    def _cmdTargetLinkLibraries(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if len(args) < 2:
            raise TexMakeSyntaxError("target_link_libraries() expects a target and libraries", node.line, self.filePath)
        name = args[0]
        if name not in self.targets:
            raise TexMakeSyntaxError(f"unknown target '{name}'", node.line, self.filePath)
        target = self.targets[name]
        for arg in args[1:]:
            if arg in ("PUBLIC", "PRIVATE", "INTERFACE"):
                continue
            for libName in self.expand(arg, locals).split(";"):
                if not libName:
                    continue
                if libName not in self.targets:
                    raise TexMakeSyntaxError(f"unknown library '{libName}'", node.line, self.filePath)
                target.libraries.append(libName)

    def _cmdAddExecutable(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if len(args) < 2:
            raise TexMakeSyntaxError("add_executable() expects a name and a main tex file", node.line, self.filePath)
        name = args[0]
        if name in self.targets:
            raise TexMakeSyntaxError(f"target '{name}' already defined", node.line, self.filePath)
        target = Target(name, "executable", node.line)
        target.mainFile = self.expand(args[1], locals)
        target.sources = self._resolveSourceList(args[2:], locals)
        self.targets[name] = target

    def _cmdSetTargetProperties(self, node: Node, args: list[str], locals: dict[str, str] | None) -> None:
        if len(args) < 3 or args[1].upper() != "PROPERTIES":
            raise TexMakeSyntaxError("set_target_properties() expects a target, PROPERTIES and key/value pairs", node.line, self.filePath)
        name = args[0]
        if name not in self.targets:
            raise TexMakeSyntaxError(f"unknown target '{name}'", node.line, self.filePath)
        target = self.targets[name]
        props = args[2:]
        if len(props) % 2 != 0:
            raise TexMakeSyntaxError("set_target_properties() expects key/value pairs", node.line, self.filePath)
        for i in range(0, len(props), 2):
            key = props[i].upper()
            value = self.expand(props[i + 1], locals)
            if key == "RUNTIME_OUTPUT_DIRECTORY" or key.startswith("RUNTIME_OUTPUT_DIRECTORY_") or key == "OUTPUT_DIRECTORY":
                target.outputDir = value

    def _cmdIncremental(self, node: Node) -> None:
        self.incremental = True

    def _cmdClean(self, node: Node) -> None:
        self.clean = True

    def _executeIf(self, node: Node, locals: dict[str, str] | None) -> None:
        branches: list[tuple[list[str] | None, list[Node]]] = []
        currentCond: list[str] | None = node.args
        currentChildren: list[Node] = []
        for child in node.children:
            if child.kind in ("elseif", "else"):
                branches.append((currentCond, currentChildren))
                currentCond = None if child.kind == "else" else child.args
                currentChildren = []
            else:
                currentChildren.append(child)
        branches.append((currentCond, currentChildren))
        for cond, children in branches:
            if cond is None or self._evalCondition(cond, locals):
                for child in children:
                    self._executeNode(child, locals)
                break

    def _executeForeach(self, node: Node, locals: dict[str, str] | None) -> None:
        if not node.args:
            raise TexMakeSyntaxError("foreach() expects a loop variable", node.line, self.filePath)
        varName = node.args[0]
        items: list[str] = []
        for arg in node.args[1:]:
            items.extend(item for item in self.expand(arg, locals).split(";") if item)
        previous = self.variables.get(varName)
        for item in items:
            self.variables[varName] = item
            for child in node.children:
                self._executeNode(child, locals)
        if previous is None:
            self.variables.pop(varName, None)
        else:
            self.variables[varName] = previous

    def _executeWhile(self, node: Node, locals: dict[str, str] | None) -> None:
        iterations = 0
        while self._evalCondition(node.args, locals):
            iterations += 1
            if iterations > _MAX_WHILE_ITERATIONS:
                raise TexMakeSyntaxError(f"while loop exceeded {_MAX_WHILE_ITERATIONS} iterations", node.line, self.filePath)
            for child in node.children:
                self._executeNode(child, locals)

    def _executeMacroCall(self, name: str, callArgs: list[str], locals: dict[str, str] | None, node: Node) -> None:
        params, body = self.macros[name]
        if len(callArgs) < len(params):
            raise TexMakeSyntaxError(f"macro '{name}' expects {len(params)} arguments, got {len(callArgs)}", node.line, self.filePath)
        saved: dict[str, str | None] = {}
        for param, value in zip(params, callArgs):
            saved[param] = self.variables.get(param)
            self.variables[param] = self.expand(value, locals)
        for child in body.children:
            self._executeNode(child, None)
        for param, old in saved.items():
            if old is None:
                self.variables.pop(param, None)
            else:
                self.variables[param] = old

    def _evalCondition(self, args: list[str], locals: dict[str, str] | None) -> bool:
        pos = [0]
        result = self._evalOr(args, pos, locals)
        if pos[0] != len(args):
            raise TexMakeSyntaxError(f"unexpected token '{args[pos[0]]}' in condition")
        return result

    def _evalOr(self, args: list[str], pos: list[int], locals: dict[str, str] | None) -> bool:
        left = self._evalAnd(args, pos, locals)
        while pos[0] < len(args) and args[pos[0]].upper() == "OR":
            pos[0] += 1
            right = self._evalAnd(args, pos, locals)
            left = left or right
        return left

    def _evalAnd(self, args: list[str], pos: list[int], locals: dict[str, str] | None) -> bool:
        left = self._evalFactor(args, pos, locals)
        while pos[0] < len(args) and args[pos[0]].upper() == "AND":
            pos[0] += 1
            right = self._evalFactor(args, pos, locals)
            left = left and right
        return left

    def _evalFactor(self, args: list[str], pos: list[int], locals: dict[str, str] | None) -> bool:
        if pos[0] >= len(args):
            raise TexMakeSyntaxError("unexpected end of condition")
        token = args[pos[0]]
        if token == "(":
            pos[0] += 1
            value = self._evalOr(args, pos, locals)
            if pos[0] >= len(args) or args[pos[0]] != ")":
                raise TexMakeSyntaxError("missing ')' in condition")
            pos[0] += 1
            return value
        if token.upper() == "NOT":
            pos[0] += 1
            return not self._evalFactor(args, pos, locals)
        return self._evalPrimary(args, pos, locals)

    def _resolveValue(self, token: str, locals: dict[str, str] | None) -> str:
        if token in self.variables:
            return self.variables[token]
        if locals and token in locals:
            return locals[token]
        return self.expand(token, locals)

    def _evalPrimary(self, args: list[str], pos: list[int], locals: dict[str, str] | None) -> bool:
        token = args[pos[0]]
        if pos[0] + 2 < len(args) and args[pos[0] + 1].upper() == "STREQUAL":
            left = self._resolveValue(token, locals)
            right = self._resolveValue(args[pos[0] + 2], locals)
            pos[0] += 3
            return left == right
        if token.upper() == "DEFINED" and pos[0] + 1 < len(args):
            name = args[pos[0] + 1]
            pos[0] += 2
            return (locals and name in locals) or name in self.variables
        if token.upper() == "EXISTS" and pos[0] + 1 < len(args):
            path = self.expand(args[pos[0] + 1], locals)
            if not os.path.isabs(path):
                path = os.path.join(self.sourceDir, path)
            pos[0] += 2
            return os.path.exists(path)
        pos[0] += 1
        return self._evalBooleanToken(token, locals)

    def _evalBooleanToken(self, token: str, locals: dict[str, str] | None) -> bool:
        if token in self.variables:
            return self._toBoolean(self.variables[token])
        if locals and token in locals:
            return self._toBoolean(locals[token])
        expanded = self.expand(token, locals)
        if expanded != token:
            return self._toBoolean(expanded)
        return self._toBoolean(token)

    @staticmethod
    def _toBoolean(value: str) -> bool:
        lowered = value.strip().lower()
        if lowered in _FALSE_VALUES:
            return False
        if lowered in _TRUE_VALUES:
            return True
        return bool(value)