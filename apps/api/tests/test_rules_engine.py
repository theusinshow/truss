"""Motor de checklist e os dois rule packs de plantas de formas.

A politica humana confirmada em `calibration/human-review/forms-policy-decisions-v1.md`
separa regra geral leniente de preferencia pessoal obrigatoria, e lista regras
negativas que nao podem virar falso positivo. Os testes abaixo sao a leitura
executavel desse documento.
"""

import pytest

from truss_api.rules.engine import evaluate
from truss_api.rules.loader import load_pack, load_packs
from truss_api.rules.models import (
    OUTCOME_FAIL,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_PASS,
    OUTCOME_UNKNOWN,
    SCOPE_GENERAL,
    SCOPE_PERSONAL,
)
from truss_api.rules.schema import RulePackSchemaError, validate_pack


def _snapshot(views: list[dict], category: str = "PLANTA DE FORMAS") -> dict:
    return {
        "sheet_type": "planta_formas",
        "title_block": {"category": category},
        "views": views,
        "regions": [{"region_kind": "moldura", "x0": 0, "y0": 0, "x1": 100, "y1": 100}],
    }


def _view(**overrides) -> dict:
    base = {
        "id": "v1",
        "view_kind": "plan",
        "view_role": None,
        "identifier": "1",
        "title_raw": "PLANTA DE FORMAS - TERREO",
        "title": None,
        "declared_scale_raw": "ESCALA 1:50",
        "declared_scale": "1:50",
        "level_raw": "-04",
        "level": None,
        "x0": 10.0,
        "y0": 10.0,
        "x1": 200.0,
        "y1": 200.0,
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def _outcome(evaluations, rule_id: str, index: int = 0):
    return [e for e in evaluations if e.rule_id == rule_id][index]


def test_both_scopes_load_and_validate() -> None:
    packs = {pack.scope: pack for pack in load_packs("planta_formas")}

    assert set(packs) == {SCOPE_GENERAL, SCOPE_PERSONAL}
    assert {rule.rule_id for rule in packs[SCOPE_GENERAL].rules} >= {
        "forms.sheet.has_main_view",
        "forms.view.title_present",
        "forms.view.scale_declared",
        "forms.view.level_declared",
        "forms.sheet.category_matches_content",
        "forms.sheet.duplicate_identifier",
    }
    assert all(pack.sheet_type == "planta_formas" for pack in packs.values())


def test_invalid_pack_is_rejected_by_schema() -> None:
    with pytest.raises(RulePackSchemaError):
        validate_pack({"pack_id": "x", "version": "1"})


def test_complete_sheet_produces_only_pass() -> None:
    evaluations = evaluate(load_pack("planta_formas", SCOPE_GENERAL), _snapshot([_view()]))

    assert {e.outcome for e in evaluations} == {OUTCOME_PASS}


def test_technical_view_without_numeric_scale_fails_with_evidence() -> None:
    """Politica: view tecnica precisa de escala numerica ou ESCALA INDICADA."""
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_view(declared_scale_raw="ESCALA REPRESENTATIVA", declared_scale=None)]),
    )

    failure = _outcome(evaluations, "forms.view.scale_declared")
    assert failure.outcome == OUTCOME_FAIL
    assert failure.target_kind == "view"
    assert failure.target_id == "v1"
    assert failure.evidence


def test_escala_indicada_is_a_valid_declaration_for_a_technical_view() -> None:
    """Vale em composicoes com subviews em escalas diferentes."""
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_view(declared_scale_raw="ESCALA INDICADA", declared_scale=None)]),
    )

    assert _outcome(evaluations, "forms.view.scale_declared").outcome == OUTCOME_PASS


def test_auxiliary_perspective_is_never_an_incomplete_technical_view() -> None:
    """Regra negativa do gabarito: perspectiva sem titulo, escala numerica ou
    nivel nao e view tecnica incompleta."""
    perspective = _view(
        id="v2",
        view_kind="perspective",
        identifier=None,
        title_raw=None,
        declared_scale_raw="ESCALA REPRESENTATIVA",
        declared_scale=None,
        level_raw=None,
    )

    evaluations = evaluate(load_pack("planta_formas", SCOPE_GENERAL), _snapshot([perspective]))

    for rule_id in (
        "forms.view.title_present",
        "forms.view.scale_declared",
        "forms.view.level_declared",
    ):
        assert _outcome(evaluations, rule_id).outcome == OUTCOME_NOT_APPLICABLE, rule_id


