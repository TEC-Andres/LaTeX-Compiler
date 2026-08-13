from __future__ import annotations
from .errors import TexMakeSyntaxError

_BLOCK_OPENERS = {"if", "foreach", "macro", "function", "while"}
_BLOCK_CLOSERS = {"endif", "endforeach", "endmacro", "endfunction", "endwhile"}
_CLOSER_MAP = {
    "endif": "if",
    "endforeach": "foreach",
    "endmacro": "macro",
    "endfunction": "function",
    "endwhile": "while",
}
_BLOCK_ALTERNATES = {"elseif", "else"}


class Node:
    """A parsed texmake statement: a plain command or a block (if/foreach/macro/while)."""

    __slots__ = ("kind", "args", "line", "children")

    def __init__(self, kind: str, args: list[str], line: int):
        self.kind = kind
        self.args = args
        self.line = line
        self.children: list[Node] = []


class _RawCommand:
    __slots__ = ("name", "args", "line")

    def __init__(self, name: str, args: list[str], line: int):
        self.name = name
        self.args = args
        self.line = line


def _stripComments(text: str) -> str:
    out: list[str] = []
    inQuote = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            inQuote = not inQuote
            out.append(ch)
            i += 1
        elif ch == "#" and not inQuote:
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text):
                out.append("\n")
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _splitArgs(raw: str, line: int, filePath: str | None) -> list[str]:
    args: list[str] = []
    current = ""
    inQuote = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '"':
            inQuote = not inQuote
            i += 1
        elif ch.isspace() and not inQuote:
            if current:
                args.append(current)
                current = ""
            i += 1
        else:
            current += ch
            i += 1
    if inQuote:
        raise TexMakeSyntaxError("unterminated string literal", line, filePath)
    if current:
        args.append(current)
    return args


def _lineOf(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _scanCommands(text: str, filePath: str | None) -> list[_RawCommand]:
    commands: list[_RawCommand] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if not (ch.isalpha() or ch == "_"):
            raise TexMakeSyntaxError(f"unexpected character '{ch}'", _lineOf(text, i), filePath)
        j = i
        while j < n and (text[j].isalnum() or text[j] == "_"):
            j += 1
        name = text[i:j]
        k = j
        while k < n and text[k].isspace():
            k += 1
        if k >= n or text[k] != "(":
            raise TexMakeSyntaxError(f"expected '(' after '{name}'", _lineOf(text, i), filePath)
        depth = 0
        inQuote = False
        p = k
        while p < n:
            c = text[p]
            if c == '"':
                inQuote = not inQuote
            elif c == "(" and not inQuote:
                depth += 1
            elif c == ")" and not inQuote:
                depth -= 1
                if depth == 0:
                    break
            p += 1
        if p >= n:
            raise TexMakeSyntaxError(f"unbalanced parentheses in '{name}'", _lineOf(text, i), filePath)
        args = _splitArgs(text[k + 1:p], _lineOf(text, i), filePath)
        commands.append(_RawCommand(name, args, _lineOf(text, i)))
        i = p + 1
    return commands


def parse(text: str, filePath: str | None = None) -> Node:
    if text.startswith("\ufeff"):
        text = text[1:]
    root = Node("root", [], 0)
    stack: list[Node] = [root]
    for raw in _scanCommands(_stripComments(text), filePath):
        if raw.name in _BLOCK_OPENERS:
            node = Node(raw.name, raw.args, raw.line)
            stack[-1].children.append(node)
            stack.append(node)
        elif raw.name in _BLOCK_ALTERNATES:
            if stack[-1].kind != "if":
                raise TexMakeSyntaxError(f"'{raw.name}' outside of an if block", raw.line, filePath)
            stack[-1].children.append(Node(raw.name, raw.args, raw.line))
        elif raw.name in _BLOCK_CLOSERS:
            expected = _CLOSER_MAP[raw.name]
            if stack[-1].kind != expected:
                raise TexMakeSyntaxError(f"'{raw.name}' does not match an open '{expected}' block", raw.line, filePath)
            stack.pop()
        else:
            stack[-1].children.append(Node("command", [raw.name] + raw.args, raw.line))
    if len(stack) > 1:
        raise TexMakeSyntaxError(f"unclosed '{stack[-1].kind}' block", stack[-1].line, filePath)
    return root