"""Interactive or unattended prompting."""

from __future__ import annotations

from outpost.adapters.interaction.prompters import TerminalPrompter, UnattendedPrompter
from outpost.ports.interaction import Prompter


def build_prompter(*, assume_yes: bool) -> Prompter:
    return UnattendedPrompter() if assume_yes else TerminalPrompter()
