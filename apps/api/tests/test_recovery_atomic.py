from pathlib import Path

import pytest

from truss_api.recovery.atomic import atomic_output_path, atomic_write_bytes
from truss_api.recovery.errors import TrussError


def test_atomic_write_promotes_complete_content(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "artifact.bin"

    atomic_write_bytes(target, b"complete")

    assert target.read_bytes() == b"complete"
    assert list(target.parent.glob("*.partial")) == []


def test_atomic_write_does_not_publish_when_validator_fails(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"

    with pytest.raises(ValueError, match="invalid"):
        atomic_write_bytes(
            target,
            b"partial",
            validator=lambda _path: (_ for _ in ()).throw(ValueError("invalid")),
        )

    assert not target.exists()
    assert list(tmp_path.glob(".*.partial")) == []


def test_atomic_output_translates_storage_failure(tmp_path: Path) -> None:
    target = tmp_path / "artifact.bin"

    with pytest.raises(TrussError) as captured:
        with atomic_output_path(target):
            raise OSError(28, "disk full")

    assert captured.value.public.code == "STORAGE_FULL"
    assert captured.value.public.retryable is True
