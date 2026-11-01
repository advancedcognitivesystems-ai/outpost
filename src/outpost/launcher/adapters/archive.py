"""Tar streams for `outpost cp`: written and read as they flow, never staged on a disk."""

from __future__ import annotations

import tarfile
from pathlib import Path, PurePosixPath
from typing import IO


def write_archive(source: Path, name: str, out: IO[bytes]) -> None:
    """Archive a file or a folder under the single top-level `name`."""
    with tarfile.open(fileobj=out, mode="w|") as archive:
        archive.add(source, arcname=name)


def extract_archive(stream: IO[bytes], directory: Path, name: str) -> None:
    """Extract an archive whose top-level entry becomes `directory/name`; unsafe entries fail."""
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if not parts:
                continue
            member.name = str(PurePosixPath(name, *parts[1:]))
            archive.extract(member, directory, filter="data")
