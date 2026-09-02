from __future__ import annotations

from collections import defaultdict
from typing import Any

from truss_api.calibration.contracts import POLICY_VERSION, digest_payload


def _stable_key(kind: str, *parts: object) -> str:
    return f"cal:{kind}:{digest_payload([str(part or '') for part in parts])[:20]}"


def _evidence_key(item: dict[str, Any], kind: str) -> str:
    return digest_payload(
        {
            "kind": kind,
            "document": item.get("document_sha256"),
            "page": item.get("page_index"),
            "rule": item.get("rule_id"),
            "description": item.get("description", ""),
        }
    )[:24]


def _evidence(item: dict[str, Any], kind: str) -> dict[str, Any]:
    bbox = item.get("bbox") or {}
    return {
        "evidence_key": _evidence_key(item, kind),
        "evidence_kind": kind,
        "document_sha256": item.get("document_sha256"),
        "page_index": item.get("page_index"),
        "sheet_code": item.get("sheet_code"),
        "bbox": bbox or None,
        "source_finding_id": item.get("source_finding_id"),
        "description": str(item.get("description") or item.get("reason") or ""),
        "payload": {
            key: item.get(key)
            for key in ("outcome", "confidence", "authority", "signal_kind")
            if item.get(key) is not None
        },
    }


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique.setdefault(str(item["evidence_key"]), item)
    return list(unique.values())


def generate_proposals(
    raw: dict[str, Any],
    feedback: list[dict[str, Any]],
    learning_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Gera propostas conservadoras; nunca converte uma sugestao em regra executavel."""
    evaluations: list[dict[str, Any]] = raw.get("evaluations", [])
    findings: list[dict[str, Any]] = raw.get("findings", [])
    passes: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    failures: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    rejected: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for item in evaluations:
        if item.get("outcome") == "PASS":
            passes[(str(item.get("sheet_type") or ""), str(item.get("rule_id") or ""))].append(item)
    for item in findings:
        failures[(str(item.get("sheet_type") or ""), str(item.get("rule_id") or ""))].append(item)
    for item in feedback:
        if item.get("signal_kind") == "rejected" and item.get("rule_id"):
            rejected[(str(item.get("sheet_type") or ""), str(item["rule_id"]))].append(item)

    proposals: list[dict[str, Any]] = []
    for key in sorted(set(failures) | set(rejected)):
        sheet_type, rule_id = key
        samples = failures[key]
        distinct_documents = {
            str(item.get("document_sha256"))
            for item in samples
            if item.get("authority") == "delivered_reference"
        }
        rejected_samples = rejected[key]
        if len(distinct_documents) < 2 and not rejected_samples:
            continue
        evidence = [_evidence(item, "sample") for item in samples[:5]]
        evidence.extend(_evidence(item, "feedback") for item in rejected_samples[:5])
        evidence.extend(_evidence(item, "counterexample") for item in passes[key][:3])
        proposals.append(
            {
                "stable_key": _stable_key("rule_noise", sheet_type, rule_id),
                "proposal_kind": "rule_noise",
                "sheet_type": sheet_type or None,
                "technical_scope": next((item.get("technical_scope") for item in samples if item.get("technical_scope")), None),
                "rule_id": rule_id,
                "title": f"Revisar ruido da regra {rule_id}",
                "rationale": (
                    f"A regra apareceu em {len(distinct_documents)} documento(s) entregue(s)"
                    f" e possui {len(rejected_samples)} rejeicao(oes) humana(s)."
                ),
                "payload": {
                    "document_count": len(distinct_documents),
                    "finding_count": len(samples),
                    "rejected_feedback_count": len(rejected_samples),
                    "passing_counterexample_count": len(passes[key]),
                    "rule_spec_status": "existing_rule_review",
                },
                "policy_version": POLICY_VERSION,
                "evidence": _dedupe_evidence(evidence),
            }
        )

    for decision in learning_decisions:
        if decision.get("decision") != "approved":
            continue
        kind = str(decision.get("proposal_kind") or "")
        if kind not in {"draft_rule", "retain_rule"}:
            continue
        proposal_kind = "checklist_candidate" if kind == "draft_rule" else "rule_retention"
        source_key = str(decision["stable_key"])
        proposals.append(
            {
                "stable_key": _stable_key(proposal_kind, source_key),
                "proposal_kind": proposal_kind,
                "sheet_type": decision.get("sheet_type"),
                "technical_scope": decision.get("technical_scope"),
                "rule_id": decision.get("rule_id"),
                "title": (
                    "Projetar item de checklist deterministico"
                    if proposal_kind == "checklist_candidate"
                    else f"Manter regra {decision.get('rule_id') or source_key}"
                ),
                "rationale": str(decision.get("reason") or "Decisao humana aprovada na central de aprendizado."),
                "payload": {
                    "source_learning_key": source_key,
                    "source_decision_id": decision.get("id"),
                    "rule_spec_status": "needs_design" if proposal_kind == "checklist_candidate" else "retain_existing",
                },
                "policy_version": POLICY_VERSION,
                "evidence": [
                    _evidence(item, "feedback")
                    for item in decision.get("evidence", [])[:5]
                ],
            }
        )

    return sorted(proposals, key=lambda item: (str(item["proposal_kind"]), str(item["stable_key"])))
