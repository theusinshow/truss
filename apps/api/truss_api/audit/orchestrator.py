from hashlib import sha256

from truss_api.audit import repository
from truss_api.core.settings import Settings
from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_packs, load_packs_for_scopes
from truss_api.rules.models import (
    OUTCOME_FAIL,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_PASS,
    OUTCOME_SKIPPED,
    OUTCOME_UNKNOWN,
    RuleEvaluation,
)
from truss_api.sheetmap import repository as sheetmap_repository
from truss_api.sheetmap.primitives import EXTRACTOR_VERSION


AUDIT_PIPELINE_VERSION = "audit-v0.2"

def audit_cache_key(
    *,
    document_hash: str,
    extractor_version: str,
    pipeline_version: str,
    snapshot_hash: str,
    rule_pack_id: str,
    rule_pack_version: str,
) -> str:
    material = "|".join(
        [
            document_hash,
            extractor_version,
            pipeline_version,
            snapshot_hash,
            rule_pack_id,
            rule_pack_version,
        ]
    )
    return f"audit:{sha256(material.encode('utf-8')).hexdigest()[:24]}"


def dedupe_key_for(evaluation: RuleEvaluation, sheet_id: str) -> str:
    """Identidade estavel de um achado ao longo de reexecucoes.

    O escopo entra na chave porque a regra geral e a preferencia pessoal
    compartilham `rule_id` sobre o mesmo alvo. Sem ele, a exigencia pessoal do
    proprietario seria engolida pela regra geral e nunca apareceria.
    """
    material = "|".join(
        [
            sheet_id,
            evaluation.technical_scope,
            evaluation.scope,
            evaluation.rule_id,
            evaluation.target_kind,
            evaluation.target_id or "",
        ]
    )
    return sha256(material.encode("utf-8")).hexdigest()[:24]


def _finding_from_evaluation(
    evaluation: RuleEvaluation,
    sheet_context: dict[str, object],
) -> dict[str, object]:
    bbox = evaluation.bbox or (
        0.0,
        0.0,
        float(sheet_context["width_pt"]),
        float(sheet_context["height_pt"]),
    )

    return {
        "category": evaluation.category,
        "type": evaluation.finding_type,
        "description": evaluation.reason or evaluation.rule_id,
        "severity": evaluation.severity,
        "confidence": evaluation.confidence,
        "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
        "evidence": evaluation.evidence,
        "rule_id": evaluation.rule_id,
        "rule_version": evaluation.rule_version,
        "rule_scope": evaluation.scope,
        "technical_scope": evaluation.technical_scope,
        "view_id": evaluation.target_id if evaluation.target_kind == "view" else None,
        "source_layer": "deterministic",
        "dedupe_key": dedupe_key_for(evaluation, str(sheet_context["sheet_id"])),
    }


def _coverage(
    evaluations: list[RuleEvaluation],
    technical_scopes: list[str],
    packs: tuple,
) -> dict[str, object]:
    covered_scopes = sorted({pack.technical_scope for pack in packs})
    return {
        "evaluated": len(evaluations),
        "passed": sum(1 for e in evaluations if e.outcome == OUTCOME_PASS),
        "failed": sum(1 for e in evaluations if e.outcome == OUTCOME_FAIL),
        "unknown": sum(1 for e in evaluations if e.outcome == OUTCOME_UNKNOWN),
        "not_applicable": sum(1 for e in evaluations if e.outcome == OUTCOME_NOT_APPLICABLE),
        "skipped": sum(1 for e in evaluations if e.outcome == OUTCOME_SKIPPED),
        "technical_scopes": sorted(set(technical_scopes)),
        "covered_scopes": covered_scopes,
        "uncovered_scopes": sorted(set(technical_scopes) - set(covered_scopes)),
    }


def run_deterministic_audit(sheet_id: str, settings: Settings) -> dict[str, object]:
    sheet_context = repository.get_sheet_context(sheet_id, settings)
    sheet_map = sheetmap_repository.get_sheet_map(sheet_id, settings)
    technical_scopes = [
        str(item["technical_scope"])
        for item in sheet_map.get("technical_scopes", [])
        if item.get("technical_scope")
    ]
    packs = load_packs_for_scopes(technical_scopes)
    if not packs:
        packs = load_packs(str(sheet_map["sheet_type"]))

    if not packs:
        # Sem rule pack para o tipo, o Truss nao inventa conformidade nem erro.
        return repository.create_audit_run(
            sheet_context=sheet_context,
            findings=[],
            settings=settings,
            cache_key=None,
            sheet_map_id=str(sheet_map["id"]),
            rule_pack_version="",
            coverage=_coverage([], technical_scopes, ()),
            evaluations=[],
        )

    cache_key = audit_cache_key(
        document_hash=str(sheet_map.get("document_hash") or ""),
        extractor_version=str(sheet_map.get("extractor_version") or EXTRACTOR_VERSION),
        pipeline_version=AUDIT_PIPELINE_VERSION,
        snapshot_hash=str(sheet_map.get("snapshot_hash") or ""),
        rule_pack_id="+".join(pack.pack_id for pack in packs),
        rule_pack_version="+".join(pack.version for pack in packs),
    )
    cached = repository.get_cached_audit_run(cache_key, settings)
    if cached is not None:
        return cached

    # Os escopos rodam juntos e ficam separados no resultado: o proprietario ve
    # a sua exigencia sem que ela seja apresentada como norma.
    evaluations: list[RuleEvaluation] = []
    for pack in packs:
        evaluations.extend(evaluate(pack, sheet_map))

    findings = [
        _finding_from_evaluation(evaluation, sheet_context)
        for evaluation in evaluations
        if evaluation.outcome == OUTCOME_FAIL
    ]

    return repository.create_audit_run(
        sheet_context=sheet_context,
        findings=findings,
        settings=settings,
        cache_key=cache_key,
        sheet_map_id=str(sheet_map["id"]),
        rule_pack_version="+".join(f"{pack.pack_id}@{pack.version}" for pack in packs),
        coverage=_coverage(evaluations, technical_scopes, packs),
        evaluations=evaluations,
    )
