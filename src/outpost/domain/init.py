"""Init scripts: run at every start, and by `up` when their content changed."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Script:
    name: str
    path: PurePosixPath
    content_digest: str


def scripts_digest(scripts: Sequence[Script]) -> str:
    """One digest for the whole ordered set: a renamed, reordered or edited script changes it."""
    digest = hashlib.sha256()
    for script in scripts:
        digest.update(f"{script.path}\0{script.content_digest}\0".encode())
    return digest.hexdigest()
