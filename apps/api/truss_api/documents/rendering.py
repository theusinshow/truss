from pathlib import Path

import fitz

from truss_api.core.settings import Settings
from truss_api.documents import repository


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
        raise RenderError("Source PDF file is missing")

    render_dir = (
        settings.renders_dir
        / str(context["project_id"])
        / str(context["revision_id"])
        / str(context["document_id"])
    )
    render_dir.mkdir(parents=True, exist_ok=True)
    output_path = render_dir / f"page-{int(context['page_index']) + 1:04d}@{scale:g}x.png"

    if not output_path.exists():
        document = fitz.open(source_path)
        try:
            page = document.load_page(int(context["page_index"]))
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pixmap.save(output_path)
        except Exception as error:
            raise RenderError("Could not render PDF page") from error
        finally:
            document.close()

    repository.update_sheet_render_path(
        sheet_id,
        str(output_path.relative_to(settings.data_dir)),
        settings,
    )
    return output_path
