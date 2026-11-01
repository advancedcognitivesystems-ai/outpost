"""Credential flow: check in the box, then copy, use a token, or log in, as the strategy says."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from outpost.domain.config import ToolCredentials
from outpost.domain.credentials import AuthState, Strategy, Tool
from outpost.domain.errors import Declined, Unavailable
from outpost.domain.secrets import Secret
from outpost.ports.credentials import SecretSource, ToolAuth
from outpost.ports.interaction import Prompter


@dataclass(frozen=True)
class CredentialBinding:
    """One tool: its strategy, where `copy` or `token` read, and its auth on each side."""

    spec: ToolCredentials
    source: SecretSource
    box: ToolAuth
    client: ToolAuth


class CredentialSync:
    def __init__(self, bindings: Sequence[CredentialBinding], prompter: Prompter) -> None:
        self._bindings = {binding.spec.tool: binding for binding in bindings}
        self._prompter = prompter

    @property
    def tools(self) -> tuple[Tool, ...]:
        return tuple(self._bindings)

    @property
    def sources_in_use(self) -> tuple[SecretSource, ...]:
        """The client sources the configured strategies will read."""
        reading = {Strategy.COPY, Strategy.TOKEN}
        return tuple(
            binding.source
            for binding in self._bindings.values()
            if binding.spec.strategy in reading
        )

    def state(self, tool: Tool) -> AuthState:
        return self._bindings[tool].box.state()

    def skips(self, tool: Tool) -> bool:
        return self._bindings[tool].spec.strategy is Strategy.SKIP

    def sync(self, only: Tool | None = None) -> tuple[AuthState, ...]:
        return tuple(
            self._sync(binding)
            for tool, binding in self._bindings.items()
            if only is None or only is tool
        )

    def _sync(self, binding: CredentialBinding) -> AuthState:
        tool, strategy = binding.spec.tool, binding.spec.strategy
        state = binding.box.state()
        if not state.valid:
            if strategy is Strategy.SKIP:
                self._prompter.warn(f"{tool}: not logged in in the box (strategy: skip)")
                return state
            self._put_in_place(binding)
            state = binding.box.state()
            if not state.valid:
                raise Unavailable(f"{tool}: still not logged in after {strategy}: {state.detail}")
        binding.box.finish()
        return state

    def _put_in_place(self, binding: CredentialBinding) -> None:
        match binding.spec.strategy:
            case Strategy.LOGIN:
                binding.box.login()
            case Strategy.COPY | Strategy.TOKEN:
                secret = binding.source.read() or self._recover(binding)
                if secret is not None:
                    binding.box.install(secret)
            case Strategy.SKIP:
                return

    def _recover(self, binding: CredentialBinding) -> Secret | None:
        """Nothing to copy: log in on the box, or on this machine and copy, or stop."""
        tool = binding.spec.tool
        can_copy = binding.spec.strategy is Strategy.COPY
        options = ["Log in on the box now"]
        if can_copy:
            options.append("Log in on this machine, then copy")
        options.append("Stop")
        choice = self._prompter.choose(
            f"No {tool} credential found in {binding.source.description}.", options
        )
        if choice == 0:
            binding.box.login()
            return None
        if can_copy and choice == 1:
            binding.client.login()
            secret = binding.source.read()
            if secret is None:
                raise Unavailable(f"{tool}: logged in, but {binding.source.description} is empty")
            return secret
        raise Declined(f"{tool} credentials are needed in the box")
