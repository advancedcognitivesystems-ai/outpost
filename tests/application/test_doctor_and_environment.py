from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from outpost.application.box import BoxImage
from outpost.application.checks import required_client_tools, standard_checks
from outpost.application.containers import Change, converge
from outpost.application.credentials import CredentialBinding, CredentialSync
from outpost.application.doctor import Doctor
from outpost.application.environment import Environment
from outpost.domain.checks import Status
from outpost.domain.config import ResolvedConfig
from outpost.domain.credentials import Tool
from outpost.domain.errors import Declined, Unavailable
from outpost.ports.engine import ContainerSpec
from tests.fakes import (
    EchoTemplates,
    FakeEdge,
    FakeEngine,
    FakeImages,
    FakeProbe,
    FakePrompter,
    FakeRepository,
    FakeRouter,
    FakeSecretSource,
    FakeShell,
    FakeTls,
    FakeToolAuth,
)


def _credentials(config: ResolvedConfig, prompter: FakePrompter) -> CredentialSync:
    bindings = [
        CredentialBinding(
            spec, FakeSecretSource("secret"), FakeToolAuth(spec.tool), FakeToolAuth(spec.tool)
        )
        for spec in config.credentials.tools
    ]
    return CredentialSync(bindings, prompter)


def _doctor(config: ResolvedConfig, engine: FakeEngine, prompter: FakePrompter) -> Doctor:
    checks = standard_checks(
        config,
        client=FakeProbe(commands=("ssh", "scp", "az", "gh")),
        host=FakeProbe(),
        host_description="ssh dev@vm",
        engine=engine,
        credentials=_credentials(config, prompter),
    )
    return Doctor(checks, prompter)


def test_required_client_tools(azure: ResolvedConfig, wsl: ResolvedConfig) -> None:
    assert required_client_tools(azure) == ("ssh", "scp", "az", "gh")
    assert required_client_tools(wsl) == ("gh",)


def test_doctor_skips_checks_whose_prerequisite_failed(wsl: ResolvedConfig) -> None:
    prompter = FakePrompter()
    report = _doctor(wsl, FakeEngine(reachable=False), prompter).run(fix=False)
    statuses = {result.check_id: result.status for result in report.results}
    assert statuses["engine"] is Status.FAIL
    assert statuses["isolation"] is Status.SKIPPED
    assert statuses["auth-claude"] is Status.SKIPPED
    assert report.blocking


def test_doctor_offers_fixes_for_credentials(wsl: ResolvedConfig) -> None:
    engine = FakeEngine()
    engine.run(ContainerSpec(name="outpost-acme-box", image="box"))
    prompter = FakePrompter(confirms=(True, True))
    report = _doctor(wsl, engine, prompter).run(fix=True)
    statuses = {result.check_id: result.status for result in report.results}
    assert statuses["auth-claude"] is Status.OK
    assert statuses["auth-github"] is Status.OK
    assert not report.blocking


def test_converge_creates_then_leaves_alone_then_recreates() -> None:
    engine = FakeEngine()
    spec = ContainerSpec(name="edge", image="traefik:v3")
    assert converge(engine, spec) is Change.CREATED
    assert converge(engine, spec) is Change.UNCHANGED
    engine.stop("edge")
    assert converge(engine, spec) is Change.STARTED
    assert converge(engine, ContainerSpec(name="edge", image="traefik:v4")) is Change.RECREATED
    with pytest.raises(Declined):
        converge(engine, spec, allow_recreate=lambda: False)


def _environment(
    config: ResolvedConfig,
    engine: FakeEngine,
    prompter: FakePrompter,
    doctor: Doctor | None = None,
) -> tuple[Environment, FakeRepository, FakeShell]:
    host = FakeShell()
    repository = FakeRepository()
    environment = Environment(
        config=config,
        doctor=doctor or Doctor([], prompter),
        host=host,
        host_probe=FakeProbe(),
        engine=engine,
        images=FakeImages(),
        box_image=BoxImage(config, host, engine, EchoTemplates(), FakeRouter()),
        tls=FakeTls(),
        edge=FakeEdge(),
        credentials=_credentials(config, prompter),
        repository=repository,
        prompter=prompter,
    )
    return environment, repository, host


def test_up_builds_runs_edge_then_box_then_clones(wsl: ResolvedConfig) -> None:
    engine = FakeEngine()
    prompter = FakePrompter()
    environment, repository, host = _environment(wsl, engine, prompter)
    environment.up()
    runs = [event for event in engine.events if event.startswith(("build", "run"))]
    assert runs[0].startswith("build outpost-acme-box:")
    assert runs[1:] == ["run outpost-acme-edge", "run outpost-acme-box"]
    assert engine.volumes == {
        "outpost-acme-workspaces",
        "outpost-acme-docker",
        "outpost-acme-home",
        "outpost-acme-edge-data",
    }
    assert PurePosixPath("/home/dev/.outpost/exchange") in host.directories
    assert repository.cloned
    assert repository.identity == wsl.credentials.git


def test_up_twice_changes_nothing(wsl: ResolvedConfig) -> None:
    engine = FakeEngine()
    environment, _, _ = _environment(wsl, engine, FakePrompter())
    environment.up()
    before = list(engine.events)
    environment.up()
    assert engine.events == before


def test_up_stops_on_blocking_doctor_results(wsl: ResolvedConfig) -> None:
    engine = FakeEngine(reachable=False)
    prompter = FakePrompter()
    environment, _, _ = _environment(wsl, engine, prompter, _doctor(wsl, engine, prompter))
    with pytest.raises(Unavailable, match="Docker engine"):
        environment.up()


def test_tools_are_known_to_credentials(wsl: ResolvedConfig) -> None:
    assert _credentials(wsl, FakePrompter()).tools == (Tool.CLAUDE, Tool.GITHUB)
