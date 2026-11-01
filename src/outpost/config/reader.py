"""A typed view over parsed YAML that reports errors with their exact key path."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import TypeVar

from outpost.domain.errors import ConfigError, InvalidValue

E = TypeVar("E", bound=StrEnum)
T = TypeVar("T")


class Node:
    """One mapping of the file. Every accessor records the key, so unknown keys can be refused."""

    def __init__(self, data: object, path: str) -> None:
        if not isinstance(data, Mapping):
            raise ConfigError(path, "expected a mapping of keys to values")
        self._data: Mapping[object, object] = data
        self._path = path
        self._read: set[str] = set()

    @property
    def path(self) -> str:
        return self._path

    def at(self, key: str) -> str:
        return f"{self._path}.{key}" if self._path else key

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return [str(key) for key in self._data]

    def _raw(self, key: str) -> object:
        self._read.add(key)
        if key not in self._data or self._data[key] is None:
            raise ConfigError(self.at(key), "is required")
        return self._data[key]

    def child(self, key: str) -> Node:
        return Node(self._raw(key), self.at(key))

    def section(self, key: str) -> Node:
        """A child mapping that may be absent; absent reads as empty, so defaults apply."""
        self._read.add(key)
        if self._data.get(key) is None:
            return Node({}, self.at(key))
        return self.child(key)

    def text(self, key: str, default: str | None = None) -> str:
        if default is not None and self._data.get(key) is None:
            self._read.add(key)
            return default
        value = self._raw(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(self.at(key), "must be a non-empty string")
        return value

    def optional_text(self, key: str) -> str | None:
        self._read.add(key)
        return self.text(key) if self._data.get(key) is not None else None

    def integer(self, key: str, default: int | None = None, *, minimum: int = 0) -> int:
        if default is not None and self._data.get(key) is None:
            self._read.add(key)
            return default
        value = self._raw(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ConfigError(self.at(key), f"must be an integer of at least {minimum}")
        return value

    def optional_number(self, key: str) -> float | None:
        self._read.add(key)
        value = self._data.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            raise ConfigError(self.at(key), "must be a positive number")
        return float(value)

    def flag(self, key: str, default: bool) -> bool:
        self._read.add(key)
        value = self._data.get(key, default)
        if not isinstance(value, bool):
            raise ConfigError(self.at(key), "must be true or false")
        return value

    def choice(self, key: str, enum: type[E], default: E | None = None) -> E:
        if default is not None and self._data.get(key) is None:
            self._read.add(key)
            return default
        value = self.text(key)
        try:
            return enum(value)
        except ValueError:
            allowed = ", ".join(member.value for member in enum)
            raise ConfigError(self.at(key), f"must be one of: {allowed}") from None

    def texts(self, key: str, default: tuple[str, ...] | None = None) -> tuple[str, ...]:
        if default is not None and self._data.get(key) is None:
            self._read.add(key)
            return default
        value = self._raw(key)
        if not isinstance(value, list) or not value:
            raise ConfigError(self.at(key), "must be a non-empty list of strings")
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ConfigError(self.at(key), "must contain only non-empty strings")
        return tuple(str(item) for item in value)

    def text_map(self, key: str) -> dict[str, str]:
        self._read.add(key)
        value = self._data.get(key)
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ConfigError(self.at(key), "must be a mapping of names to strings")
        result: dict[str, str] = {}
        for name, item in value.items():
            if not isinstance(name, str) or not isinstance(item, str):
                raise ConfigError(self.at(key), "names and values must be strings (quote numbers)")
            result[name] = item
        return result

    def nodes(self, key: str) -> list[Node]:
        value = self._raw(key)
        if not isinstance(value, list):
            raise ConfigError(self.at(key), "must be a list")
        return [Node(item, f"{self.at(key)}[{index}]") for index, item in enumerate(value)]

    def node_map(self, key: str) -> dict[str, Node]:
        value = self._raw(key)
        if not isinstance(value, Mapping) or not value:
            raise ConfigError(self.at(key), "must be a non-empty mapping")
        return {str(name): Node(item, f"{self.at(key)}.{name}") for name, item in value.items()}

    def value(self, key: str, build: Callable[[str], T], default: str | None = None) -> T:
        """Build a domain value from a string, reporting its rule violations at this key."""
        return self.check(key, build, self.text(key, default))

    def check(self, key: str, build: Callable[[str], T], raw: str) -> T:
        """Apply a domain rule to a value read under `key`, reporting a violation at that key."""
        try:
            return build(raw)
        except InvalidValue as error:
            raise ConfigError(self.at(key), str(error)) from None

    def done(self) -> None:
        """Refuse keys nobody read: they are typos or unsupported settings."""
        unknown = sorted(set(self.keys()) - self._read)
        if unknown:
            raise ConfigError(self._path or "<root>", f"unknown keys: {', '.join(unknown)}")
