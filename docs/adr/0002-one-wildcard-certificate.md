# 0002. One wildcard certificate per environment

Status: accepted, 2026-11-01

## Context

Every route needs a valid certificate in the client's browser, including routes created minutes ago and hosts on private or VPN addresses.

## Decision

Issue one wildcard certificate per environment: Let's Encrypt through DNS-01 when the domain is public, a local CA trusted once on the client otherwise.

## Consequences

New names need no issuance and hit no rate limit. DNS-01 needs DNS provider credentials on the host. The local CA must be trusted on every client machine (`outpost tls trust`).
