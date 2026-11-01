"""Converging one container to its spec: create, start, recreate on change, or leave it alone."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from enum import StrEnum

from outpost.domain.errors import Declined
from outpost.domain.fingerprint import fingerprint
from outpost.ports.engine import FINGERPRINT_LABEL, ContainerEngine, ContainerSpec, ContainerState


class Change(StrEnum):
    CREATED = "created"
    STARTED = "started"
    RECREATED = "recreated"
    UNCHANGED = "unchanged"


def converge(
    engine: ContainerEngine,
    spec: ContainerSpec,
    *,
    allow_recreate: Callable[[], bool] = lambda: True,
) -> Change:
    wanted = fingerprint(repr(spec))
    labelled = replace(spec, labels={**spec.labels, FINGERPRINT_LABEL: wanted})
    state = engine.state(spec.name)
    if state is ContainerState.MISSING:
        engine.run(labelled)
        return Change.CREATED
    if engine.label(spec.name, FINGERPRINT_LABEL) != wanted:
        if not allow_recreate():
            raise Declined(f"{spec.name} must be recreated to apply the new settings")
        engine.remove(spec.name)
        engine.run(labelled)
        return Change.RECREATED
    if state is ContainerState.STOPPED:
        engine.start(spec.name)
        return Change.STARTED
    return Change.UNCHANGED
