"""Short content fingerprints, used to rebuild or recreate only what changed."""

from __future__ import annotations

import hashlib

LENGTH = 12


def fingerprint(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode())
        digest.update(b"\0")
    return digest.hexdigest()[:LENGTH]
