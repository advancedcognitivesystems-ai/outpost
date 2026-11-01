"""The devcontainer.json Outpost runs: your settings over its defaults, plus what Outpost owns.

Everything about the file lives here: the defaults, how your settings merge into them, what
Outpost refuses (host mounts, published ports, the keys it sets itself), and the digest that
tells `up` whether the container must be recreated.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import PurePath

from outpost.domain.errors import ConfigError, InvalidValue
from outpost.domain.layout import (
    ENV_DOMAIN,
    ENV_NAME,
    ENV_PORT,
    PROXY_LISTEN_PORT,
    SETTINGS_LABEL,
    USER,
    WORKSPACES,
)
from outpost.domain.names import EnvironmentName, ImageRef
from outpost.domain.routes import Site
from outpost.domain.volumes import Volume

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None

BASE_REPOSITORY = "outpost/base"
BASE_IMAGE_ARG = "OUTPOST_BASE"
CLAUDE_CODE_FEATURE = "ghcr.io/anthropics/devcontainer-features/claude-code:1.0"
RESERVED_ENV_PREFIX = "OUTPOST_"
MERGED_KEYS = ("features", "containerEnv")
DIGEST_LENGTH = 12

_HOST_MOUNTS = "mounts from the host are not allowed; use `persist` or `outpost cp`"
_COMPOSE = "compose-based dev containers are not supported"
_PUBLISH = "the proxy's port is the only published port; register a route instead"
OWNED_KEYS: dict[str, str] = {
    "name": "Outpost names the container outpost-<name>",
    "workspaceMount": "the workspace is the volume on /workspaces",
    "workspaceFolder": "the workspace is the volume on /workspaces",
    "mounts": "add volumes with `persist`; " + _HOST_MOUNTS,
    "privileged": "the inner Docker needs it, so Outpost sets it",
    "overrideCommand": "the image's entrypoint must run at every start",
    "remoteUser": f"Outpost containers run shells as {USER}",
    "containerUser": "the entrypoint runs as root, shells as dev",
    "updateRemoteUserUID": "there is no bind mount to match",
    "appPort": _PUBLISH,
    "dockerComposeFile": _COMPOSE,
    "service": _COMPOSE,
    "runServices": _COMPOSE,
}
REFUSED_RUN_ARGS: dict[str, str] = {
    "-v": _HOST_MOUNTS,
    "--volume": _HOST_MOUNTS,
    "--mount": "Outpost sets the mounts; use `persist`",
    "-p": _PUBLISH,
    "--publish": _PUBLISH,
    "-P": _PUBLISH,
    "--publish-all": _PUBLISH,
    "--name": "Outpost names the container",
    "--restart": "Outpost sets --restart unless-stopped",
}


def base_image(sources_digest: str) -> ImageRef:
    """The default image, tagged with a digest of its sources so that any change rebuilds it."""
    return ImageRef(f"{BASE_REPOSITORY}:{sources_digest[:DIGEST_LENGTH]}")


# ------------------------------------------------------------------ your settings


@dataclass(frozen=True)
class DevContainerSettings:
    """Your devcontainer.json properties, checked once: JSON only, nothing Outpost owns."""

    properties: Mapping[str, Json] = field(default_factory=dict)

    @classmethod
    def parse(cls, raw: object, path: str) -> DevContainerSettings:
        if raw is None:
            return cls()
        value = _json(raw, path)
        if not isinstance(value, dict):
            raise ConfigError(path, "must be a mapping of devcontainer.json properties")
        for key in value:
            if key in OWNED_KEYS:
                raise ConfigError(f"{path}.{key}", f"is set by Outpost: {OWNED_KEYS[key]}")
        if "image" in value and "build" in value:
            raise ConfigError(path, "set `image` or `build`, not both")
        if "image" in value:
            _image(value["image"], f"{path}.image")
        _check_features(value.get("features"), f"{path}.features")
        _check_env(value.get("containerEnv"), f"{path}.containerEnv")
        _check_run_args(value.get("runArgs"), f"{path}.runArgs")
        _check_build(value.get("build"), f"{path}.build")
        return cls(value)


def _json(value: object, path: str) -> Json:
    match value:
        case None | bool() | int() | float() | str():
            return value
        case list():
            return [_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
        case Mapping():
            result: dict[str, Json] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ConfigError(path, f"key {key!r} must be a string")
                result[key] = _json(item, f"{path}.{key}")
            return result
        case _:
            raise ConfigError(path, "must be JSON: strings, numbers, booleans, lists, mappings")


def _image(value: Json, path: str) -> ImageRef:
    if not isinstance(value, str):
        raise ConfigError(path, "must be an image reference")
    try:
        return ImageRef(value)
    except InvalidValue as error:
        raise ConfigError(path, str(error)) from None


def _mapping(value: Json, path: str) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise ConfigError(path, "must be a mapping")
    return value


def _check_features(value: Json, path: str) -> None:
    if value is None:
        return
    for feature, options in _mapping(value, path).items():
        if feature.startswith(("./", "../", "/")):
            raise ConfigError(
                f"{path}.{feature}",
                "local features are not supported; publish it, or install it in your image",
            )
        if options is not None and not isinstance(options, dict | str):
            raise ConfigError(f"{path}.{feature}", "must be a mapping of options, or null")


def _check_env(value: Json, path: str) -> None:
    if value is None:
        return
    for name, item in _mapping(value, path).items():
        if name.startswith(RESERVED_ENV_PREFIX):
            raise ConfigError(
                f"{path}.{name}", f"{RESERVED_ENV_PREFIX}* variables are set by Outpost"
            )
        if item is not None and not isinstance(item, str):
            raise ConfigError(f"{path}.{name}", "must be a string (quote numbers)")


def refused_run_arg(token: str) -> str | None:
    """The flag a `runArgs` item uses that Outpost refuses, or None."""
    for flag in REFUSED_RUN_ARGS:
        if flag.startswith("--"):
            if token == flag or token.startswith(f"{flag}="):
                return flag
        elif token.startswith(flag) and not token.startswith("--"):
            return flag
    return None


def _check_run_args(value: Json, path: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(path, "must be a list of strings")
    for index, item in enumerate(value):
        flag = refused_run_arg(str(item))
        if flag:
            raise ConfigError(f"{path}[{index}]", f"{flag} is refused: {REFUSED_RUN_ARGS[flag]}")


def _check_build(value: Json, path: str) -> None:
    if value is None:
        return
    build = _mapping(value, path)
    for key in ("dockerfile", "context"):
        if key in build and not isinstance(build[key], str):
            raise ConfigError(f"{path}.{key}", "must be a path")
    if not isinstance(build.get("dockerfile"), str):
        raise ConfigError(f"{path}.dockerfile", "is required: the Dockerfile to build")
    args = _mapping(build.get("args") or {}, f"{path}.args")
    if BASE_IMAGE_ARG in args:
        raise ConfigError(f"{path}.args.{BASE_IMAGE_ARG}", "is set by Outpost to the base image")


# ------------------------------------------------------------------ the file Outpost runs


@dataclass(frozen=True)
class DevContainerDefinition:
    document: Mapping[str, Json]
    settings_digest: str
    image: ImageRef | None
    """The image to run as is; None when the container is built from your Dockerfile."""

    @property
    def needs_base(self) -> bool:
        """True when the default image must exist first: it runs, or a Dockerfile builds on it."""
        return self.image is None or self.image.value.startswith(f"{BASE_REPOSITORY}:")

    def text(self) -> str:
        return json.dumps(self.document, indent=2) + "\n"


def define(
    *,
    name: EnvironmentName,
    site: Site,
    volumes: Sequence[Volume],
    settings: DevContainerSettings,
    root: PurePath,
    base: ImageRef,
) -> DevContainerDefinition:
    """Merge your settings over the defaults, add what Outpost owns, then stamp the digest."""
    merged = _merge({"image": base.value, "features": {CLAUDE_CODE_FEATURE: {}}}, settings)
    document = _with_owned(merged, name, site, volumes, base)
    digest = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
    digest = digest[:DIGEST_LENGTH]
    run_args = document["runArgs"]
    assert isinstance(run_args, list)
    run_args.extend(["--label", f"{SETTINGS_LABEL}={digest}"])
    image = merged.get("image")
    return DevContainerDefinition(
        document=_resolve_build_paths(document, root),
        settings_digest=digest,
        image=ImageRef(image) if isinstance(image, str) else None,
    )


def _merge(defaults: dict[str, Json], settings: DevContainerSettings) -> dict[str, Json]:
    result = copy.deepcopy(defaults)
    if "build" in settings.properties:
        result.pop("image")
    for key, value in copy.deepcopy(dict(settings.properties)).items():
        if value is None:
            result.pop(key, None)
        elif key in MERGED_KEYS and isinstance(value, dict):
            current = result.get(key)
            merged = dict(current) if isinstance(current, dict) else {}
            for item, item_value in value.items():
                if item_value is None:
                    merged.pop(item, None)
                else:
                    merged[item] = item_value
            result[key] = merged
        else:
            result[key] = value
    return result


def _with_owned(
    merged: dict[str, Json],
    name: EnvironmentName,
    site: Site,
    volumes: Sequence[Volume],
    base: ImageRef,
) -> dict[str, Json]:
    document: dict[str, Json] = {"name": name.container}
    document.update({k: v for k, v in merged.items() if k not in ("containerEnv", "runArgs")})
    build = document.get("build")
    if isinstance(build, dict):
        build["args"] = {
            **_mapping(build.get("args") or {}, "build.args"),
            BASE_IMAGE_ARG: base.value,
        }
    workspaces = next(volume for volume in volumes if volume.target == WORKSPACES)
    document["workspaceMount"] = f"source={workspaces.name},target={WORKSPACES},type=volume"
    document["workspaceFolder"] = str(WORKSPACES)
    document["mounts"] = [
        {"type": "volume", "source": volume.name, "target": str(volume.target)}
        for volume in volumes
        if volume is not workspaces
    ]
    document["privileged"] = True
    document["overrideCommand"] = False
    document["remoteUser"] = USER
    document["updateRemoteUserUID"] = False
    env = merged.get("containerEnv")
    document["containerEnv"] = {
        **(env if isinstance(env, dict) else {}),
        ENV_NAME: name.value,
        ENV_DOMAIN: site.domain.value,
        ENV_PORT: str(site.port),
    }
    run_args = merged.get("runArgs")
    document["runArgs"] = [
        *(run_args if isinstance(run_args, list) else []),
        "--name",
        name.container,
        "--restart",
        "unless-stopped",
        "--publish",
        f"127.0.0.1:{site.port}:{PROXY_LISTEN_PORT}",
    ]
    return document


def _resolve_build_paths(document: dict[str, Json], root: PurePath) -> dict[str, Json]:
    """Paths in `build` are relative to outpost.yaml; the file Outpost writes lives elsewhere."""
    build = document.get("build")
    if isinstance(build, dict):
        for key in ("dockerfile", "context"):
            value = build.get(key)
            if isinstance(value, str):
                build[key] = str(root / value)
    return document
