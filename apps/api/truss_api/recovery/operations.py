from hashlib import sha256
import json
from pathlib import Path

from truss_api.audit import repository as audit_repository
from truss_api.audit.orchestrator import AUDIT_PIPELINE_VERSION, run_deterministic_audit
from truss_api.core.settings import Settings
from truss_api.documents import repository as documents_repository
from truss_api.documents.importer import (
    InvalidPdfError,
    hash_bytes,
    inspect_pdf,
    prepare_pdf_storage,
    safe_filename,
)
from truss_api.recovery import repository
from truss_api.recovery.errors import TrussError
from truss_api.rules.loader import load_packs, load_packs_for_scopes
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.builder import build_sheet_map_for_document, build_sheet_map_for_sheet
from truss_api.sheetmap.elements.registry import build_revision_registry
from truss_api.sheetmap.snapshot import SHEET_MAP_PIPELINE
from truss_api.vision.orchestrator import VISION_PIPELINE_VERSION, run_visual_audit


IMPORT_PIPELINE_VERSION = "document-import-v0.2"


def operation_identity(kind: str, **components: object) -> str:
    material = json.dumps(
        {"kind": kind, **components},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _deterministic_identity_context(
    sheet_map: dict[str, object],
) -> tuple[str, bool]:
    technical_scopes = [
        str(item["technical_scope"])
        for item in sheet_map.get("technical_scopes", [])
        if isinstance(item, dict) and item.get("technical_scope")
    ]
    packs = load_packs_for_scopes(technical_scopes)
    if not packs:
        packs = load_packs(str(sheet_map["sheet_type"]))
    signature = "+".join(f"{pack.pack_id}@{pack.version}" for pack in packs)
    needs_registry = any(rule.target == "element" for pack in packs for rule in pack.rules)
    return signature, needs_registry


def _vision_identity_context(settings: Settings) -> dict[str, object]:
    return {
        "provider": settings.ai_provider,
        "model": settings.openai_model,
        "reasoning": settings.openai_reasoning_effort,
        "small_text_threshold_pt": settings.vision_small_text_threshold_pt,
        "max_candidates_per_sheet": settings.vision_max_candidates_per_sheet,
        "crop_padding_pt": settings.vision_crop_padding_pt,
        "render_scale": settings.vision_render_scale,
        "max_crop_pixels": settings.vision_max_crop_pixels,
        "image_detail": settings.vision_image_detail,
        "max_output_tokens": settings.vision_max_output_tokens,
        "min_confidence": settings.vision_min_confidence,
    }


def _public_invalid_pdf(error: InvalidPdfError) -> TrussError:
    code = "PDF_EMPTY" if "no pages" in str(error).lower() else "PDF_UNREADABLE"
    return TrussError(
        code=code,
        message=(
            "O PDF nao possui paginas utilizaveis."
            if code == "PDF_EMPTY"
            else "O arquivo nao pode ser aberto como PDF."
        ),
        action="Exporte o PDF novamente e importe a nova copia.",
        status_code=400,
    )


def _fail(operation_id: str, settings: Settings, error: Exception) -> None:
    if isinstance(error, TrussError):
        repository.fail_operation(
            operation_id,
            settings,
            code=error.public.code,
            message=error.public.message,
            retryable=error.public.retryable,
        )
        return
    repository.fail_operation(
        operation_id,
        settings,
        code="OPERATION_INTERRUPTED",
        message="O processamento foi interrompido antes da conclusao.",
        retryable=True,
    )


def import_document(
    *,
    project_id: str,
    revision_id: str,
    filename: str,
    content: bytes,
    mime_type: str,
    settings: Settings,
    build_sheet_maps: bool = True,
) -> dict[str, object]:
    try:
        pages = inspect_pdf(content)
    except InvalidPdfError as error:
        raise _public_invalid_pdf(error) from error

    content_hash = hash_bytes(content)
    identity = operation_identity(
        "document_import",
        revision_id=revision_id,
        content_hash=content_hash,
        pipeline=IMPORT_PIPELINE_VERSION,
    )
    operation = repository.create_operation(
        identity_key=identity,
        kind="document_import",
        project_id=project_id,
        revision_id=revision_id,
        input_hash=content_hash,
        pipeline_version=IMPORT_PIPELINE_VERSION,
        checkpoint="validated",
        payload={
            "original_filename": safe_filename(filename),
            "mime_type": mime_type,
            "build_sheet_maps": build_sheet_maps,
        },
        settings=settings,
    )
    if operation["status"] == "completed":
        raise documents_repository.DuplicateDocumentError(content_hash)
    repository.claim_operation(str(operation["id"]), settings)
    return _continue_document_import(
        str(operation["id"]),
        settings,
        content=content,
        pages=pages,
    )


def _continue_document_import(
    operation_id: str,
    settings: Settings,
    *,
    content: bytes | None = None,
    pages=None,
) -> dict[str, object]:
    operation = repository.get_operation(operation_id, settings)
    payload = dict(operation["payload"])
    try:
        stored_relative = payload.get("stored_file_path")
        if stored_relative:
            stored_path = settings.data_dir / str(stored_relative)
            if not stored_path.is_file():
                raise TrussError(
                    code="PDF_SOURCE_MISSING",
                    message="O PDF original da operacao nao foi encontrado.",
                    action="Importe o arquivo novamente ou restaure um backup valido.",
                    status_code=500,
                    retryable=False,
                    operation_id=operation_id,
                )
            stored_content = stored_path.read_bytes()
            if hash_bytes(stored_content) != str(operation["input_hash"]):
                raise TrussError(
                    code="ARTIFACT_CORRUPT",
                    message="O PDF original diverge do hash registrado.",
                    action="Restaure um backup valido em um novo diretorio.",
                    status_code=500,
                    operation_id=operation_id,
                )
            content = stored_content
        if content is None:
            raise TrussError(
                code="OPERATION_REQUIRES_FILE",
                message="A operacao parou antes de armazenar o PDF.",
                action="Selecione o mesmo PDF e importe novamente.",
                status_code=409,
                operation_id=operation_id,
            )

        if not stored_relative:
            resolved_pages = pages if pages is not None else inspect_pdf(content)
            prepared = prepare_pdf_storage(
                content=content,
                filename=str(payload.get("original_filename") or "document.pdf"),
                project_id=str(operation["project_id"]),
                revision_id=str(operation["revision_id"]),
                settings=settings,
                mime_type=str(payload.get("mime_type") or "application/pdf"),
                pages=resolved_pages,
                operation_id=operation_id,
            )
            operation = repository.save_checkpoint(
                operation_id,
                "original_stored",
                settings,
                payload={"stored_file_path": prepared.stored_file_path},
            )
        else:
            prepared = prepare_pdf_storage(
                content=content,
                filename=str(payload.get("original_filename") or Path(str(stored_relative)).name),
                project_id=str(operation["project_id"]),
                revision_id=str(operation["revision_id"]),
                settings=settings,
                mime_type=str(payload.get("mime_type") or "application/pdf"),
                operation_id=operation_id,
            )

        document = None
        if operation.get("document_id"):
            document = documents_repository.get_document(str(operation["document_id"]), settings)
        if document is None:
            document = documents_repository.get_document_by_revision_hash(
                str(operation["revision_id"]),
                str(operation["input_hash"]),
                settings,
            )
        if document is None:
            document = documents_repository.create_document_from_prepared_pdf(
                project_id=str(operation["project_id"]),
                revision_id=str(operation["revision_id"]),
                prepared_pdf=prepared,
                settings=settings,
            )
        operation = repository.save_checkpoint(
            operation_id,
            "document_registered",
            settings,
            document_id=str(document["id"]),
        )
        if bool(payload.get("build_sheet_maps", True)):
            build_sheet_map_for_document(str(document["id"]), settings)
            repository.save_checkpoint(operation_id, "sheet_maps_completed", settings)
        repository.complete_operation(
            operation_id,
            settings,
            payload={"result_document_id": str(document["id"])},
        )
        return documents_repository.get_document(str(document["id"]), settings)
    except InvalidPdfError as error:
        public = _public_invalid_pdf(error)
        _fail(operation_id, settings, public)
        raise public from error
    except Exception as error:
        _fail(operation_id, settings, error)
        if isinstance(error, TrussError):
            raise
        raise TrussError(
            code="OPERATION_INTERRUPTED",
            message="O processamento do documento foi interrompido.",
            action="Continue a operacao a partir do ultimo checkpoint seguro.",
            status_code=500,
            retryable=True,
            operation_id=operation_id,
        ) from error


def run_sheet_map_operation(sheet_id: str, settings: Settings) -> dict[str, object]:
    context = documents_repository.get_sheet_processing_context(sheet_id, settings)
    identity = operation_identity(
        "sheet_map_build",
        sheet_id=sheet_id,
        document_hash=context["document_hash"],
        page_index=context["page_index"],
        pipeline=SHEET_MAP_PIPELINE,
    )
    operation = repository.create_operation(
        identity_key=identity,
        kind="sheet_map_build",
        project_id=str(context["project_id"]),
        revision_id=str(context["revision_id"]),
        document_id=str(context["document_id"]),
        sheet_id=sheet_id,
        input_hash=str(context["document_hash"]),
        pipeline_version=SHEET_MAP_PIPELINE,
        checkpoint="ready",
        settings=settings,
    )
    result_id = dict(operation["payload"]).get("result_sheet_map_id")
    if operation["status"] == "completed" and result_id:
        return sheetmap_repository.get_sheet_map_by_id(str(result_id), settings)
    repository.claim_operation(str(operation["id"]), settings)
    try:
        result = build_sheet_map_for_sheet(sheet_id, settings)
        repository.complete_operation(
            str(operation["id"]),
            settings,
            payload={"result_sheet_map_id": str(result["id"])},
        )
        return result
    except Exception as error:
        code = error.public.code if isinstance(error, TrussError) else "SHEET_MAP_FAILED"
        message = (
            error.public.message
            if isinstance(error, TrussError)
            else "O Sheet Map da folha nao pode ser concluido."
        )
        repository.fail_operation(
            str(operation["id"]),
            settings,
            code=code,
            message=message,
            retryable=True,
        )
        raise


def _audit_operation(
    sheet_id: str,
    settings: Settings,
    *,
    vision: bool,
) -> dict[str, object]:
    sheet_map = sheetmap_repository.get_sheet_map(sheet_id, settings)
    kind = "vision_audit" if vision else "deterministic_audit"
    pipeline = VISION_PIPELINE_VERSION if vision else AUDIT_PIPELINE_VERSION
    registry_hash = ""
    rule_packs = ""
    if not vision:
        rule_packs, needs_registry = _deterministic_identity_context(sheet_map)
        if needs_registry:
            registry_hash = str(
                build_revision_registry(str(sheet_map["revision_id"]), settings).get(
                    "registry_hash"
                )
                or ""
            )
    identity = operation_identity(
        kind,
        sheet_id=sheet_id,
        sheet_map_id=str(sheet_map["id"]),
        pipeline=pipeline,
        registry_hash=registry_hash,
        rule_packs=rule_packs,
        vision_settings=_vision_identity_context(settings) if vision else None,
    )
    operation = repository.create_operation(
        identity_key=identity,
        kind=kind,
        sheet_id=sheet_id,
        project_id=str(sheet_map["project_id"]),
        revision_id=str(sheet_map["revision_id"]),
        input_hash=str(sheet_map.get("snapshot_hash") or sheet_map["id"]),
        pipeline_version=pipeline,
        checkpoint="ready",
        settings=settings,
    )
    result_id = dict(operation["payload"]).get("result_audit_run_id")
    if operation["status"] == "completed" and result_id:
        return audit_repository.get_audit_run(str(result_id), settings)
    if operation["status"] == "manual_retry_required" and vision:
        raise TrussError(
            code="EXTERNAL_RETRY_REQUIRES_CONFIRMATION",
            message="A analise visual anterior foi interrompida e pode ter gerado custo.",
            action="Inicie uma nova analise visual somente se aceitar outra chamada.",
            status_code=409,
            operation_id=str(operation["id"]),
        )
    repository.claim_operation(str(operation["id"]), settings)
    try:
        result = run_visual_audit(sheet_id, settings) if vision else run_deterministic_audit(sheet_id, settings)
        repository.complete_operation(
            str(operation["id"]),
            settings,
            payload={"result_audit_run_id": str(result["id"])},
        )
        return result
    except Exception as error:
        if isinstance(error, TrussError):
            code = error.public.code
            message = error.public.message
        else:
            code = "OPERATION_INTERRUPTED"
            message = "A auditoria foi interrompida antes da conclusao."
        repository.fail_operation(
            str(operation["id"]),
            settings,
            code=code,
            message=message,
            retryable=not vision,
            manual_retry=vision,
        )
        raise


def run_deterministic_audit_operation(sheet_id: str, settings: Settings) -> dict[str, object]:
    return _audit_operation(sheet_id, settings, vision=False)


def run_visual_audit_operation(sheet_id: str, settings: Settings) -> dict[str, object]:
    if not settings.vision_enabled:
        # Preserva o contrato: configuracao e validada antes da existencia da folha.
        return run_visual_audit(sheet_id, settings)
    return _audit_operation(sheet_id, settings, vision=True)


def resume_operation(operation_id: str, settings: Settings) -> dict[str, object]:
    operation = repository.get_operation(operation_id, settings)
    if operation["kind"] == "vision_audit":
        raise TrussError(
            code="EXTERNAL_RETRY_REQUIRES_CONFIRMATION",
            message="A analise visual nao pode ser retomada automaticamente.",
            action="Inicie uma nova analise visual se aceitar outra chamada.",
            status_code=409,
            operation_id=operation_id,
        )
    if operation["status"] == "completed":
        return operation
    repository.claim_operation(operation_id, settings)
    if operation["kind"] == "document_import":
        _continue_document_import(operation_id, settings)
    elif operation["kind"] == "sheet_map_build":
        result = build_sheet_map_for_sheet(str(operation["sheet_id"]), settings)
        repository.complete_operation(
            operation_id,
            settings,
            payload={"result_sheet_map_id": str(result["id"])},
        )
    elif operation["kind"] == "deterministic_audit":
        result = run_deterministic_audit(str(operation["sheet_id"]), settings)
        repository.complete_operation(
            operation_id,
            settings,
            payload={"result_audit_run_id": str(result["id"])},
        )
    else:
        raise TrussError(
            code="OPERATION_NOT_RESUMABLE",
            message="Esta operacao nao possui retomada unitaria.",
            action="Execute novamente a acao original.",
            status_code=409,
            operation_id=operation_id,
        )
    return repository.get_operation(operation_id, settings)
