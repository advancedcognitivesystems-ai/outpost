"""What the container reports about itself; written by the tool inside, read by the launcher."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from outpost.domain.errors import InvalidValue

INIT_SCRIPTS_FAILED = 3
"""Exit code of `outpost init` when a script failed: reported, not an error of the tool."""


@dataclass(frozen=True)
class BootRecord:
    """Kept in the state volume: whether boot finished, and the init scripts it last ran.

    `boot_id` names the start it was written for: a record from an earlier start never
    reads as ready.
    """

    ready: bool
    boot_id: str = ""
    init_digest: str = ""
    init_failed: tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> BootRecord:
        data = _object(text)
        return cls(
            ready=bool(data.get("ready", False)),
            boot_id=str(data.get("boot_id", "")),
            init_digest=str(data.get("init_digest", "")),
            init_failed=tuple(str(name) for name in _list(data.get("init_failed"))),
        )


@dataclass(frozen=True)
class ContainerStatus:
    ready: bool
    proxy_running: bool
    routes: int
    init_failed: tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self)) + "\n"

    @classmethod
    def from_json(cls, text: str) -> ContainerStatus:
        data = _object(text)
        routes = data.get("routes", 0)
        return cls(
            ready=bool(data.get("ready", False)),
            proxy_running=bool(data.get("proxy_running", False)),
            routes=routes if isinstance(routes, int) else 0,
            init_failed=tuple(str(name) for name in _list(data.get("init_failed"))),
        )


def _object(text: str) -> dict[str, object]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise InvalidValue("the container's status is not JSON") from None
    if not isinstance(data, dict):
        raise InvalidValue("the container's status is not a JSON object")
    return data


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
