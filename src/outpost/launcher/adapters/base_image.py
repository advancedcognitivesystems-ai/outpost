"""The default image's sources in the Outpost checkout, and the digest that tags the image."""

from __future__ import annotations

import hashlib
from functools import cached_property
from pathlib import Path

from outpost.domain.devcontainer import base_image
from outpost.domain.names import ImageRef

SOURCES = ("image", "src", "pyproject.toml", "README.md")
"""What the Dockerfile copies; `.dockerignore` keeps the build context to the same list."""
SKIPPED = ("__pycache__",)


class CheckoutBaseImage:
    def __init__(self, home: Path) -> None:
        self._home = home

    @property
    def context(self) -> Path:
        return self._home

    @property
    def dockerfile(self) -> Path:
        return self._home / "image" / "Dockerfile"

    def reference(self) -> ImageRef:
        return base_image(self._digest)

    @cached_property
    def _digest(self) -> str:
        digest = hashlib.sha256()
        for path in self._files():
            digest.update(path.relative_to(self._home).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
        return digest.hexdigest()

    def _files(self) -> list[Path]:
        found: list[Path] = []
        for name in SOURCES:
            root = self._home / name
            candidates = [root] if root.is_file() else sorted(root.rglob("*"))
            found.extend(
                path
                for path in candidates
                if path.is_file()
                and not any(part in SKIPPED for part in path.parts)
                and path.suffix != ".pyc"
            )
        return found
