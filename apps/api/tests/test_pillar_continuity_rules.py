import pytest

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


RULE_ID = "cross_sheet.pillar_lifecycle_continuity"


def _element(code: str, state: str | None, *, view_id: str = "source") -> dict:
    attributes = {
        "source_text": f"{code}({state.upper()})" if state else code,
    }
    if state:
        attributes.update(
            {
                "lifecycle_state": state,
                "lifecycle_raw": f"({state.upper()})",
                "lifecycle_confidence": 0.98,
            }
        )
    return {
        "id": f"element-{code}-{view_id}",
        "view_id": view_id,
        "technical_scope": "formas",
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


def _snapshot(element: dict) -> dict:
    return {
        "id": "source-map",
        "sheet_type": "planta_formas",
        "technical_scopes": [{"technical_scope": "formas"}],
        "title_block": {"category": "PLANTA DE FORMAS", "title": "PLANTA"},
        "regions": [{"region_kind": "moldura", "x0": 0, "y0": 0, "x1": 100, "y1": 100}],
        "views": [],
        "elements": [element],
    }


def _registry(
    *,
    source_is_upper: bool,
    target_codes: tuple[str, ...],
    include_pair: bool = True,
) -> dict:
    lower_id, upper_id = ("target", "source") if source_is_upper else ("source", "target")
    levels = [
        {
            "view_id": lower_id,
            "level_raw": "100",
            "sheet_code": "EST-0100-A",
        },
        {
            "view_id": upper_id,
            "level_raw": "200",
            "sheet_code": "EST-0200-A",
        },
    ]
    pairs = (
        [
            {
                "lower_view_id": lower_id,
                "upper_view_id": upper_id,
                "provenance": "same-sheet-level-order-v1",
                "confidence": 0.9,
            }
        ]
        if include_pair
        else []
    )
    return {
        "registry_hash": "registry-continuity",
        "form_levels": levels,
        "form_level_pairs": pairs,
        "occurrences": [
            {
                "id": f"target-{code}",
                "view_id": "target",
                "sheet_id": "sheet-target",
                "technical_scope": "formas",
                "element_kind": "pillar",
                "code": code,
                "x0": 50.0,
                "y0": 60.0,
                "x1": 70.0,
                "y1": 80.0,
                "confidence": 0.95,
            }
            for code in target_codes
        ],
    }


def _continuity(element: dict, registry: dict):
    evaluations = evaluate(
        load_pack("planta_formas", SCOPE_GENERAL),
        _snapshot(element),
        registry,
    )
    return [item for item in evaluations if item.rule_id == RULE_ID]


@pytest.mark.parametrize(
    ("state", "source_is_upper", "target_codes", "expected"),
    [
        ("passa", False, ("P1", "P99"), OUTCOME_PASS),
        ("passa", False, ("P99",), OUTCOME_FAIL),
        ("morre", False, ("P99",), OUTCOME_PASS),
        ("morre", False, ("P1", "P99"), OUTCOME_FAIL),
        ("nasce", True, ("P99",), OUTCOME_PASS),
        ("nasce", True, ("P1", "P99"), OUTCOME_FAIL),
    ],
)
def test_explicit_lifecycle_covers_six_expected_outcomes(
    state: str,
    source_is_upper: bool,
    target_codes: tuple[str, ...],
    expected: str,
) -> None:
    [evaluation] = _continuity(
        _element("P1", state),
        _registry(source_is_upper=source_is_upper, target_codes=target_codes),
    )

    assert evaluation.outcome == expected
    assert evaluation.element_code == "P1"
    assert evaluation.view_id == "source"
    assert evaluation.registry_hash == "registry-continuity"
    assert evaluation.dedupe_discriminator == f"{state}|{'200' if source_is_upper else '100'}"
    assert evaluation.evidence[0] == f"estado: {state}"


def test_missing_pair_or_empty_target_is_unknown() -> None:
    no_pair = _continuity(
        _element("P1", "morre"),
        _registry(source_is_upper=False, target_codes=("P99",), include_pair=False),
    )[0]
    empty_target = _continuity(
        _element("P1", "morre"),
        _registry(source_is_upper=False, target_codes=()),
    )[0]

    assert no_pair.outcome == OUTCOME_UNKNOWN
    assert empty_target.outcome == OUTCOME_UNKNOWN


def test_unmarked_pillar_is_not_applicable_never_assumed_to_pass() -> None:
    [evaluation] = _continuity(
        _element("P1", None),
        _registry(source_is_upper=False, target_codes=("P99",)),
    )

    assert evaluation.outcome == OUTCOME_NOT_APPLICABLE
    assert evaluation.target_id is None


def test_same_code_at_different_levels_has_distinct_stable_dedupe() -> None:
    first_registry = _registry(source_is_upper=False, target_codes=("P1", "P99"))
    second_registry = _registry(source_is_upper=False, target_codes=("P1", "P99"))
    second_registry["form_levels"][0]["level_raw"] = "150"
    second_registry["form_levels"][1]["level_raw"] = "250"
    first = _continuity(_element("P1", "morre"), first_registry)[0]
    second = _continuity(_element("P1", "morre"), second_registry)[0]

    assert dedupe_key_for(first, "sheet") != dedupe_key_for(second, "sheet")
