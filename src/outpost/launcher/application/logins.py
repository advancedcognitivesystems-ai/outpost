"""Logins in the container: check with the tool, copy yours when it has none, or offer a login."""

from __future__ import annotations

from collections.abc import Sequence

from outpost.domain.credentials import LoginState
from outpost.launcher.ports.credentials import LoginSource, ToolLogin
from outpost.launcher.ports.machine import Console


class Logins:
    def __init__(self, console: Console, pairs: Sequence[tuple[LoginSource, ToolLogin]]) -> None:
        self._console = console
        self._pairs = tuple(pairs)

    def ensure_all(self) -> tuple[LoginState, ...]:
        return tuple(self.ensure(source, login) for source, login in self._pairs)

    def ensure(self, source: LoginSource, login: ToolLogin) -> LoginState:
        state = login.state()
        if not state.valid and state.installed:
            state = self._copy(source, login, state)
        if not state.valid and state.installed:
            state = self._offer_login(login, state)
        if state.valid:
            login.finish()
        else:
            self._console.warn(
                f"{login.tool}: not logged in inside the container ({state.detail}); "
                "log in there from `./outpost shell`"
            )
        return state

    def _copy(self, source: LoginSource, login: ToolLogin, state: LoginState) -> LoginState:
        secret = source.read()
        if secret is None:
            self._console.info(f"{login.tool}: no login to copy from {source.description}")
            return state
        login.install(secret)
        copied = login.state()
        if copied.valid:
            self._console.info(f"{login.tool}: login copied from {source.description}")
        return copied

    def _offer_login(self, login: ToolLogin, state: LoginState) -> LoginState:
        question = (
            f"{login.tool} is not logged in inside the container ({state.detail}). Log in now?"
        )
        if not self._console.interactive or not self._console.confirm(question, default=True):
            return state
        login.login()
        return login.state()
