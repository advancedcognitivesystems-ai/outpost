"""The devcontainer.json Outpost runs: defaults, merging, what it owns, what it refuses."""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath

import pytest

from outpost.domain.devcontainer import (
    BASE_IMAGE_ARG,
    CLAUDE_CODE_FEATURE,
    DevContainerSettings,
    base_image,
)
from outpost.domain.environment import Environment
from outpost.domain.errors import ConfigError
from outpost.domain.names import ImageRef

BASE = base_image("0123456789abcdef")
ROOT = PurePath("/home/me/project")


def define(settings: object = None, root: PurePath = ROOT) -> dict[str, object]:
    environment = Environment(
        root=root, devcontainer=DevContainerSettings.parse(settings, "devcontainer")
    )
    return dict(environment.definition(BASE).document)


def test_defaults_run_the_base_image_with_claude_code() -> None:
    document = define()
    assert document["image"] == "outpost/base:0123456789ab"
    assert document["features"] == {CLAUDE_CODE_FEATURE: {}}
    assert document["name"] == "outpost-main"
    assert document["remoteUser"] == "dev"
    assert document["privileged"] is True
    assert document["overrideCommand"] is False
    assert document["updateRemoteUserUID"] is False


def test_every_mount_is_a_named_volume() -> None:
    document = define()
    assert document["workspaceMount"] == (
        "source=outpost-main-workspaces,target=/workspaces,type=volume"
    )
    assert document["workspaceFolder"] == "/workspaces"
    mounts = document["mounts"]
    assert isinstance(mounts, list)
    assert {mount["type"] for mount in mounts} == {"volume"}
    assert [mount["target"] for mount in mounts] == [
        "/home/dev",
        "/var/lib/docker",
        "/var/lib/outpost",
    ]


def test_outpost_owns_the_name_restart_policy_and_the_only_published_port() -> None:
    run_args = define({"runArgs": ["--cpus=8"]})["runArgs"]
    assert isinstance(run_args, list)
    assert run_args[:1] == ["--cpus=8"]
    assert run_args[1:11] == [
        "--name",
        "outpost-main",
        "--restart",
        "unless-stopped",
        "--stop-timeout",
        "60",
        "--publish",
        "127.0.0.1:8443:443",
        "--label",
        run_args[10],
    ]
    assert str(run_args[10]).startswith("outpost.settings=")


def test_features_and_env_merge_key_by_key_and_null_removes() -> None:
    document = define(
        {
            "features": {
                "ghcr.io/devcontainers/features/dotnet:2": {"version": "9.0"},
                CLAUDE_CODE_FEATURE: None,
            },
            "containerEnv": {"TZ": "Europe/Zurich"},
        }
    )
    assert document["features"] == {"ghcr.io/devcontainers/features/dotnet:2": {"version": "9.0"}}
    env = document["containerEnv"]
    assert isinstance(env, dict)
    assert env["TZ"] == "Europe/Zurich"
    assert env["OUTPOST_DOMAIN"] == "dev.localhost"
    assert env["OUTPOST_PORT"] == "8443"


def test_build_replaces_the_image_and_builds_on_the_base() -> None:
    environment = Environment(
        root=ROOT,
        devcontainer=DevContainerSettings.parse(
            {"build": {"dockerfile": "image/Dockerfile", "context": "."}}, "devcontainer"
        ),
    )
    definition = environment.definition(BASE)
    assert "image" not in definition.document
    assert definition.image is None
    assert definition.needs_base
    assert definition.document["build"] == {
        "dockerfile": "/home/me/project/image/Dockerfile",
        "context": "/home/me/project",
        "args": {BASE_IMAGE_ARG: BASE.value},
    }


def test_another_image_does_not_need_the_base() -> None:
    environment = Environment(
        root=ROOT, devcontainer=DevContainerSettings.parse({"image": "acme/dev:3"}, "dc")
    )
    definition = environment.definition(BASE)
    assert definition.image == ImageRef("acme/dev:3")
    assert not definition.needs_base


def test_the_digest_follows_the_settings_not_the_folder() -> None:
    build = {"build": {"dockerfile": "Dockerfile"}}

    def digest(settings: object, root: PurePath = ROOT) -> str:
        environment = Environment(root=root, devcontainer=DevContainerSettings.parse(settings, "d"))
        return environment.definition(BASE).settings_digest

    assert digest(None) == digest(None)
    assert digest({"containerEnv": {"A": "1"}}) != digest(None)
    assert digest(build) == digest(build, PurePath("/elsewhere"))


@pytest.mark.parametrize(
    ("settings", "path"),
    [
        ({"mounts": ["source=/x,target=/y,type=bind"]}, "devcontainer.mounts"),
        ({"workspaceMount": "type=bind"}, "devcontainer.workspaceMount"),
        ({"privileged": False}, "devcontainer.privileged"),
        ({"appPort": [3000]}, "devcontainer.appPort"),
        ({"dockerComposeFile": "compose.yaml"}, "devcontainer.dockerComposeFile"),
        ({"runArgs": ["-v", "/x:/y"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["--cpus=2", "--volume=/x:/y"]}, "devcontainer.runArgs[1]"),
        ({"runArgs": ["--mount", "type=bind,src=/x,dst=/y"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["-p", "5432:5432"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["--name=x"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["-tv", "/:/host"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["--network=host"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["--net", "host"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["--volumes-from", "cache"]}, "devcontainer.runArgs[0]"),
        ({"runArgs": ["--stop-timeout=5"]}, "devcontainer.runArgs[0]"),
        ({"features": {"./my-feature": {}}}, "devcontainer.features../my-feature"),
        ({"containerEnv": {"OUTPOST_PORT": "1"}}, "devcontainer.containerEnv.OUTPOST_PORT"),
        ({"containerEnv": {"PORT": 1}}, "devcontainer.containerEnv.PORT"),
        ({"image": "x", "build": {"dockerfile": "D"}}, "devcontainer"),
        ({"build": {"context": "."}}, "devcontainer.build.dockerfile"),
        ({"build": {"dockerfile": "D", "args": {"OUTPOST_BASE": "x"}}}, "devcontainer.build.args"),
        ({"image": "Not An Image"}, "devcontainer.image"),
        (["image"], "devcontainer"),
    ],
)
def test_refusals_name_the_key(settings: object, path: str) -> None:
    with pytest.raises(ConfigError) as caught:
        DevContainerSettings.parse(settings, "devcontainer")
    assert caught.value.path.startswith(path)


def test_harmless_run_args_pass() -> None:
    run_args = ["--cpus=8", "-e", "VERBOSE=1", "-ePV=1", "--memory", "24g", "--shm-size=2g"]
    assert DevContainerSettings.parse({"runArgs": run_args}, "d").properties["runArgs"] == run_args


def test_persisted_paths_reach_the_container() -> None:
    environment = Environment(
        root=ROOT, persist=(PurePosixPath("/opt/tools"), PurePosixPath("/srv/cache"))
    )
    env = environment.definition(BASE).document["containerEnv"]
    assert isinstance(env, dict)
    assert env["OUTPOST_PERSIST"] == "/opt/tools:/srv/cache"
