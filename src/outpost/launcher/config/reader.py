"""A typed view over parsed YAML that reports errors with their exact key path."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from outpost.domain.errors import ConfigError, InvalidValue


class Node:
    """One mapping of the file. Every accessor records its key, so unknown keys can be refused."""

    def __init__(self, data: object, path: str) -> None:
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise ConfigError(path, "expected a mapping of keys to values")
        self._data: Mapping[object, object] = data
        self._path = path
        self._read: set[str] = set()

    def at(self, key: str) -> str:
        return f"{self._path}.{key}" if self._path else key

    def raw(self, key: str) -> object:
        """The value as parsed, or None; for sections a domain value parses itself."""
        self._read.add(key)
        return self._data.get(key)

    def text(self, key: str, default: str) -> str:
        value = self.raw(key)
        if value is None:
            return default
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(self.at(key), "must be a non-empty string")
        return value

    def integer(self, key: str, default: int) -> int:
        value = self.raw(key)
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(self.at(key), "must be an integer")
        return value

    def texts(self, key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
        value = self.raw(key)
        if value is None:
            return default
        if not isinstance(value, list):
            raise ConfigError(self.at(key), "must be a list of strings")
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise ConfigError(f"{self.at(key)}[{index}]", "must be a non-empty string")
        return tuple(value)

    def text_map(self, key: str) -> dict[str, str]:
        value = self.raw(key)
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ConfigError(self.at(key), "must be a mapping of strings to strings")
        result: dict[str, str] = {}
        for name, item in value.items():
            if not isinstance(name, str) or not isinstance(item, str):
                raise ConfigError(f"{self.at(key)}.{name}", "must map a string to a string")
            result[name] = item
        return result

    def check[R, T](self, key: str, build: Callable[[R], T], raw: R) -> T:
        """Apply a domain rule to a value read under `key`, reporting a violation at that key."""
        try:
            return build(raw)
        except InvalidValue as error:
            raise ConfigError(self.at(key), str(error)) from None

    def value[T](self, key: str, build: Callable[[str], T], default: str) -> T:
        return self.check(key, build, self.text(key, default))

    def done(self) -> None:
        """Refuse keys nobody read: they are typos or unsupported settings."""
        unknown = sorted(str(key) for key in self._data if str(key) not in self._read)
        if unknown:
            raise ConfigError(self._path or "outpost.yaml", f"unknown keys: {', '.join(unknown)}")
