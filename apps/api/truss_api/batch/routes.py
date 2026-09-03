from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status

from truss_api.batch.models import BatchCapabilities, BatchItem, BatchRunCreate, BatchRunSummary
from truss_api.batch import repository
from truss_api.ai.provider import get_ai_provider_status
from truss_api.core.settings import Settings, get_settings
from truss_api.documents import repository as documents_repository
from truss_api.documents.models import DocumentDetail
from truss_api.recovery.errors import TrussError
from truss_api.recovery.operations import import_document


router = APIRouter(tags=["batch"])


def _config(
    *,
    include_visual: bool,
    ai_review: bool,
    settings: Settings,
) -> dict[str, object]:
    return {
        "include_visual": include_visual,
        "ai_review": ai_review,
        "worker_concurrency": 1,
        "visual_concurrency": 1,
        "vision_budget_usd_per_revision": settings.vision_budget_usd_per_revision,
        "vision_max_calls_per_revision": settings.vision_max_calls_per_revision,
        "vision_max_candidates_per_sheet": settings.vision_max_candidates_per_sheet,
        "vision_cost_reserve_usd_per_call": settings.vision_cost_reserve_usd_per_call,
        "vision_max_output_tokens": settings.vision_max_output_tokens,
        "openai_reasoning_effort": settings.openai_reasoning_effort,
        "provider": settings.ai_provider,
        "model": settings.openai_model if include_visual or ai_review else None,
        "ai_review_global_max_pixels": settings.ai_review_global_max_pixels,
        "ai_review_tile_max_pixels": settings.ai_review_tile_max_pixels,
        "ai_review_tile_overlap_ratio": settings.ai_review_tile_overlap_ratio,
    }


def _validate_visual_request(include_visual: bool, settings: Settings) -> None:
    if include_visual and not settings.vision_enabled:
        raise TrussError(
            code="VISION_DISABLED",
            message="A analise visual esta desativada nesta instalacao.",
            action="Ative a visao e confirme os limites antes de criar um lote visual.",
            status_code=409,
        )


def _validate_ai_review_request(ai_review: bool, settings: Settings) -> None:
    if not ai_review:
        return
    status = get_ai_provider_status(settings)
    if not settings.vision_enabled:
        raise TrussError(
            code="AI_REVIEW_DISABLED",
            message="A revisao por IA esta desativada nesta instalacao.",
            action="Ative TRUSS_VISION_ENABLED e confirme o teto de custo.",
            status_code=409,
        )
    if status.resolved_provider != "openai" or not status.external_calls_enabled:
        raise TrussError(
            code="AI_PROVIDER_UNAVAILABLE",
            message="A revisao por IA exige uma chave OpenAI ativa.",
            action="Configure TRUSS_AI_PROVIDER=openai ou auto com uma chave valida.",
            status_code=409,
        )


@router.get("/batch-capabilities", response_model=BatchCapabilities)
def batch_capabilities(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    status = get_ai_provider_status(settings)
    return {
        "visual_enabled": settings.vision_enabled,
        "ai_review_available": (
            settings.vision_enabled
            and status.resolved_provider == "openai"
            and status.external_calls_enabled
        ),
        "external_calls_enabled": status.external_calls_enabled,
        "provider": status.resolved_provider,
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
    ai_review: bool = Form(default=False),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if include_visual and ai_review:
        raise TrussError(
            code="BATCH_MODE_CONFLICT",
            message="Escolha somente um modo de analise externa.",
            action="Use a revisao por IA para o fluxo principal.",
            status_code=400,
        )
    _validate_visual_request(include_visual, settings)
    _validate_ai_review_request(ai_review, settings)
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
    mode = "with_visual" if include_visual or ai_review else "local_deterministic"
    batch = repository.create_batch_run(
        project_id=project_id,
        revision_id=revision_id,
        mode=mode,
        config=_config(
            include_visual=include_visual,
            ai_review=ai_review,
            settings=settings,
        ),
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
    if request.include_visual and request.ai_review:
        raise TrussError(
            code="BATCH_MODE_CONFLICT",
            message="Escolha somente um modo de analise externa.",
            action="Use a revisao por IA para o fluxo principal.",
            status_code=400,
        )
    _validate_visual_request(request.include_visual, settings)
    _validate_ai_review_request(request.ai_review, settings)
    try:
        documents_repository.ensure_revision_belongs_to_project(project_id, revision_id, settings)
    except documents_repository.RevisionNotFoundError as error:
        raise HTTPException(status_code=404, detail="Revision not found") from error
    mode = "with_visual" if request.include_visual or request.ai_review else "local_deterministic"
    return repository.create_batch_run(
        project_id=project_id,
        revision_id=revision_id,
        mode=mode,
        config=_config(
            include_visual=request.include_visual,
            ai_review=request.ai_review,
            settings=settings,
        ),
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
