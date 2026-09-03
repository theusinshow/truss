from collections.abc import Callable, Iterator
from contextlib import contextmanager
import os
from pathlib import Path
from uuid import uuid4

from truss_api.recovery.errors import storage_error


Validator = Callable[[Path], None]


def _partial_path(target: Path) -> Path:
    # O arquivo temporario precisa ficar no mesmo diretorio para que o replace
    # final continue atomico, mas nao deve repetir o nome (potencialmente longo)
    # do artefato. Isso preserva margem para os limites de caminho do Windows.
    return target.parent / f".{uuid4().hex}.partial"


def _sync_file(path: Path) -> None:
    # Windows exige um descritor gravavel para fsync.
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


@contextmanager
def atomic_output_path(
    target: Path,
    *,
    validator: Validator | None = None,
    operation_id: str | None = None,
) -> Iterator[Path]:
    partial = _partial_path(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        yield partial
        if not partial.is_file():
            raise OSError(f"Atomic writer did not create {partial.name}")
        _sync_file(partial)
        if validator is not None:
            validator(partial)
        os.replace(partial, target)
    except OSError as error:
        partial.unlink(missing_ok=True)
        raise storage_error(error, operation_id=operation_id) from error
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def atomic_write_bytes(
    target: Path,
    content: bytes,
    *,
    validator: Validator | None = None,
    operation_id: str | None = None,
) -> None:
    with atomic_output_path(
        target,
        validator=validator,
        operation_id=operation_id,
    ) as partial:
        partial.write_bytes(content)


def atomic_write_text(
    target: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    validator: Validator | None = None,
    operation_id: str | None = None,
) -> None:
    with atomic_output_path(
        target,
        validator=validator,
        operation_id=operation_id,
    ) as partial:
        partial.write_text(content, encoding=encoding)
