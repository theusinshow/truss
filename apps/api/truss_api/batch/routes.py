from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from truss_api.batch.models import BatchCapabilities, BatchItem, BatchRunCreate, BatchRunSummary
from truss_api.batch import repository
from truss_api.core.settings import Settings, get_settings
from truss_api.documents import repository as documents_repository
from truss_api.documents.models import DocumentDetail
from truss_api.recovery.errors import TrussError
from truss_api.recovery.operations import import_document


router = APIRouter(tags=["batch"])


def _config(include_visual: bool, settings: Settings) -> dict[str, object]:
    return {
        "include_visual": include_visual,
        "worker_concurrency": 1,
        "visual_concurrency": 1,
        "vision_budget_usd_per_revision": settings.vision_budget_usd_per_revision,
        "vision_max_calls_per_revision": settings.vision_max_calls_per_revision,
        "vision_max_candidates_per_sheet": settings.vision_max_candidates_per_sheet,
        "provider": settings.ai_provider,
        "model": settings.openai_model if include_visual else None,
    }


def _validate_visual_request(include_visual: bool, settings: Settings) -> None:
    if include_visual and not settings.vision_enabled:
        raise TrussError(
            code="VISION_DISABLED",
            message="A analise visual esta desativada nesta instalacao.",
            action="Ative a visao e confirme os limites antes de criar um lote visual.",
            status_code=409,
        )


@router.get("/batch-capabilities", response_model=BatchCapabilities)
def batch_capabilities(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "visual_enabled": settings.vision_enabled,
        "provider": settings.ai_provider,
        "model": settings.openai_model,
        "vision_budget_usd_per_revision": settings.vision_budget_usd_per_revision,
        "vision_max_calls_per_revision": settings.vision_max_calls_per_revision,
        "vision_max_candidates_per_sheet": settings.vision_max_candidates_per_sheet,
        "worker_concurrency": 1,
        "visual_concurrency": 1,
    }


@router.post(
    "/projects/{project_id}/revisions/{revision_id}/batch-imports",
    status_code=status.HTTP_202_ACCEPTED,
)
async def batch_import(
    project_id: str,
    revision_id: str,
    file: UploadFile = File(...),
    include_visual: bool = Form(default=False),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    _validate_visual_request(include_visual, settings)
    if file.content_type not in {None, "application/pdf", "application/octet-stream"}:
        raise TrussError(
            code="PDF_UNREADABLE",
            message="Somente arquivos PDF podem iniciar um lote.",
            action="Selecione um PDF estrutural valido.",
            status_code=415,
        )
    content = await file.read()
    if not content:
        raise TrussError(
            code="PDF_EMPTY",
            message="O arquivo enviado esta vazio.",
            action="Selecione um PDF valido e tente novamente.",
            status_code=400,
        )
    if repository.list_revision_batch_runs(revision_id, settings, active_only=True):
        raise TrussError(
            code="BATCH_ALREADY_ACTIVE",
            message="Esta revisao ja possui um lote ativo.",
            action="Acompanhe ou encerre o lote atual antes de importar outro PDF.",
            status_code=409,
        )
    try:
        documents_repository.ensure_revision_belongs_to_project(project_id, revision_id, settings)
        document = import_document(
            project_id=project_id,
            revision_id=revision_id,
            filename=file.filename or "document.pdf",
            content=content,
            mime_type=file.content_type or "application/pdf",
            settings=settings,
            build_sheet_maps=False,
        )
    except documents_repository.RevisionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Revision not found") from error
    except documents_repository.DuplicateDocumentError as error:
        raise HTTPException(
            status_code=409,
            detail="This PDF was already imported for the revision",
        ) from error
    mode = "with_visual" if include_visual else "local_deterministic"
    batch = repository.create_batch_run(
        project_id=project_id,
        revision_id=revision_id,
        mode=mode,
        config=_config(include_visual, settings),
        settings=settings,
    )
    return {"document": DocumentDetail.model_validate(document), "batch": batch}


@router.post(
    "/projects/{project_id}/revisions/{revision_id}/batch-runs",
    response_model=BatchRunSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_batch_run(
    project_id: str,
    revision_id: str,
    request: BatchRunCreate,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    _validate_visual_request(request.include_visual, settings)
    try:
        documents_repository.ensure_revision_belongs_to_project(project_id, revision_id, settings)
    except documents_repository.RevisionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Revision not found") from error
    mode = "with_visual" if request.include_visual else "local_deterministic"
    return repository.create_batch_run(
        project_id=project_id,
        revision_id=revision_id,
        mode=mode,
        config=_config(request.include_visual, settings),
        settings=settings,
    )


@router.get("/revisions/{revision_id}/batch-runs", response_model=list[BatchRunSummary])
def list_batch_runs(
    revision_id: str,
    active: bool = Query(default=False),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_revision_batch_runs(revision_id, settings, active_only=active)


@router.get("/batch-runs/{batch_run_id}", response_model=BatchRunSummary)
def get_batch_run(
    batch_run_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return repository.get_batch_run(batch_run_id, settings)


@router.get("/batch-runs/{batch_run_id}/items", response_model=list[BatchItem])
def list_batch_items(
    batch_run_id: str,
    item_status: str | None = Query(default=None, alias="status"),
    phase: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    return repository.list_batch_items(
        batch_run_id,
        settings,
        status=item_status,
        phase=phase,
        limit=limit,
        offset=offset,
    )


@router.post("/batch-runs/{batch_run_id}/cancel", response_model=BatchRunSummary)
def cancel_batch_run(
    batch_run_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return repository.request_cancel(batch_run_id, settings)


@router.post("/batch-runs/{batch_run_id}/resume", response_model=BatchRunSummary)
def resume_batch_run(
    batch_run_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return repository.retry_failures(batch_run_id, settings)


@router.post("/batch-runs/{batch_run_id}/retry-failures", response_model=BatchRunSummary)
def retry_batch_failures(
    batch_run_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return repository.retry_failures(batch_run_id, settings)
