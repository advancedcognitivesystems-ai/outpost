# 0003. Flat route names

Status: accepted, 2026-11-01

## Context

A wildcard certificate for `*.dev.example.com` does not cover `api.feat-a.dev.example.com`.

## Decision

Name routes `<service>--<worktree>.<domain>`, one DNS label before the domain. Worktree names cannot contain `--`, and a route longer than 63 characters is refused.

## Consequences

Every route sits under the single wildcard. Worktree names are limited to 40 characters.
