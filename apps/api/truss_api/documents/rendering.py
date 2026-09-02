from pathlib import Path

import fitz

from truss_api.core.settings import Settings
from truss_api.documents import repository
from truss_api.recovery.atomic import atomic_write_bytes
from truss_api.recovery.errors import TrussError


class RenderError(Exception):
    pass


def render_sheet_png(sheet_id: str, settings: Settings, scale: float = 2.0) -> Path:
    context = repository.get_sheet_render_context(sheet_id, settings)

    existing_render_path = context.get("render_path")
    if existing_render_path:
        existing_path = settings.data_dir / str(existing_render_path)
        if existing_path.exists():
            return existing_path

    source_path = settings.data_dir / str(context["stored_file_path"])
    if not source_path.exists():
        raise TrussError(
            code="PDF_SOURCE_MISSING",
            message="O PDF original desta folha nao foi encontrado.",
            action="Execute o diagnostico e restaure um backup valido em um novo diretorio.",
            status_code=500,
        )

    render_dir = (
        settings.renders_dir
        / str(context["project_id"])
        / str(context["revision_id"])
        / str(context["document_id"])
    )
    render_dir.mkdir(parents=True, exist_ok=True)
    output_path = render_dir / f"page-{int(context['page_index']) + 1:04d}@{scale:g}x.png"

    if not output_path.exists():
        try:
            document = fitz.open(source_path)
            try:
                page = document.load_page(int(context["page_index"]))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                png = pixmap.tobytes("png")
            finally:
                document.close()
            atomic_write_bytes(
                output_path,
                png,
                validator=lambda path: _validate_png(path),
            )
        except TrussError:
            raise
        except Exception as error:
            if isinstance(error, RenderError):
                raise
            raise RenderError("Could not render PDF page") from error

    repository.update_sheet_render_path(
        sheet_id,
        str(output_path.relative_to(settings.data_dir)),
        settings,
    )
    return output_path


def _validate_png(path: Path) -> None:
    if not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise RenderError("Rendered image is not a valid PNG")
