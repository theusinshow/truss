import os
from pathlib import Path
import shutil

import pytest


_BASE_PREFIX = ".truss-pytest-"


def pytest_configure(config: pytest.Config) -> None:
    """Reserva uma raiz curta no Windows sem sobrescrever --basetemp explicito."""
    if os.name != "nt" or config.option.basetemp is not None:
        return

    drive_root = Path(Path.cwd().anchor)
    base = drive_root / f"{_BASE_PREFIX}{os.getpid()}"
    config.option.basetemp = str(base)
    config._truss_basetemp = base  # type: ignore[attr-defined]


def pytest_unconfigure(config: pytest.Config) -> None:
    base = getattr(config, "_truss_basetemp", None)
    if not isinstance(base, Path):
        return

    drive_root = Path(base.anchor)
    if base.parent == drive_root and base.name.startswith(_BASE_PREFIX):
        shutil.rmtree(base, ignore_errors=True)
