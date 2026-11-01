"""Every [`symbol`](file#Lx-Ly) link in CONTRIBUTING.md and docs/ points at the symbol's lines."""

from __future__ import annotations

import pytest

from tools.line_refs import Reference, documents, link, references, symbol_lines

ALL = [reference for document in documents() for reference in references(document)]


def test_the_documents_do_reference_code() -> None:
    assert len(ALL) >= 20


@pytest.mark.parametrize("reference", ALL, ids=lambda ref: f"{ref.document.name}:{ref.symbol}")
def test_reference_is_current(reference: Reference) -> None:
    assert reference.target.is_file(), f"{reference.path} does not exist"
    lines = symbol_lines(reference.target, reference.symbol)
    assert lines is not None, f"{reference.symbol} is not in {reference.path}"
    assert (reference.start, reference.end) == lines, (
        f"stale link, run `uv run python -m tools.line_refs`; "
        f"expected {link(reference.symbol, reference.path, lines)}"
    )
