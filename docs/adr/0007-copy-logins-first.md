# 0007. Copy logins first, log in inside as a fallback

Status: accepted, 2026-11-01.

## Context

Claude Code must use the claude.ai login inside the container: a token from `claude setup-token` or an API key does not load the claude.ai connectors. The GitHub CLI token is needed for git and `gh`.

## Decision

On every `up`, each tool checks its own login inside the container. Only when it is missing does Outpost copy yours: Claude Code's from the macOS Keychain or `~/.claude/.credentials.json`, the GitHub CLI's from `gh auth token`. With nothing to copy, `up` offers the tool's own login inside the container.

## Consequences

- One Claude refresh token is shared by your machine and the container until one side refreshes it. If one side gets logged out, log in inside the container instead; the home volume keeps that login.
- Secrets travel through stdin into files with mode 0600.
