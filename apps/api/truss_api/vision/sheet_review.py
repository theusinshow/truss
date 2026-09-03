from hashlib import sha256
import json
from typing import Any

import fitz

from truss_api.ai.provider import AIProvider, AIProviderUnavailableError, build_ai_provider
from truss_api.audit import repository as audit_repository
from truss_api.core.settings import Settings
from truss_api.documents import repository as documents_repository
from truss_api.recovery.errors import TrussError
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.vision import repository as vision_repository
from truss_api.vision.models import (
    SheetReviewFinding,
    SheetReviewImage,
    SheetReviewInput,
    SheetReviewProviderResponse,
)


AI_REVIEW_PIPELINE_VERSION = "ai-sheet-review-v0.1"
AI_REVIEW_PROMPT_VERSION = "structural-graphic-review-v1"
AI_REVIEW_RULE_ID = "ai.sheet_review"
AI_REVIEW_RULE_VERSION = "1.0.0"


def _render_image(
    page: fitz.Page,
    bbox: fitz.Rect,
    *,
    max_pixels: int,
    role: str,
    detail: str,
) -> SheetReviewImage:
    scale = min(float(max_pixels) / max(float(bbox.width), float(bbox.height)), 2.0)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=bbox, alpha=False)
    image_bytes = pixmap.tobytes("png")
    return SheetReviewImage(
        role="global" if role == "global" else "tile",
        image_bytes=image_bytes,
        image_hash=sha256(image_bytes).hexdigest(),
        bbox_pt=(float(bbox.x0), float(bbox.y0), float(bbox.x1), float(bbox.y1)),
        width_px=pixmap.width,
        height_px=pixmap.height,
        detail="low" if detail == "low" else "high",
    )


def render_sheet_review_images(sheet_id: str, settings: Settings) -> tuple[SheetReviewImage, ...]:
    context = documents_repository.get_sheet_render_context(sheet_id, settings)
    source_path = settings.data_dir / str(context["stored_file_path"])
    document = fitz.open(source_path)
    try:
        page = document.load_page(int(context["page_index"]))
        page_rect = page.rect
        images = [
            _render_image(
                page,
                page_rect,
                max_pixels=settings.ai_review_global_max_pixels,
                role="global",
                detail="low",
            )
        ]
        overlap_x = page_rect.width * settings.ai_review_tile_overlap_ratio
        overlap_y = page_rect.height * settings.ai_review_tile_overlap_ratio
        half_width = page_rect.width / 2
        half_height = page_rect.height / 2
        for row in range(2):
            for column in range(2):
                x0 = max(page_rect.x0, page_rect.x0 + column * half_width - overlap_x)
                y0 = max(page_rect.y0, page_rect.y0 + row * half_height - overlap_y)
                x1 = min(page_rect.x1, page_rect.x0 + (column + 1) * half_width + overlap_x)
                y1 = min(page_rect.y1, page_rect.y0 + (row + 1) * half_height + overlap_y)
                images.append(
                    _render_image(
                        page,
                        fitz.Rect(x0, y0, x1, y1),
                        max_pixels=settings.ai_review_tile_max_pixels,
                        role="tile",
                        detail="high",
                    )
                )
        return tuple(images)
    finally:
        document.close()


def _compact_context(
    sheet_context: dict[str, object],
    sheet_map: dict[str, object],
    text_blocks: list[dict[str, object]],
) -> dict[str, Any]:
    views: list[dict[str, object]] = []
    for view in sheet_map.get("views", []):
        if not isinstance(view, dict):
            continue
        views.append(
            {
                key: view.get(key)
                for key in (
                    "id",
                    "title",
                    "view_type",
                    "technical_scope",
                    "scale_raw",
                    "x0",
                    "y0",
                    "x1",
                    "y1",
                )
            }
        )

    selected_text: list[dict[str, object]] = []
    used_chars = 0
    for block in text_blocks:
        text = " ".join(str(block.get("text") or "").split())
        if not text:
            continue
        if used_chars + len(text) > 12000 or len(selected_text) >= 180:
            break
        used_chars += len(text)
        selected_text.append(
            {
                "text": text[:500],
                "bbox_pt": [
                    round(float(block.get("x0") or 0), 2),
                    round(float(block.get("y0") or 0), 2),
                    round(float(block.get("x1") or 0), 2),
                    round(float(block.get("y1") or 0), 2),
                ],
            }
        )

    return {
        "sheet": {
            "id": sheet_context["sheet_id"],
            "label": sheet_context["label"],
            "width_pt": sheet_context["width_pt"],
            "height_pt": sheet_context["height_pt"],
            "sheet_code": sheet_map.get("sheet_code"),
            "sheet_code_raw": sheet_map.get("sheet_code_raw"),
            "paper_format": sheet_map.get("paper_format"),
            "sheet_type": sheet_map.get("sheet_type"),
        },
        "technical_scopes": sheet_map.get("technical_scopes", []),
        "views": views[:40],
        "native_text": selected_text,
        "native_text_truncated": len(selected_text) < len(text_blocks),
        "coordinate_contract": "bbox normalized 0..1000 relative to the full sheet",
    }


