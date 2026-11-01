from __future__ import annotations

from pathlib import Path

import pytest

from outpost.config import load_config
from outpost.domain.config import OutpostConfig, ResolvedConfig

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "outpost.example.yaml"


@pytest.fixture(scope="session")
def example() -> OutpostConfig:
    return load_config(EXAMPLE)


@pytest.fixture
def azure(example: OutpostConfig) -> ResolvedConfig:
    return example.resolve("azure")


@pytest.fixture
def wsl(example: OutpostConfig) -> ResolvedConfig:
    return example.resolve("wsl")
