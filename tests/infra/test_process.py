"""The real runner, on real processes: streams never deadlock, failures to start are codes."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import IO

from outpost.infra.process import CANNOT_EXECUTE, COMMAND_NOT_FOUND, SubprocessRunner

NOISY = "import sys; sys.stderr.write('w' * 300_000); sys.stderr.flush(); "


def test_feed_survives_a_program_that_writes_a_lot_of_errors() -> None:
    reader = NOISY + "data = sys.stdin.buffer.read(); sys.stdout.write(str(len(data)))"

    def write(out: IO[bytes]) -> None:
        for _ in range(64):
            out.write(b"x" * 16_384)

    result = SubprocessRunner().feed([sys.executable, "-c", reader], write)
    assert result.ok
    assert len(result.stderr) == 300_000


def test_drain_survives_a_program_that_writes_a_lot_of_errors() -> None:
    writer = NOISY + "sys.stdout.buffer.write(b'y' * 1_000_000)"
    received = io.BytesIO()

    def read(stream: IO[bytes]) -> None:
        received.write(stream.read())

    result = SubprocessRunner().drain([sys.executable, "-c", writer], read)
    assert result.ok
    assert len(received.getvalue()) == 1_000_000


def test_programs_that_cannot_start_are_codes(tmp_path: Path) -> None:
    runner = SubprocessRunner()
    assert runner.run(["outpost-no-such-program"]).code == COMMAND_NOT_FOUND
    script = tmp_path / "no-shebang"
    script.write_text("echo hi\n", encoding="utf-8")
    script.chmod(0o755)
    assert runner.attached([str(script)]) in (0, CANNOT_EXECUTE)
    not_executable = tmp_path / "plain"
    not_executable.write_text("x", encoding="utf-8")
    assert runner.run([str(not_executable)]).code == CANNOT_EXECUTE
