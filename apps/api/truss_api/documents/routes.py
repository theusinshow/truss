from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from truss_api.core.settings import Settings, get_settings
from truss_api.documents import repository
from truss_api.documents.models import Document, DocumentDetail, TextBlock
from truss_api.documents.rendering import RenderError, render_sheet_png
from truss_api.recovery.errors import TrussError
from truss_api.recovery.operations import import_document


router = APIRouter(tags=["documents"])


@router.get(
    "/projects/{project_id}/revisions/{revision_id}/documents",
    response_model=list[Document],
)
def list_revision_documents(
    project_id: str,
    revision_id: str,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    try:
        repository.ensure_revision_belongs_to_project(project_id, revision_id, settings)
    except repository.RevisionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found") from error

    return repository.list_documents_for_revision(revision_id, settings)


@router.post(
    "/projects/{project_id}/revisions/{revision_id}/documents",
    response_model=DocumentDetail,
    status_code=status.HTTP_201_CREATED,
)
async def import_revision_document(
    project_id: str,
    revision_id: str,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if file.content_type not in {None, "application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PDF files are supported")

    content = await file.read()
    if not content:
        raise TrussError(
            code="PDF_EMPTY",
            message="O arquivo enviado esta vazio.",
            action="Selecione um PDF valido e tente novamente.",
            status_code=400,
        )

    try:
        repository.ensure_revision_belongs_to_project(project_id, revision_id, settings)
        return import_document(
            project_id=project_id,
            revision_id=revision_id,
            filename=file.filename or "document.pdf",
            content=content,
            mime_type=file.content_type or "application/pdf",
            settings=settings,
        )
    except repository.RevisionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found") from error
    except repository.DuplicateDocumentError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This PDF was already imported for the revision",
        ) from error


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.get_document(document_id, settings)
    except repository.DocumentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found") from error


@router.get("/sheets/{sheet_id}/image", response_class=FileResponse)
def get_sheet_image(
    sheet_id: str,
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    try:
        image_path = render_sheet_png(sheet_id, settings)
    except repository.SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error
    except RenderError as error:
        raise TrussError(
            code="RENDER_FAILED",
            message="A pagina nao pode ser renderizada.",
            action="Execute o diagnostico do PDF e tente reconstruir o render.",
            status_code=500,
            retryable=True,
        ) from error

    return FileResponse(image_path, media_type="image/png")


@router.get("/sheets/{sheet_id}/text-blocks", response_model=list[TextBlock])
def list_sheet_text_blocks(
    sheet_id: str,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    try:
        return repository.list_text_blocks_for_sheet(sheet_id, settings)
    except repository.SheetNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found") from error
