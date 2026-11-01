# 0007. Copy credentials first, log in as fallback

Status: accepted, 2026-11-01

## Context

Agents in the box need Claude Code (with claude.ai connectors) and GitHub. A long-lived `setup-token` cannot load claude.ai connectors; only the full claude.ai login can.

## Decision

Check each tool in the box on every `up`. By default copy the client's credential; when the client has none, offer to log in on the box or on the client then copy. `login`, `token` (GitHub) and `skip` are alternatives.

## Consequences

Copying a Claude login shares one refresh token between client and box; if refresh rotates it, one side may be logged out. To verify on a real host; switch to `login` if it happens.
