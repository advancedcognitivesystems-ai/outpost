# 0001. Hostname routing through two proxies

Status: accepted, 2026-11-01

## Context

Many worktrees run the same stack of 24 services at once, on WSL and on Azure. Each service must be reachable from the client while new stacks appear and disappear during the day.

## Decision

Route by hostname, never by host port. An edge proxy on the host terminates TLS and forwards every name under the domain to a router inside the box. The router discovers stacks from Docker labels on the inner engine. Both are Traefik.

## Consequences

A new stack is routable as soon as its containers start, with no reload and no port bookkeeping. The edge never needs to see the inner engine's socket. Non-HTTP ports need a separate path (`stack forward`, planned).
