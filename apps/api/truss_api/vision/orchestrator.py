from hashlib import sha256
import json

from truss_api.ai.provider import AIProvider, AIProviderUnavailableError, build_ai_provider
from truss_api.audit import repository as audit_repository
from truss_api.core.settings import Settings
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.vision.candidates import detect_legibility_candidates, read_sheet_extraction
from truss_api.vision.crops import render_vision_crop
from truss_api.vision.models import VisionCandidate, VisionCropInput, VisionProviderResponse
from truss_api.vision import repository


VISION_PIPELINE_VERSION = "vision-v0.1"
VISION_PROMPT_VERSION = "legibility-v1"
VISION_RULE_ID = "vision.text_legibility"
VISION_RULE_VERSION = "1.0.0"


class VisionDisabledError(Exception):
    pass


def _vision_cache_key(
    *,
    crop_hash: str,
    candidate: VisionCandidate,
    provider: AIProvider,
    settings: Settings,
) -> str:
    material = json.dumps(
        {
            "candidate_id": candidate.candidate_id,
            "crop_hash": crop_hash,
            "detail": settings.vision_image_detail,
            "max_output_tokens": settings.vision_max_output_tokens,
            "model": provider.model,
            "pipeline": VISION_PIPELINE_VERSION,
            "prompt": VISION_PROMPT_VERSION,
            "reasoning": settings.openai_reasoning_effort,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vision:{sha256(material.encode('utf-8')).hexdigest()}"


def _run_cache_key(
    *,
    snapshot_hash: str,
    candidates: list[VisionCandidate],
    model: str,
    settings: Settings,
) -> str:
    material = json.dumps(
        {
            "candidates": [candidate.candidate_id for candidate in candidates],
            "crop_padding_pt": settings.vision_crop_padding_pt,
            "detail": settings.vision_image_detail,
            "max_crop_pixels": settings.vision_max_crop_pixels,
            "min_confidence": settings.vision_min_confidence,
            "model": model,
            "max_output_tokens": settings.vision_max_output_tokens,
            "pipeline": VISION_PIPELINE_VERSION,
            "prompt": VISION_PROMPT_VERSION,
            "reasoning": settings.openai_reasoning_effort,
            "render_scale": settings.vision_render_scale,
            "snapshot_hash": snapshot_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"audit:vision:{sha256(material.encode('utf-8')).hexdigest()[:24]}"


def _dedupe_key(candidate: VisionCandidate) -> str:
    material = f"{VISION_RULE_ID}|{candidate.candidate_id}"
    return sha256(material.encode("utf-8")).hexdigest()[:24]


def _finding(
    candidate: VisionCandidate,
    response: VisionProviderResponse,
    *,
    crop_hash: str,
    crop_bbox_pt: tuple[float, float, float, float],
) -> dict[str, object]:
    analysis = response.analysis
    bbox = candidate.bbox_pt
    samples = " | ".join(candidate.text_samples)[:300]
    evidence = [
        f"candidato: {candidate.candidate_id}",
        f"tipo candidato: {candidate.kind}",
        f"textos: {samples or 'indisponivel'}",
        f"bbox fonte: {bbox[0]:.3f},{bbox[1]:.3f} -> {bbox[2]:.3f},{bbox[3]:.3f} pt",
        (
            f"crop: hash={crop_hash[:20]} bbox={crop_bbox_pt[0]:.3f},{crop_bbox_pt[1]:.3f} "
            f"-> {crop_bbox_pt[2]:.3f},{crop_bbox_pt[3]:.3f} pt"
        ),
        f"visao: provider={response.provider} modelo={response.model} prompt={VISION_PROMPT_VERSION}",
        *analysis.evidence[:4],
    ]
    return {
        "category": "legibility",
        "type": "attention",
        "description": analysis.description,
        "severity": "medium",
        "confidence": analysis.confidence,
        "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
        "evidence": evidence[:10],
        "rule_id": VISION_RULE_ID,
        "rule_version": VISION_RULE_VERSION,
        "rule_scope": "general",
        "technical_scope": candidate.technical_scope,
        "view_id": candidate.view_id,
        "source_layer": "vision",
        "dedupe_key": _dedupe_key(candidate),
    }


def _coverage(
    *,
    evaluated: int,
    passed: int,
    failed: int,
    unknown: int,
    skipped: int,
    scopes: list[str],
) -> dict[str, object]:
    return {
        "evaluated": evaluated,
        "passed": passed,
        "failed": failed,
        "unknown": unknown,
        "not_applicable": 0,
        "skipped": skipped,
        "technical_scopes": sorted(set(scopes)),
        "covered_scopes": sorted(set(scopes)) if evaluated else [],
        "uncovered_scopes": [] if evaluated else sorted(set(scopes)),
    }


def run_visual_audit(
    sheet_id: str,
    settings: Settings,
    *,
    provider: AIProvider | None = None,
) -> dict[str, object]:
    if not settings.vision_enabled:
        raise VisionDisabledError(
            "Analise visual desabilitada. Configure TRUSS_VISION_ENABLED=true e um teto de custo."
        )
    if settings.vision_budget_usd_per_revision <= 0:
        raise VisionDisabledError("O teto de custo da analise visual precisa ser maior que zero.")

    sheet_context = audit_repository.get_sheet_context(sheet_id, settings)
    sheet_map = sheetmap_repository.get_sheet_map(sheet_id, settings)
    extraction = read_sheet_extraction(sheet_id, settings)
    candidates = detect_legibility_candidates(
        extraction,
        sheet_map,
        small_text_threshold_pt=settings.vision_small_text_threshold_pt,
        max_candidates=settings.vision_max_candidates_per_sheet,
    )
    scopes = [
        str(item["technical_scope"])
        for item in sheet_map.get("technical_scopes", [])
        if isinstance(item, dict) and item.get("technical_scope")
    ]

    if not candidates:
        return audit_repository.create_audit_run(
            sheet_context=sheet_context,
            findings=[],
            settings=settings,
            sheet_map_id=str(sheet_map["id"]),
            rule_pack_version=f"{VISION_RULE_ID}@{VISION_RULE_VERSION}",
            coverage=_coverage(
                evaluated=0, passed=0, failed=0, unknown=0, skipped=0, scopes=scopes
            ),
            mode="vision",
            pipeline_version=VISION_PIPELINE_VERSION,
            summary="Nenhum candidato deterministico para analise visual.",
        )

    resolved_provider = provider or build_ai_provider(settings)
    if provider is None and resolved_provider.provider != "openai":
        raise AIProviderUnavailableError(
            "Configured provider does not support vision.",
            public_message="Analise visual exige provider OpenAI configurado.",
            provider_code="vision_provider_unavailable",
        )

    run_cache_key = _run_cache_key(
        snapshot_hash=str(sheet_map.get("snapshot_hash") or ""),
        candidates=candidates,
        model=resolved_provider.model,
        settings=settings,
    )
    cached_run = audit_repository.get_cached_audit_run(run_cache_key, settings)
    if cached_run is not None:
        return cached_run

    calls, spent = repository.revision_usage(str(sheet_context["revision_id"]), settings)
    findings: list[dict[str, object]] = []
    evaluated = passed = failed = unknown = skipped = 0

    for candidate in candidates:
        crop = render_vision_crop(sheet_id, candidate, settings)
        cache_key = _vision_cache_key(
            crop_hash=crop.crop_hash,
            candidate=candidate,
            provider=resolved_provider,
            settings=settings,
        )
        response = repository.get_cached_response(cache_key, settings)
        if response is None:
            exceeds_calls = calls >= settings.vision_max_calls_per_revision
            exceeds_budget = (
                spent + settings.vision_cost_reserve_usd_per_call
                > settings.vision_budget_usd_per_revision
            )
            if exceeds_calls or exceeds_budget:
                skipped += 1
                continue

            response = resolved_provider.analyze_crop(
                crop=VisionCropInput(
                    candidate=candidate,
                    image_bytes=crop.image_bytes,
                    image_detail=settings.vision_image_detail,
                    crop_hash=crop.crop_hash,
                    crop_bbox_pt=crop.crop_bbox_pt,
                    width_px=crop.width_px,
                    height_px=crop.height_px,
                )
            )
            repository.record_usage(
                response,
                project_id=str(sheet_context["project_id"]),
                revision_id=str(sheet_context["revision_id"]),
                sheet_id=sheet_id,
                settings=settings,
            )
            repository.save_cached_response(cache_key, response, settings)
            calls += 1
            spent += response.estimated_cost_usd

        evaluated += 1
        analysis = response.analysis
        if analysis.outcome == "pass":
            passed += 1
        elif analysis.outcome == "attention" and analysis.confidence >= settings.vision_min_confidence:
            failed += 1
            findings.append(
                _finding(
                    candidate,
                    response,
                    crop_hash=crop.crop_hash,
                    crop_bbox_pt=crop.crop_bbox_pt,
                )
            )
        else:
            unknown += 1

    coverage = _coverage(
        evaluated=evaluated,
        passed=passed,
        failed=failed,
        unknown=unknown,
        skipped=skipped,
        scopes=scopes,
    )
    return audit_repository.create_audit_run(
        sheet_context=sheet_context,
        findings=findings,
        settings=settings,
        cache_key=run_cache_key if skipped == 0 else None,
        sheet_map_id=str(sheet_map["id"]),
        rule_pack_version=(
            f"{VISION_RULE_ID}@{VISION_RULE_VERSION}+{VISION_PROMPT_VERSION}+{resolved_provider.model}"
        ),
        coverage=coverage,
        mode="vision",
        pipeline_version=VISION_PIPELINE_VERSION,
        summary=(
            f"{len(findings)} pontos de atencao visuais em {evaluated} crops; "
            f"{skipped} candidato(s) bloqueado(s) pelo teto."
        ),
    )
