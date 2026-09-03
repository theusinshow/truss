from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re

import fitz

from truss_api.core.settings import Settings
from truss_api.recovery.atomic import atomic_write_bytes
from truss_api.recovery.errors import TrussError


MAX_STORED_FILENAME_CHARS = 80


class InvalidPdfError(Exception):
    pass


@dataclass(frozen=True)
class PdfTextBlockInfo:
    block_index: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class PdfPageInfo:
    page_index: int
    sheet_number: int
    width_pt: float
    height_pt: float
    rotation: int
    label: str
    text_blocks: list[PdfTextBlockInfo]


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


def storage_filename(content_hash: str, filename: str) -> str:
    """Mantem o hash inteiro e limita somente o nome fisico content-addressed."""
    safe = safe_filename(filename)
    suffix = Path(safe).suffix
    prefix = f"{content_hash}-"
    available = MAX_STORED_FILENAME_CHARS - len(prefix) - len(suffix)
    if available <= 0:
        return f"{content_hash}{suffix}"[:MAX_STORED_FILENAME_CHARS]
    stem = Path(safe).stem[:available].rstrip(".-") or "document"
    return f"{prefix}{stem}{suffix}"


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
            text_blocks: list[PdfTextBlockInfo] = []

            for block_index, block in enumerate(page.get_text("blocks")):
                x0, y0, x1, y1, text, *_ = block
                normalized_text = str(text).strip()
                if not normalized_text:
                    continue

                text_blocks.append(
                    PdfTextBlockInfo(
                        block_index=block_index,
                        text=normalized_text,
                        x0=float(x0),
                        y0=float(y0),
                        x1=float(x1),
                        y1=float(y1),
                    )
                )

            pages.append(
                PdfPageInfo(
                    page_index=page_index,
                    sheet_number=page_index + 1,
                    width_pt=float(rect.width),
                    height_pt=float(rect.height),
                    rotation=int(page.rotation),
                    label=f"Folha {page_index + 1:02d}",
                    text_blocks=text_blocks,
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
    pages: list[PdfPageInfo] | None = None,
    operation_id: str | None = None,
) -> PreparedPdf:
    resolved_pages = pages if pages is not None else inspect_pdf(content)
    content_hash = hash_bytes(content)
    filename_safe = safe_filename(filename)
    storage_dir = settings.originals_dir / project_id / revision_id
    storage_dir.mkdir(parents=True, exist_ok=True)

    stored_path = storage_dir / storage_filename(content_hash, filename_safe)
    if stored_path.exists():
        if hash_bytes(stored_path.read_bytes()) != content_hash:
            raise TrussError(
                code="ARTIFACT_CORRUPT",
                message="O destino do PDF original possui conteudo divergente.",
                action="Execute o diagnostico local e restaure um backup valido.",
                status_code=500,
                operation_id=operation_id,
            )
    else:
        atomic_write_bytes(stored_path, content, operation_id=operation_id)

    return PreparedPdf(
        original_filename=filename_safe,
        stored_file_path=str(stored_path.relative_to(settings.data_dir)),
        content_hash=content_hash,
        mime_type=mime_type or "application/pdf",
        file_size_bytes=len(content),
        pages=resolved_pages,
    )
