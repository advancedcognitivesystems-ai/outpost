from __future__ import annotations

import pytest

from outpost.application.credentials import CredentialBinding, CredentialSync
from outpost.domain.config import AutoSource, EnvSource, ToolCredentials
from outpost.domain.credentials import Strategy, Tool
from outpost.domain.errors import Declined, Unavailable
from outpost.domain.secrets import Secret
from tests.fakes import FakePrompter, FakeSecretSource, FakeToolAuth


def _sync(
    strategy: Strategy,
    *,
    secret: str | None = None,
    box: FakeToolAuth | None = None,
    client: FakeToolAuth | None = None,
    choices: tuple[int, ...] = (),
    source: FakeSecretSource | None = None,
) -> tuple[CredentialSync, FakeToolAuth, FakeToolAuth, FakePrompter]:
    box = box or FakeToolAuth(Tool.CLAUDE)
    client = client or FakeToolAuth(Tool.CLAUDE, valid=True)
    prompter = FakePrompter(choices=choices)
    spec = ToolCredentials(Tool.CLAUDE, strategy, AutoSource())
    binding = CredentialBinding(spec, source or FakeSecretSource(secret), box, client)
    return CredentialSync([binding], prompter), box, client, prompter


def test_valid_login_is_left_alone_and_finished() -> None:
    sync, box, _, _ = _sync(Strategy.COPY, box=FakeToolAuth(Tool.CLAUDE, valid=True))
    (state,) = sync.sync()
    assert state.valid
    assert box.installed == []
    assert box.finished == 1


def test_copy_installs_the_client_credential() -> None:
    sync, box, _, _ = _sync(Strategy.COPY, secret='{"claudeAiOauth": {}}')
    sync.sync()
    assert box.installed == [Secret('{"claudeAiOauth": {}}')]


def test_copy_with_nothing_on_the_client_can_log_in_on_the_box() -> None:
    sync, box, _, prompter = _sync(Strategy.COPY, choices=(0,))
    sync.sync()
    assert box.logins == 1
    assert "No claude credential found" in prompter.questions[0]


def test_copy_can_log_in_on_the_client_then_copy() -> None:
    source = FakeSecretSource(None)

    class LoginFillsSource(FakeToolAuth):
        def login(self) -> None:
            super().login()
            source.value = "fresh"

    sync, box, client, _ = _sync(
        Strategy.COPY, choices=(1,), source=source, client=LoginFillsSource(Tool.CLAUDE)
    )
    sync.sync()
    assert client.logins == 1
    assert box.installed == [Secret("fresh")]


def test_stop_is_a_declined_step() -> None:
    sync, *_ = _sync(Strategy.COPY, choices=(2,))
    with pytest.raises(Declined):
        sync.sync()


def test_login_strategy_goes_straight_to_the_box() -> None:
    sync, box, _, prompter = _sync(Strategy.LOGIN)
    sync.sync()
    assert box.logins == 1
    assert prompter.questions == []


def test_skip_only_warns() -> None:
    sync, box, _, prompter = _sync(Strategy.SKIP)
    (state,) = sync.sync()
    assert not state.valid
    assert box.logins == 0
    assert prompter.messages == ["warning: claude: not logged in in the box (strategy: skip)"]


def test_a_login_that_does_not_stick_is_reported() -> None:
    sync, *_ = _sync(Strategy.LOGIN, box=FakeToolAuth(Tool.CLAUDE, login_works=False))
    with pytest.raises(Unavailable, match="still not logged in"):
        sync.sync()


def test_token_strategy_offers_no_client_login() -> None:
    box = FakeToolAuth(Tool.GITHUB)
    prompter = FakePrompter(choices=(1,))
    spec = ToolCredentials(Tool.GITHUB, Strategy.TOKEN, EnvSource("PAT"))
    binding = CredentialBinding(spec, FakeSecretSource(None), box, FakeToolAuth(Tool.GITHUB))
    with pytest.raises(Declined):
        CredentialSync([binding], prompter).sync()