def test_subview_does_not_have_to_repeat_the_grouping_title() -> None:
    subview = _view(id="v3", view_role="subview", title_raw=None, identifier="2")

    evaluations = evaluate(load_pack("planta_formas", SCOPE_GENERAL), _snapshot([subview]))

    assert _outcome(evaluations, "forms.view.title_present").outcome == OUTCOME_NOT_APPLICABLE


def test_sheet_without_views_fails_the_main_view_rule() -> None:
    """Sem views o motor nao pode alegar conformidade."""
    evaluations = evaluate(load_pack("planta_formas", SCOPE_GENERAL), _snapshot([]))

    assert _outcome(evaluations, "forms.sheet.has_main_view").outcome == OUTCOME_FAIL
    assert not [e for e in evaluations if e.target_kind == "view"]


def test_duplicate_identifiers_are_reported_once_as_attention() -> None:
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_view(id="v1", identifier="1"), _view(id="v2", identifier="1")]),
    )

    duplicates = [
        e
        for e in evaluations
        if e.rule_id == "forms.sheet.duplicate_identifier" and e.outcome == OUTCOME_FAIL
    ]
    assert len(duplicates) == 1
    assert duplicates[0].finding_type == "attention"


def test_intentional_grouping_equivalence_is_not_a_duplicate() -> None:
    """P21=P38 e P28=P37 sao detalhamentos equivalentes, nao duplicidade."""
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot(
            [
                _view(id="v1", identifier="1", title_raw="PILAR P21=P38"),
                _view(id="v2", identifier="1", title_raw="PILAR P28=P37"),
            ]
        ),
    )

    assert _outcome(evaluations, "forms.sheet.duplicate_identifier").outcome == OUTCOME_PASS


def test_category_mismatch_is_an_inconsistency_of_medium_severity() -> None:
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_view(view_kind="detail", title_raw="DETALHE 01")]),
    )

    mismatch = _outcome(evaluations, "forms.sheet.category_matches_content")
    assert mismatch.outcome == OUTCOME_FAIL
    assert mismatch.finding_type == "inconsistency"
    assert mismatch.severity == "medium"


def test_missing_level_is_lenient_in_general_and_mandatory_in_personal() -> None:
    """A politica do proprietario: regra geral leniente, preferencia pessoal obrigatoria."""
    snapshot = _snapshot([_view(level_raw=None)])

    general = _outcome(
        evaluate(load_pack("planta_formas", SCOPE_GENERAL), snapshot),
        "forms.view.level_declared",
    )
    personal = _outcome(
        evaluate(load_pack("planta_formas", SCOPE_PERSONAL), snapshot),
        "forms.view.level_declared",
    )

    assert general.outcome == OUTCOME_FAIL
    assert general.finding_type == "attention"
    assert general.severity == "low"

    assert personal.outcome == OUTCOME_FAIL
    assert personal.finding_type == "missing_information"
    assert personal.severity == "high"
    assert personal.scope == SCOPE_PERSONAL


def test_low_confidence_segmentation_is_unverifiable_not_a_failure() -> None:
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot([_view(title_raw=None, confidence=0.5)]),
    )

    unverifiable = _outcome(evaluations, "forms.view.title_present")
    assert unverifiable.outcome == OUTCOME_UNKNOWN
    assert unverifiable.finding_type == "unverifiable"


def test_every_evaluation_is_traceable() -> None:
    for evaluation in evaluate(load_pack("planta_formas", SCOPE_GENERAL), _snapshot([_view()])):
        assert evaluation.rule_id and evaluation.rule_version and evaluation.rule_pack_version
        assert evaluation.scope in {SCOPE_GENERAL, SCOPE_PERSONAL}
        assert evaluation.bbox is not None
