"""Init scripts from the image's and the state volume's `init.d`, and the boot record file."""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import TextIO

from outpost.domain.errors import InvalidValue
from outpost.domain.init import Script
from outpost.domain.layout import BOOT_RECORD, IMAGE_INIT_DIR, USER, USER_INIT_DIR
from outpost.domain.status import BootRecord
from outpost.infra.process import Runner

USER_VARIABLE = "OUTPOST_USER"


class ScriptDirectories:
    def __init__(
        self,
        runner: Runner,
        directories: Sequence[Path] = (Path(IMAGE_INIT_DIR), Path(USER_INIT_DIR)),
        log: TextIO = sys.stderr,
    ) -> None:
        self._runner = runner
        self._directories = tuple(directories)
        self._log = log

    def listing(self) -> tuple[Script, ...]:
        scripts: list[Script] = []
        for directory in self._directories:
            if not directory.is_dir():
                continue
            for path in sorted(item for item in directory.iterdir() if item.is_file()):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                scripts.append(Script(path.name, PurePosixPath(path.as_posix()), digest))
        return tuple(scripts)

    def run(self, script: Script) -> int:
        """Run it directly when executable, with sh otherwise; its output goes to the log."""
        path = str(script.path)
        argv = [path] if os.access(path, os.X_OK) else ["sh", path]
        print(f"outpost: init {script.name}", file=self._log, flush=True)
        code = self._runner.attached(argv, env={USER_VARIABLE: USER})
        if code != 0:
            print(f"outpost: init {script.name} failed with {code}", file=self._log, flush=True)
        return code


class JsonBootStore:
    def __init__(self, path: Path = Path(BOOT_RECORD)) -> None:
        self._path = path

    def read(self) -> BootRecord:
        try:
            return BootRecord.from_json(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, InvalidValue):
            return BootRecord(ready=False)

    def write(self, record: BootRecord) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        staged = self._path.with_suffix(".tmp")
        staged.write_text(record.to_json(), encoding="utf-8")
        staged.chmod(0o644)
        staged.replace(self._path)
