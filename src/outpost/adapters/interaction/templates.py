"""Templates shipped in `outpost/resources`, with `{{name}}` placeholders."""

from __future__ import annotations

import re
from collections.abc import Mapping
from importlib import resources

from outpost.domain.errors import InvalidValue

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


class PackageTemplates:
    def __init__(self, package: str = "outpost.resources") -> None:
        self._package = package

    def render(self, name: str, values: Mapping[str, str]) -> str:
        template = resources.files(self._package).joinpath(name).read_text(encoding="utf-8")
        return render_text(template, values, name)


def render_text(template: str, values: Mapping[str, str], name: str = "template") -> str:
    """Replace every placeholder; a missing value or an unused one is an error."""
    used = set(_PLACEHOLDER.findall(template))
    missing = sorted(used - set(values))
    unused = sorted(set(values) - used)
    if missing or unused:
        raise InvalidValue(f"{name}: missing values {missing}, unused values {unused}")
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)
