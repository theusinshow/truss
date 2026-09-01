from truss_api.audit.orchestrator import dedupe_key_for
from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_pack
from truss_api.rules.models import (
    OUTCOME_FAIL,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_PASS,
    OUTCOME_UNKNOWN,
    SCOPE_GENERAL,
)


RULE_ID = "cross_sheet.pillar_section_transition"
PROVENANCE = "native-text/pillar-section-v1:adjacent-label"


def _element(
    code: str,
    *,
    view_id: str = "lower",
    associated: bool = True,
    technical_scope: str = "formas",
) -> dict:
    attributes: dict[str, object] = {}
    if associated:
        attributes["section_association_status"] = "matched"
    return {
        "id": f"element-{code}-{view_id}",
        "view_id": view_id,
        "technical_scope": technical_scope,
        "element_kind": "pillar",
        "code_raw": code,
        "code": code,
        "attributes": attributes,
        "x0": 10.0,
        "y0": 20.0,
        "x1": 30.0,
        "y1": 40.0,
        "confidence": 0.95,
    }


def _snapshot(*elements: dict) -> dict:
    return {
        "id": "source-map",
        "sheet_type": "planta_formas",
        "technical_scopes": [{"technical_scope": "formas"}],
        "title_block": {"category": "PLANTA DE FORMAS", "title": "PLANTA"},
        "regions": [{"region_kind": "moldura", "x0": 0, "y0": 0, "x1": 100, "y1": 100}],
        "views": [],
        "elements": list(elements),
    }


def _section(
    code: str,
    *,
    view_id: str,
    signature: tuple[int, int] | None,
    ordered: tuple[int, int] | None = None,
    unit: str | None = None,
    status: str = "resolved",
) -> dict:
    entry: dict[str, object] = {
        "view_id": view_id,
        "code": code,
        "technical_scope": "formas",
        "sheet_id": f"sheet-{view_id}",
        "sheet_code": "EST-0100-A" if view_id == "lower" else "EST-0200-A",
        "status": status,
        "evidence_count": 1,
    }
    if status == "resolved" and signature is not None:
        printed = ordered or signature
        entry.update(
            {
                "resolution": "unique",
                "section_raw": f"{printed[0]}x{printed[1]}",
                "section_signature": list(signature),
                "section_ordered_signature": list(printed),
                "section_unit_raw": unit,
                "section_bbox_pt": [10.0, 41.0, 30.0, 50.0],
                "code_bbox_pt": [10.0, 20.0, 30.0, 40.0],
                "section_provenance": PROVENANCE,
                "section_confidence": 0.9,
            }
        )
    else:
        entry.update(
            {
                "section_signatures": [[20, 20], [20, 40]],
                "section_units": [None],
                "section_provenance": PROVENANCE,
            }
        )
    return entry


def _registry(*sections: dict, include_pair: bool = True) -> dict:
    pairs = (
        [
            {
                "lower_view_id": "lower",
                "upper_view_id": "upper",
                "lower_sheet_id": "sheet-lower",
                "upper_sheet_id": "sheet-upper",
                "lower_sheet_code": "EST-0100-A",
                "upper_sheet_code": "EST-0200-A",
                "lower_level_raw": "680",
                "upper_level_raw": "780",
                "provenance": "same-sheet-level-order-v1",
                "confidence": 0.9,
            }
        ]
        if include_pair
        else []
    )
    return {
        "registry_hash": "registry-sections",
        "form_levels": [
            {"view_id": "lower", "level_raw": "680", "sheet_code": "EST-0100-A"},
            {"view_id": "upper", "level_raw": "780", "sheet_code": "EST-0200-A"},
        ],
        "form_level_pairs": pairs,
        "occurrences": [],
        "pillar_sections": list(sections),
    }


def _transition(snapshot: dict, registry: dict):
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL), snapshot, registry
    )
    return [item for item in evaluations if item.rule_id == RULE_ID]


def test_same_signature_between_paired_levels_passes() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P27", view_id="upper", signature=(20, 40)),
        ),
    )

    assert evaluation.outcome == OUTCOME_PASS
    assert evaluation.element_code == "P27"
    assert evaluation.view_id == "lower"
    assert evaluation.registry_hash == "registry-sections"


