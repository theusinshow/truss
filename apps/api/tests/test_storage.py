from truss_api.core.settings import Settings
from truss_api.core.storage import ensure_storage_layout, storage_directories


def test_ensure_storage_layout_creates_expected_directories(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "truss-data")

    ensure_storage_layout(settings)

    for directory in storage_directories(settings):
        assert directory.exists()
        assert directory.is_dir()
