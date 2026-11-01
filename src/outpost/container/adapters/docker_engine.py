"""`Engine` through the inner Docker's CLI."""

from __future__ import annotations

from outpost.infra.process import Runner

NETWORKS = "{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}"


class DockerEngine:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner

    def is_container(self, name: str) -> bool:
        return self._runner.run(["docker", "container", "inspect", "--format", "{{.Id}}", name]).ok

    def networks(self, container: str) -> tuple[str, ...]:
        argv = ["docker", "container", "inspect", "--format", NETWORKS, container]
        return tuple(self._runner.run(argv).check().stdout.split())

    def connect(self, network: str, container: str) -> None:
        self._runner.run(["docker", "network", "connect", network, container]).check()
