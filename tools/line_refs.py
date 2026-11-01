"""Keeps Markdown links of the form [`symbol`](path#Lstart-Lend) pointing at the symbol's lines.

Run `uv run python -m tools.line_refs` to rewrite stale links; the tests fail while one is stale.
A Python symbol is a top-level name or `Class.member`; for other files it is the first line that
contains the text, and the range runs to the end of that block (the next blank line).
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("CONTRIBUTING.md", "docs/*.md")
LINK = re.compile(
    r"\[`(?P<symbol>[^`]+)`\]\((?P<path>[^)#\s]+)#L(?P<start>\d+)(?:-L(?P<end>\d+))?\)"
)


@dataclass(frozen=True)
class Reference:
    document: Path
    symbol: str
    path: str
    start: int
    end: int

    @property
    def target(self) -> Path:
        return (self.document.parent / self.path).resolve()


def documents(root: Path = ROOT) -> list[Path]:
    return sorted(path for pattern in DOCUMENTS for path in root.glob(pattern))


def references(document: Path) -> Iterator[Reference]:
    for match in LINK.finditer(document.read_text(encoding="utf-8")):
        start = int(match["start"])
        end = int(match["end"] or start)
        yield Reference(document, match["symbol"], match["path"], start, end)


def symbol_lines(target: Path, symbol: str) -> tuple[int, int] | None:
    """First and last line of a symbol's definition, or None when it is not found."""
    text = target.read_text(encoding="utf-8")
    if target.suffix == ".py":
        return _python_lines(ast.parse(text), symbol.split("."))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if symbol in line:
            end = index
            while end + 1 < len(lines) and lines[end + 1].strip():
                end += 1
            return index + 1, end + 1
    return None


def _python_lines(tree: ast.Module | ast.ClassDef, parts: list[str]) -> tuple[int, int] | None:
    head, rest = parts[0], parts[1:]
    for node in tree.body:
        if _defines(node, head):
            if not rest:
                return node.lineno, node.end_lineno or node.lineno
            if isinstance(node, ast.ClassDef):
                return _python_lines(node, rest)
    return None


def _defines(node: ast.stmt, name: str) -> bool:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name == name
    if isinstance(node, ast.Assign):
        return any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == name
    return False


def link(symbol: str, path: str, lines: tuple[int, int]) -> str:
    start, end = lines
    anchor = f"L{start}" if start == end else f"L{start}-L{end}"
    return f"[`{symbol}`]({path}#{anchor})"


def refresh(root: Path = ROOT) -> list[str]:
    """Rewrite every stale link; returns the problems that cannot be fixed automatically."""
    problems: list[str] = []
    for document in documents(root):
        text = document.read_text(encoding="utf-8")

        def replace(match: re.Match[str], document: Path = document) -> str:
            target = (document.parent / match["path"]).resolve()
            if not target.is_file():
                problems.append(f"{document.name}: {match['path']} does not exist")
                return match[0]
            lines = symbol_lines(target, match["symbol"])
            if lines is None:
                problems.append(f"{document.name}: {match['symbol']} not in {match['path']}")
                return match[0]
            return link(match["symbol"], match["path"], lines)

        updated = LINK.sub(replace, text)
        if updated != text:
            document.write_text(updated, encoding="utf-8")
    return problems


if __name__ == "__main__":
    remaining = refresh()
    for problem in remaining:
        print(problem, file=sys.stderr)
    sys.exit(1 if remaining else 0)
