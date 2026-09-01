from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_pack
from truss_api.rules.models import (
    OUTCOME_FAIL,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_PASS,
    OUTCOME_UNKNOWN,
    SCOPE_GENERAL,
)


def _element(code: str, *, element_id: str, view_id: str | None = "forms-view") -> dict:
    return {
        "id": element_id,
        "view_id": view_id,
        "technical_scope": "formas" if view_id else None,
        "element_kind": "pillar",
        "code_raw": code,
        "code": code,
        "x0": 10.0,
        "y0": 20.0,
        "x1": 30.0,
        "y1": 40.0,
        "confidence": 0.95,
    }


def _snapshot(elements: list[dict]) -> dict:
    return {
        "id": "source-map",
        "sheet_type": "planta_formas",
        "technical_scopes": [{"technical_scope": "formas"}],
        "title_block": {"category": "PLANTA DE FORMAS", "title": "PLANTA"},
        "regions": [{"region_kind": "moldura", "x0": 0, "y0": 0, "x1": 100, "y1": 100}],
        "views": [],
        "elements": elements,
    }


def _registry(*, target: bool = True, codes=("P1",)) -> dict:
    views = (
        [
            {
                "id": "target-view",
                "sheet_map_id": "target-map",
                "technical_scope": "armaduras",
                "title_raw": "DETALHAMENTO PILARES",
                "sheet_code": "EST-0200-A",
                "page_index": 1,
                "confidence": 0.9,
            }
        ]
        if target
        else []
    )
    return {
        "registry_hash": "registry-123",
        "views": views,
        "occurrences": [
            {
                "id": f"target-{code}",
                "view_id": "target-view",
                "sheet_map_id": "target-map",
                "technical_scope": "armaduras",
                "element_kind": "pillar",
                "code": code,
                "confidence": 0.95,
            }
            for code in codes
        ],
    }


def _cross(evaluations):
    return [item for item in evaluations if item.rule_id == "cross_sheet.pillar_has_detail"]


def test_missing_pillar_yields_one_localized_cross_sheet_failure() -> None:
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_element("P1", element_id="e1"), _element("P2", element_id="e2")]),
        _registry(codes=("P1",)),
    )

    by_code = {item.element_code: item for item in _cross(evaluations)}
    assert by_code["P1"].outcome == OUTCOME_PASS
    assert by_code["P2"].outcome == OUTCOME_FAIL
    assert by_code["P2"].target_kind == "element"
    assert by_code["P2"].target_id == "e2"
    assert by_code["P2"].view_id == "forms-view"
    assert by_code["P2"].bbox == (10.0, 20.0, 30.0, 40.0)
    assert by_code["P2"].registry_hash == "registry-123"
    assert "nao foi localizado" in by_code["P2"].reason


def test_missing_or_empty_target_is_unknown_never_a_failure() -> None:
    snapshot = _snapshot([_element("P1", element_id="e1")])

    no_target = _cross(
        evaluate(load_pack("planta_formas", SCOPE_GENERAL), snapshot, _registry(target=False))
    )[0]
    empty_target = _cross(
        evaluate(load_pack("planta_formas", SCOPE_GENERAL), snapshot, _registry(codes=()))
    )[0]

    assert no_target.outcome == OUTCOME_UNKNOWN
    assert empty_target.outcome == OUTCOME_UNKNOWN


def test_sheet_without_reliably_associated_source_pillars_is_not_applicable() -> None:
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_element("P1", element_id="e1", view_id=None)]),
        _registry(),
    )

    assert _cross(evaluations)[0].outcome == OUTCOME_NOT_APPLICABLE


def test_ambiguous_occurrence_on_a_recognized_single_scope_target_sheet_counts() -> None:
    registry = _registry(codes=("P1",))
    registry["occurrences"][0]["view_id"] = None
    snapshot = _snapshot([_element("P1", element_id="e1")])

    evaluation = _cross(
        evaluate(load_pack("planta_formas", SCOPE_GENERAL), snapshot, registry)
    )[0]

    assert evaluation.outcome == OUTCOME_PASS


def test_foundation_and_starter_pillar_detail_is_a_valid_target() -> None:
    registry = _registry(codes=("P1",))
    registry["views"][0]["technical_scope"] = "fundacoes"
    registry["views"][0]["title_raw"] = "DETALHAMENTO FUNDACOES E PILARES DE ARRANQUE"
    registry["occurrences"][0]["technical_scope"] = "fundacoes"

    evaluation = _cross(
        evaluate(
            load_pack("planta_formas", SCOPE_GENERAL),
            _snapshot([_element("P1", element_id="e1")]),
            registry,
        )
    )[0]

    assert evaluation.outcome == OUTCOME_PASS


def test_explicit_pillar_detail_title_overrides_noisy_sheet_scope() -> None:
    registry = _registry(codes=("P1",))
    registry["views"][0]["technical_scope"] = "locacao"
    registry["views"][0]["title_raw"] = "DETALHAMENTO FUNDACOES E PILARES DE ARRANQUE"
    registry["occurrences"][0]["technical_scope"] = "locacao"

    evaluation = _cross(
        evaluate(
            load_pack("planta_formas", SCOPE_GENERAL),
            _snapshot([_element("P1", element_id="e1")]),
            registry,
        )
    )[0]

    assert evaluation.outcome == OUTCOME_PASS
