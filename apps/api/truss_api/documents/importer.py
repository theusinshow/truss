from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import fitz

from truss_api.core.settings import Settings


class InvalidPdfError(Exception):
    pass


@dataclass(frozen=True)
class PdfPageInfo:
    page_index: int
    sheet_number: int
    width_pt: float
    height_pt: float
    rotation: int
    label: str


@dataclass(frozen=True)
class PreparedPdf:
    original_filename: str
    stored_file_path: str
    content_hash: str
    mime_type: str
    file_size_bytes: int
    pages: list[PdfPageInfo]


def hash_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def safe_filename(filename: str) -> str:
    stem = Path(filename).name.strip() or "document.pdf"
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return sanitized or "document.pdf"


def inspect_pdf(content: bytes) -> list[PdfPageInfo]:
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as error:
        raise InvalidPdfError("File is not a readable PDF") from error

    try:
        if document.page_count < 1:
            raise InvalidPdfError("PDF has no pages")

        pages: list[PdfPageInfo] = []
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            rect = page.rect
            pages.append(
                PdfPageInfo(
                    page_index=page_index,
                    sheet_number=page_index + 1,
                    width_pt=float(rect.width),
                    height_pt=float(rect.height),
                    rotation=int(page.rotation),
                    label=f"Folha {page_index + 1:02d}",
                )
            )

        return pages
    finally:
        document.close()


def prepare_pdf_storage(
    *,
    content: bytes,
    filename: str,
    project_id: str,
    revision_id: str,
    settings: Settings,
    mime_type: str | None = None,
) -> PreparedPdf:
    pages = inspect_pdf(content)
    content_hash = hash_bytes(content)
    filename_safe = safe_filename(filename)
    storage_dir = settings.originals_dir / project_id / revision_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    stored_path = storage_dir / f"{content_hash[:16]}-{filename_safe}"
    if not stored_path.exists():
        stored_path.write_bytes(content)

    return PreparedPdf(
        original_filename=filename_safe,
        stored_file_path=str(stored_path.relative_to(settings.data_dir)),
        content_hash=content_hash,
        mime_type=mime_type or "application/pdf",
        file_size_bytes=len(content),
        pages=pages,
    )