def test_changed_signature_is_a_medium_attention_point_not_an_error() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P27", view_id="upper", signature=(20, 20)),
        ),
    )

    assert evaluation.outcome == OUTCOME_FAIL
    assert evaluation.finding_type == "attention"
    assert evaluation.severity == "medium"
    assert "20x40" in evaluation.reason
    assert "20x20" in evaluation.reason
    assert "680" in evaluation.reason
    assert "780" in evaluation.reason
    assert evaluation.bbox == (10.0, 20.0, 30.0, 40.0)
    # Com o tamanho alterado, a ordem impressa ja esta contada na mudanca.
    assert not any("ordem impressa" in item for item in evaluation.evidence)


def test_finding_carries_both_ends_with_traceable_evidence() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40), unit="cm"),
            _section("P27", view_id="upper", signature=(20, 20), unit="cm"),
        ),
    )
    evidence = "\n".join(evaluation.evidence)

    assert "origem:" in evidence
    assert "alvo:" in evidence
    assert "EST-0100-A" in evidence and "EST-0200-A" in evidence
    assert "lower" in evidence and "upper" in evidence
    assert "[10.0, 41.0, 30.0, 50.0]" in evidence
    assert PROVENANCE in evidence
    assert "registry-sections" in evidence
    assert "unidade: cm" in evidence


def test_reversed_order_is_same_size_and_orientation_stays_unverified() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(14, 30), ordered=(14, 30)),
            _section("P27", view_id="upper", signature=(14, 30), ordered=(30, 14)),
        ),
    )
    evidence = "\n".join(evaluation.evidence)

    assert evaluation.outcome == OUTCOME_PASS
    assert "14x30" in evidence and "30x14" in evidence
    assert "orientacao nao verificada" in evidence


def test_absent_section_at_the_target_end_is_unknown() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(_section("P27", view_id="lower", signature=(20, 40))),
    )

    assert evaluation.outcome == OUTCOME_UNKNOWN
    assert evaluation.finding_type == "unverifiable"


def test_ambiguous_section_at_either_end_is_unknown() -> None:
    at_target = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P27", view_id="upper", signature=None, status="ambiguous"),
        ),
    )[0]
    at_source = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=None, status="ambiguous"),
            _section("P27", view_id="upper", signature=(20, 40)),
        ),
    )[0]

    assert at_target.outcome == OUTCOME_UNKNOWN
    assert at_source.outcome == OUTCOME_UNKNOWN


def test_incompatible_unit_is_unknown_and_never_completed_by_convention() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40), unit="cm"),
            _section("P27", view_id="upper", signature=(20, 20), unit=None),
        ),
    )

    assert evaluation.outcome == OUTCOME_UNKNOWN
    assert evaluation.finding_type == "unverifiable"


def test_sheet_without_associated_sections_is_not_applicable() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27", associated=False)),
        _registry(),
    )

    assert evaluation.outcome == OUTCOME_NOT_APPLICABLE
    assert evaluation.target_id is None


def test_pillar_without_a_safe_pair_is_not_applicable() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            include_pair=False,
        ),
    )

    assert evaluation.outcome == OUTCOME_NOT_APPLICABLE
    assert evaluation.element_code == "P27"


def test_absent_code_at_the_target_level_stays_with_f32_and_never_fails_here() -> None:
    [evaluation] = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P30", view_id="upper", signature=(20, 20)),
        ),
    )

    assert evaluation.outcome == OUTCOME_UNKNOWN


def test_other_technical_scopes_are_never_compared() -> None:
    evaluations = _transition(
        _snapshot(_element("P27", technical_scope="cobertura")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P27", view_id="upper", signature=(20, 20)),
        ),
    )

    assert [item.outcome for item in evaluations] == [OUTCOME_NOT_APPLICABLE]


def test_dedupe_separates_distinct_transitions_of_the_same_code() -> None:
    changed = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P27", view_id="upper", signature=(20, 20)),
        ),
    )[0]
    other = _transition(
        _snapshot(_element("P27")),
        _registry(
            _section("P27", view_id="lower", signature=(20, 40)),
            _section("P27", view_id="upper", signature=(20, 30)),
        ),
    )[0]

    assert dedupe_key_for(changed, "sheet") != dedupe_key_for(other, "sheet")
