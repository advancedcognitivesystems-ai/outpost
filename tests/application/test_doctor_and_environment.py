from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

import pytest

from outpost.application.box import BoxImage
from outpost.application.checks import standard_checks
from outpost.application.containers import Change, converge
from outpost.application.credentials import CredentialBinding, CredentialSync
from outpost.application.doctor import Doctor
from outpost.application.environment import Environment, InnerRouter
from outpost.domain.checks import Status
from outpost.domain.config import ResolvedConfig
from outpost.domain.credentials import Strategy, Tool
from outpost.domain.errors import Declined, Unavailable
from outpost.domain.names import ImageRef
from outpost.ports.engine import ContainerSpec
from outpost.ports.shell import ClientNeeds
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


def _credentials(
    config: ResolvedConfig, prompter: FakePrompter, *, skip: Tool | None = None
) -> CredentialSync:
    bindings = []
    for spec in config.credentials.tools:
        strategy = Strategy.SKIP if spec.tool is skip else spec.strategy
        bindings.append(
            CredentialBinding(
                replace(spec, strategy=strategy),
                FakeSecretSource("secret", client_commands=("gh",)),
                FakeToolAuth(spec.tool),
                FakeToolAuth(spec.tool),
            )
        )
    return CredentialSync(bindings, prompter)


def _doctor(
    config: ResolvedConfig,
    engine: FakeEngine,
    prompter: FakePrompter,
    *,
    credentials: CredentialSync | None = None,
    needs: tuple[ClientNeeds, ...] = (),
    client: FakeProbe | None = None,
) -> Doctor:
    checks = standard_checks(
        config,
        client=client or FakeProbe(commands=("ssh", "scp", "gh")),
        client_needs=needs,
        host=FakeProbe(),
        host_description="ssh dev@vm",
        engine=engine,
        credentials=credentials or _credentials(config, prompter),
    )
    return Doctor(checks, prompter)


def _statuses(doctor: Doctor, *, fix: bool = False) -> dict[str, Status]:
    return {result.check_id: result.status for result in doctor.run(fix=fix).results}


def _running_box() -> FakeEngine:
    engine = FakeEngine()
    engine.run(ContainerSpec(name="outpost-acme-box", image=ImageRef("box")))
    return engine


def test_client_tools_come_from_the_adapters_in_use(azure: ResolvedConfig) -> None:
    needs = (
        FakeShell(client_commands=("ssh", "scp")),
        FakeSecretSource("x", client_commands=("az",)),
    )
    statuses = _statuses(_doctor(azure, FakeEngine(), FakePrompter(), needs=needs))
    assert statuses["client-tools"] is Status.FAIL


def test_wildcard_dns_is_checked_only_outside_localhost(
    azure: ResolvedConfig, wsl: ResolvedConfig
) -> None:
    assert "dns" in _statuses(_doctor(azure, FakeEngine(), FakePrompter()))
    assert "dns" not in _statuses(_doctor(wsl, FakeEngine(), FakePrompter()))


def test_doctor_skips_checks_whose_prerequisite_failed(wsl: ResolvedConfig) -> None:
    statuses = _statuses(_doctor(wsl, FakeEngine(reachable=False), FakePrompter()))
    assert statuses["engine"] is Status.FAIL
    assert statuses["isolation"] is Status.SKIPPED
    assert statuses["auth-claude"] is Status.SKIPPED


def test_doctor_offers_fixes_for_credentials(wsl: ResolvedConfig) -> None:
    prompter = FakePrompter(confirms=(True, True))
    statuses = _statuses(_doctor(wsl, _running_box(), prompter), fix=True)
    assert statuses["auth-claude"] is Status.OK
    assert statuses["auth-github"] is Status.OK


def test_a_skipped_tool_only_warns(wsl: ResolvedConfig) -> None:
    prompter = FakePrompter()
    credentials = _credentials(wsl, prompter, skip=Tool.CLAUDE)
    doctor = _doctor(wsl, _running_box(), prompter, credentials=credentials)
    report = doctor.run(fix=False)
    statuses = {result.check_id: result.status for result in report.results}
    assert statuses["auth-claude"] is Status.WARN


def test_converge_creates_then_leaves_alone_then_recreates() -> None:
    engine = FakeEngine()
    spec = ContainerSpec(name="edge", image=ImageRef("traefik:v3"))
    assert converge(engine, spec) is Change.CREATED
    assert converge(engine, spec) is Change.UNCHANGED
    engine.stop("edge")
    assert converge(engine, spec) is Change.STARTED
    newer = ContainerSpec(name="edge", image=ImageRef("traefik:v4"))
    assert converge(engine, newer) is Change.RECREATED
    with pytest.raises(Declined):
        converge(engine, spec, allow_recreate=lambda: False)


def test_inner_router_waits_for_the_inner_engine() -> None:
    waits: list[float] = []
    router = InnerRouter(FakeEngine(reachable=False), FakeRouter(), sleep=waits.append)
    with pytest.raises(Unavailable, match="did not start"):
        router.ensure()
    assert len(waits) == 60


def _environment(
    config: ResolvedConfig,
    engine: FakeEngine,
    prompter: FakePrompter,
    doctor: Doctor | None = None,
) -> tuple[Environment, FakeRepository, FakeShell, FakeEngine]:
    host = FakeShell()
    inner = FakeEngine()
    repository = FakeRepository()
    environment = Environment(
        config=config,
        doctor=doctor or Doctor([], prompter),
        host=host,
        host_probe=FakeProbe(),
        engine=engine,
        images=FakeImages(),
        box_image=BoxImage(config, host, engine, EchoTemplates(), "start-stacks"),
        tls=FakeTls(),
        edge=FakeEdge(),
        router=InnerRouter(inner, FakeRouter(), sleep=lambda _: None),
        credentials=_credentials(config, prompter),
        repository=repository,
        prompter=prompter,
    )
    return environment, repository, host, inner


def test_up_builds_then_runs_edge_box_router_then_clones(wsl: ResolvedConfig) -> None:
    engine = FakeEngine()
    environment, repository, host, inner = _environment(wsl, engine, FakePrompter())
    environment.up()
    runs = [event for event in engine.events if event.startswith(("build", "run"))]
    assert runs[0].startswith("build outpost-acme-box:")
    assert runs[1:] == ["run outpost-acme-edge", "run outpost-acme-box"]
    assert inner.events == ["run router"]
    assert inner.networks == {"routes"}
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
    environment, _, _, inner = _environment(wsl, engine, FakePrompter())
    environment.up()
    before = (list(engine.events), list(inner.events))
    environment.up()
    assert (engine.events, inner.events) == before


def test_up_stops_on_blocking_doctor_results(wsl: ResolvedConfig) -> None:
    engine = FakeEngine(reachable=False)
    prompter = FakePrompter()
    environment, *_ = _environment(wsl, engine, prompter, _doctor(wsl, engine, prompter))
    with pytest.raises(Unavailable, match="Docker engine"):
        environment.up()
