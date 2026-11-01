# 0006. A layered Python CLI behind one bash script

Status: accepted, 2026-11-01

## Context

Outpost must start from one script, stay readable as it grows, and let each design choice change without touching the rest.

## Decision

Write Outpost in Python 3.12, bootstrapped by uv from a bash entry script. Layer it as domain, ports, application, adapters and CLI, with import contracts enforced in CI and one factory per configuration kind.

## Consequences

Each choice can be swapped by adding an adapter and a factory case. Contributors need uv; the client needs bash.
