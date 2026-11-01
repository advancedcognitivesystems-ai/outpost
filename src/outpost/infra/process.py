"""Running programs. Every adapter that runs one goes through a `Runner`, so tests can fake it."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import IO, Protocol, TextIO

from outpost.domain.commands import COMMAND_NOT_FOUND, CommandResult

type Env = Mapping[str, str] | None
type Writer = Callable[[IO[bytes]], None]
type Reader = Callable[[IO[bytes]], None]


class Runner(Protocol):
    def run(
        self, argv: Sequence[str], *, env: Env = None, stdin: str | None = None
    ) -> CommandResult:
        """Run without the terminal and capture the output; stdin is the given text or nothing."""
        ...

    def attached(self, argv: Sequence[str], *, env: Env = None) -> int:
        """Run on the terminal, for interactive programs and progress output."""
        ...

    def feed(self, argv: Sequence[str], write: Writer, *, env: Env = None) -> CommandResult:
        """Stream bytes into a program's stdin, as `write` produces them."""
        ...

    def drain(self, argv: Sequence[str], read: Reader, *, env: Env = None) -> CommandResult:
        """Stream a program's stdout into `read`."""
        ...

    def pipe(
        self, producer: Sequence[str], consumer: Sequence[str], *, env: Env, consumer_env: Env
    ) -> CommandResult:
        """`producer | consumer`; the result is the first failure, or the consumer's success."""
        ...


class SubprocessRunner:
    def __init__(self, trace: TextIO | None = None) -> None:
        self._trace = trace

    def run(
        self, argv: Sequence[str], *, env: Env = None, stdin: str | None = None
    ) -> CommandResult:
        self._log(argv, env)
        try:
            completed = subprocess.run(
                list(argv),
                input=stdin,
                stdin=None if stdin is not None else subprocess.DEVNULL,
                capture_output=True,
                text=True,
                env=_environ(env),
                check=False,
            )
        except FileNotFoundError:
            return _not_found(argv)
        return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)

    def attached(self, argv: Sequence[str], *, env: Env = None) -> int:
        self._log(argv, env)
        try:
            return subprocess.run(list(argv), env=_environ(env), check=False).returncode
        except FileNotFoundError:
            return COMMAND_NOT_FOUND

    def feed(self, argv: Sequence[str], write: Writer, *, env: Env = None) -> CommandResult:
        self._log(argv, env)
        try:
            process = subprocess.Popen(
                list(argv),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=_environ(env),
            )
        except FileNotFoundError:
            return _not_found(argv)
        assert process.stdin is not None
        assert process.stderr is not None
        try:
            write(process.stdin)
        except BrokenPipeError:
            pass
        finally:
            process.stdin.close()
        stderr = process.stderr.read().decode(errors="replace")
        return CommandResult(tuple(argv), process.wait(), "", stderr)

    def drain(self, argv: Sequence[str], read: Reader, *, env: Env = None) -> CommandResult:
        self._log(argv, env)
        try:
            process = subprocess.Popen(
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_environ(env),
            )
        except FileNotFoundError:
            return _not_found(argv)
        assert process.stdout is not None
        assert process.stderr is not None
        with process.stdout:
            read(process.stdout)
        stderr = process.stderr.read().decode(errors="replace")
        return CommandResult(tuple(argv), process.wait(), "", stderr)

    def pipe(
        self, producer: Sequence[str], consumer: Sequence[str], *, env: Env, consumer_env: Env
    ) -> CommandResult:
        self._log(producer, env)
        self._log(consumer, consumer_env)
        try:
            first = subprocess.Popen(
                list(producer), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_environ(env)
            )
        except FileNotFoundError:
            return _not_found(producer)
        try:
            second = subprocess.Popen(
                list(consumer),
                stdin=first.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=_environ(consumer_env),
            )
        except FileNotFoundError:
            first.kill()
            return _not_found(consumer)
        assert first.stdout is not None
        assert first.stderr is not None
        assert second.stderr is not None
        first.stdout.close()
        consumer_err = second.stderr.read().decode(errors="replace")
        consumer_code = second.wait()
        producer_err = first.stderr.read().decode(errors="replace")
        producer_code = first.wait()
        if producer_code != 0:
            return CommandResult(tuple(producer), producer_code, "", producer_err)
        return CommandResult(tuple(consumer), consumer_code, "", consumer_err)

    def _log(self, argv: Sequence[str], env: Env) -> None:
        if self._trace is None:
            return
        prefix = " ".join(f"{name}={value}" for name, value in (env or {}).items())
        print(f"+ {prefix + ' ' if prefix else ''}{shlex.join(argv)}", file=self._trace)


def _environ(overrides: Env) -> dict[str, str] | None:
    return {**os.environ, **overrides} if overrides else None


def _not_found(argv: Sequence[str]) -> CommandResult:
    return CommandResult(tuple(argv), COMMAND_NOT_FOUND, "", f"{argv[0]}: command not found")


def stderr_runner(verbose: bool) -> SubprocessRunner:
    return SubprocessRunner(trace=sys.stderr if verbose else None)
