"""Running programs. Every adapter that runs one goes through a `Runner`, so tests can fake it."""

from __future__ import annotations

import contextlib
import os
import shlex
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO, Protocol, TextIO

from outpost.domain.errors import CommandFailed

COMMAND_NOT_FOUND = 127
CANNOT_EXECUTE = 126

type Env = Mapping[str, str] | None
type Writer = Callable[[IO[bytes]], None]
type Reader = Callable[[IO[bytes]], None]


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0

    @property
    def missing_command(self) -> bool:
        return self.code == COMMAND_NOT_FOUND

    def check(self) -> CommandResult:
        """Return itself when the command succeeded, raise `CommandFailed` otherwise."""
        if not self.ok:
            raise CommandFailed(self.argv, self.code, self.stderr)
        return self


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


class _Collector:
    """Reads a stream on its own thread, so a full pipe never blocks the program."""

    def __init__(self, stream: IO[bytes] | None) -> None:
        self._chunks: list[bytes] = []
        self._thread = threading.Thread(target=self._read, args=(stream,), daemon=True)
        self._thread.start()

    def _read(self, stream: IO[bytes] | None) -> None:
        if stream is None:
            return
        with stream:
            for chunk in iter(lambda: stream.read(1 << 16), b""):
                self._chunks.append(chunk)

    def text(self) -> str:
        self._thread.join()
        return b"".join(self._chunks).decode(errors="replace")


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
        except OSError as error:
            return _not_started(argv, error)
        return CommandResult(tuple(argv), completed.returncode, completed.stdout, completed.stderr)

    def attached(self, argv: Sequence[str], *, env: Env = None) -> int:
        self._log(argv, env)
        try:
            return subprocess.run(list(argv), env=_environ(env), check=False).returncode
        except OSError as error:
            result = _not_started(argv, error)
            print(result.stderr, file=sys.stderr)
            return result.code

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
        except OSError as error:
            return _not_started(argv, error)
        errors = _Collector(process.stderr)
        assert process.stdin is not None
        try:
            write(process.stdin)
        except BrokenPipeError:
            pass
        finally:
            with contextlib.suppress(BrokenPipeError):
                process.stdin.close()
            code = process.wait()
        return CommandResult(tuple(argv), code, "", errors.text())

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
        except OSError as error:
            return _not_started(argv, error)
        errors = _Collector(process.stderr)
        assert process.stdout is not None
        try:
            with process.stdout:
                read(process.stdout)
        finally:
            code = process.wait()
        return CommandResult(tuple(argv), code, "", errors.text())

    def pipe(
        self, producer: Sequence[str], consumer: Sequence[str], *, env: Env, consumer_env: Env
    ) -> CommandResult:
        self._log(producer, env)
        self._log(consumer, consumer_env)
        try:
            first = subprocess.Popen(
                list(producer), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_environ(env)
            )
        except OSError as error:
            return _not_started(producer, error)
        first_errors = _Collector(first.stderr)
        try:
            second = subprocess.Popen(
                list(consumer),
                stdin=first.stdout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=_environ(consumer_env),
            )
        except OSError as error:
            first.kill()
            first.wait()
            return _not_started(consumer, error)
        second_errors = _Collector(second.stderr)
        assert first.stdout is not None
        first.stdout.close()
        consumer_code = second.wait()
        producer_code = first.wait()
        if producer_code != 0:
            return CommandResult(tuple(producer), producer_code, "", first_errors.text())
        return CommandResult(tuple(consumer), consumer_code, "", second_errors.text())

    def _log(self, argv: Sequence[str], env: Env) -> None:
        if self._trace is None:
            return
        prefix = " ".join(f"{name}={value}" for name, value in (env or {}).items())
        print(f"+ {prefix + ' ' if prefix else ''}{shlex.join(argv)}", file=self._trace)


def _environ(overrides: Env) -> dict[str, str] | None:
    return {**os.environ, **overrides} if overrides else None


def _not_started(argv: Sequence[str], error: OSError) -> CommandResult:
    """A program that could not start: missing (127), or not executable (126)."""
    code = COMMAND_NOT_FOUND if isinstance(error, FileNotFoundError) else CANNOT_EXECUTE
    return CommandResult(tuple(argv), code, "", f"{argv[0]}: {error.strerror or error}")


def stderr_runner(verbose: bool) -> SubprocessRunner:
    return SubprocessRunner(trace=sys.stderr if verbose else None)
