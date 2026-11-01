"""A secret value that never shows up in logs, reprs or error messages."""

from __future__ import annotations

from outpost.domain.errors import InvalidValue


class Secret:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not value.strip():
            raise InvalidValue("a secret cannot be empty")
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)
