from truss_api.core.settings import Settings
from truss_api.db.migrations import apply_migrations


def initialize_database(settings: Settings | None = None) -> None:
    apply_migrations(settings)