def _cache_key(
    *,
    sheet_id: str,
    document_hash: str,
    page_index: int,
    sheet_map: dict[str, object],
    provider: AIProvider,
    settings: Settings,
) -> str:
    material = json.dumps(
        {
            "document_hash": document_hash,
            "global_max_pixels": settings.ai_review_global_max_pixels,
            "model": provider.model,
            "output_tokens": settings.vision_max_output_tokens,
            "page_index": page_index,
            "pipeline": AI_REVIEW_PIPELINE_VERSION,
            "prompt": AI_REVIEW_PROMPT_VERSION,
            "reasoning": settings.openai_reasoning_effort,
            "sheet_id": sheet_id,
            "sheet_map_snapshot": sheet_map.get("snapshot_hash"),
            "tile_max_pixels": settings.ai_review_tile_max_pixels,
            "tile_overlap": settings.ai_review_tile_overlap_ratio,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"audit:ai-review:{sha256(material.encode('utf-8')).hexdigest()}"


def _view_for_bbox(
    bbox: dict[str, float],
    sheet_map: dict[str, object],
) -> tuple[str | None, str | None]:
    center_x = (bbox["x0"] + bbox["x1"]) / 2
    center_y = (bbox["y0"] + bbox["y1"]) / 2
    matches = []
    for view in sheet_map.get("views", []):
        if not isinstance(view, dict):
            continue
        if (
            float(view.get("x0") or 0) <= center_x <= float(view.get("x1") or 0)
            and float(view.get("y0") or 0) <= center_y <= float(view.get("y1") or 0)
        ):
            matches.append(view)
    if not matches:
        return None, None
    selected = min(
        matches,
        key=lambda item: (float(item.get("x1") or 0) - float(item.get("x0") or 0))
        * (float(item.get("y1") or 0) - float(item.get("y0") or 0)),
    )
    return str(selected.get("id") or "") or None, str(selected.get("technical_scope") or "") or None


def _finding_payload(
    finding: SheetReviewFinding,
    *,
    width_pt: float,
    height_pt: float,
    sheet_map: dict[str, object],
    response: SheetReviewProviderResponse,
) -> dict[str, object] | None:
    normalized = finding.bbox
    if normalized.x1 <= normalized.x0 or normalized.y1 <= normalized.y0:
        return None
    bbox = {
        "x0": normalized.x0 / 1000 * width_pt,
        "y0": normalized.y0 / 1000 * height_pt,
        "x1": normalized.x1 / 1000 * width_pt,
        "y1": normalized.y1 / 1000 * height_pt,
    }
    area_ratio = ((bbox["x1"] - bbox["x0"]) * (bbox["y1"] - bbox["y0"])) / (
        width_pt * height_pt
    )
    view_id, technical_scope = _view_for_bbox(bbox, sheet_map)
    fingerprint = json.dumps(
        {
            "bbox": [round(value, 1) for value in bbox.values()],
            "category": finding.category,
            "description": " ".join(finding.description.lower().split()),
            "type": finding.type,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    evidence = [
        f"escopo: {finding.scope}",
        f"bbox normalizada: {normalized.x0:.1f},{normalized.y0:.1f} -> {normalized.x1:.1f},{normalized.y1:.1f}",
        f"area da prancha: {area_ratio * 100:.2f}%",
        (
            f"ia: provider={response.provider} modelo={response.model} "
            f"prompt={AI_REVIEW_PROMPT_VERSION}"
        ),
        *finding.evidence,
    ]
    return {
        "category": finding.category,
        "type": finding.type,
        "description": finding.description,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "bbox": bbox,
        "evidence": evidence[:10],
        "rule_id": AI_REVIEW_RULE_ID,
        "rule_version": AI_REVIEW_RULE_VERSION,
        "rule_scope": finding.scope,
        "technical_scope": technical_scope,
        "view_id": view_id,
        "source_layer": "ai_review",
        "dedupe_key": sha256(fingerprint.encode("utf-8")).hexdigest()[:24],
    }


def run_ai_sheet_review(
    sheet_id: str,
    settings: Settings,
    *,
    provider: AIProvider | None = None,
) -> dict[str, object]:
    if not settings.vision_enabled:
        raise TrussError(
            code="AI_REVIEW_DISABLED",
            message="A revisao por IA esta desativada nesta instalacao.",
            action="Ative TRUSS_VISION_ENABLED e confirme o teto de custo.",
            status_code=409,
        )
    if settings.vision_budget_usd_per_revision <= 0:
        raise TrussError(
            code="AI_BUDGET_DISABLED",
            message="O teto de custo da revisao por IA precisa ser maior que zero.",
            action="Configure um teto de custo por revisao.",
            status_code=409,
        )

    sheet_context = audit_repository.get_sheet_context(sheet_id, settings)
    processing_context = documents_repository.get_sheet_processing_context(sheet_id, settings)
    sheet_map = sheetmap_repository.get_sheet_map(sheet_id, settings)
    resolved_provider = provider or build_ai_provider(settings)
    if provider is None and resolved_provider.provider != "openai":
        raise AIProviderUnavailableError(
            "Configured provider does not support AI-first sheet review.",
            public_message="A revisao da prancha exige provider OpenAI configurado.",
            provider_code="sheet_review_provider_unavailable",
        )

    cache_key = _cache_key(
        sheet_id=sheet_id,
        document_hash=str(processing_context["document_hash"]),
        page_index=int(processing_context["page_index"]),
        sheet_map=sheet_map,
        provider=resolved_provider,
        settings=settings,
    )
    cached = audit_repository.get_cached_audit_run(cache_key, settings)
    if cached is not None:
        return cached

    calls, spent = vision_repository.revision_external_usage(
        str(sheet_context["revision_id"]), settings
    )
    if (
        calls >= settings.vision_max_calls_per_revision
        or spent + settings.vision_cost_reserve_usd_per_call
        > settings.vision_budget_usd_per_revision
    ):
        raise TrussError(
            code="AI_BUDGET_EXHAUSTED",
            message="O teto de custo da revisao por IA foi atingido antes desta prancha.",
            action="Revise o uso registrado antes de autorizar um novo lote.",
            status_code=409,
        )

    images = render_sheet_review_images(sheet_id, settings)
    context = _compact_context(
        sheet_context,
        sheet_map,
        audit_repository.list_text_blocks(sheet_id, settings),
    )
    try:
        response = resolved_provider.analyze_sheet(
            review=SheetReviewInput(
                sheet_id=sheet_id,
                width_pt=float(sheet_context["width_pt"]),
                height_pt=float(sheet_context["height_pt"]),
                images=images,
                context=context,
            )
        )
    except AIProviderUnavailableError as error:
        vision_repository.record_external_usage_values(
            provider=error.provider or resolved_provider.provider,
            model=error.model or resolved_provider.model,
            input_tokens=error.input_tokens,
            output_tokens=error.output_tokens,
            estimated_cost_usd=(
                error.estimated_cost_usd
                if error.estimated_cost_usd is not None and error.estimated_cost_usd > 0
                else settings.vision_cost_reserve_usd_per_call
            ),
            operation="ai.sheet_review",
            project_id=str(sheet_context["project_id"]),
            revision_id=str(sheet_context["revision_id"]),
            sheet_id=sheet_id,
            settings=settings,
        )
        raise
    vision_repository.record_external_usage(
        response,
        operation="ai.sheet_review",
        project_id=str(sheet_context["project_id"]),
        revision_id=str(sheet_context["revision_id"]),
        sheet_id=sheet_id,
        settings=settings,
    )

    findings = [
        payload
        for candidate in response.analysis.findings
        if (
            payload := _finding_payload(
                candidate,
                width_pt=float(sheet_context["width_pt"]),
                height_pt=float(sheet_context["height_pt"]),
                sheet_map=sheet_map,
                response=response,
            )
        )
        is not None
    ]
    scopes = [
        str(item.get("technical_scope"))
        for item in sheet_map.get("technical_scopes", [])
        if isinstance(item, dict) and item.get("technical_scope")
    ]
    unknown = sum(item["type"] == "unverifiable" for item in findings)
    return audit_repository.create_audit_run(
        sheet_context=sheet_context,
        findings=findings,
        settings=settings,
        cache_key=cache_key,
        sheet_map_id=str(sheet_map["id"]),
        rule_pack_version=(
            f"{AI_REVIEW_RULE_ID}@{AI_REVIEW_RULE_VERSION}+"
            f"{AI_REVIEW_PROMPT_VERSION}+{response.model}"
        ),
        coverage={
            "evaluated": 1,
            "passed": 1 if not findings else 0,
            "failed": len(findings) - unknown,
            "unknown": unknown,
            "not_applicable": 0,
            "skipped": 0,
            "technical_scopes": sorted(set(scopes)),
            "covered_scopes": sorted(set(scopes)),
            "uncovered_scopes": [],
        },
        mode="ai_review",
        pipeline_version=AI_REVIEW_PIPELINE_VERSION,
        summary=(
            f"{response.analysis.summary} {len(findings)} achado(s) localizado(s) pela IA."
        ).strip(),
    )
