from truss_api.sheetmap.elements.levels import (
    build_form_level_registry,
    context_signature,
    parse_level_ordinal,
)


def _view(
    view_id: str,
    level: str,
    *,
    page: int,
    sheet: str,
    document: str = "doc-1",
    title: str = "PLANTA DE FORMAS",
) -> dict[str, object]:
    return {
        "id": view_id,
        "view_kind": "plan",
        "technical_scope": "formas",
        "confidence": 0.9,
        "level_raw": level,
        "title_raw": f"{title} (NIVEL {level})",
        "sheet_map_id": f"map-{sheet}",
        "sheet_id": sheet,
        "document_id": document,
        "sheet_code": sheet,
        "sheet_code_raw": sheet,
        "page_index": page,
    }


def _occurrence(code: str, view_id: str, document: str = "doc-1") -> dict[str, object]:
    return {
        "id": f"{view_id}-{code}",
        "element_kind": "pillar",
        "technical_scope": "formas",
        "confidence": 0.95,
        "code": code,
        "view_id": view_id,
        "document_id": document,
    }


def _registry(views, codes_by_view) -> dict[str, object]:
    occurrences = [
        _occurrence(code, view_id, next(v["document_id"] for v in views if v["id"] == view_id))
        for view_id, codes in codes_by_view.items()
        for code in codes
    ]
    return {"views": views, "occurrences": occurrences}


def test_relative_level_parser_never_claims_an_engineering_unit() -> None:
    parsed = parse_level_ordinal("-650")

    assert parsed == {
        "raw": "-650",
        "ordinal": parsed["ordinal"],
        "notation_family": "integer",
        "provenance": "numeric-relative-level-v1",
    }
    assert str(parsed["ordinal"]) == "-650"
    assert parse_level_ordinal("COBERTURA") is None
    assert context_signature("PLANTA DE FORMAS - COBERTURA (NIVEL 680)") == "ESTRUTURA"


def test_pairs_levels_inside_sheet_and_across_adjacent_sheets_with_strong_overlap() -> None:
    views = [
        _view("ground", "-04", page=6, sheet="S7"),
        _view("first", "338", page=7, sheet="S8"),
        _view("roof", "680", page=7, sheet="S8"),
        _view("tank", "780", page=8, sheet="S9"),
        _view("top", "940", page=8, sheet="S9"),
    ]
    common = {"P1", "P2", "P3", "P4"}
    registry = _registry(
        views,
        {
            "ground": common | {"P5"},
            "first": common | {"P6"},
            "roof": common | {"P7"},
            "tank": common,
            "top": common,
        },
    )

    result = build_form_level_registry(registry)
    pairs = {
        (item["lower_view_id"], item["upper_view_id"]): item
        for item in result["form_level_pairs"]
    }

    assert set(pairs) == {
        ("ground", "first"),
        ("first", "roof"),
        ("roof", "tank"),
        ("tank", "top"),
    }
    assert pairs[("ground", "first")]["provenance"] == "adjacent-sheet-code-overlap-v1"
    assert pairs[("first", "roof")]["provenance"] == "same-sheet-level-order-v1"


def test_never_pairs_documents_page_gaps_or_weak_code_reuse() -> None:
    views = [
        _view("a", "100", page=0, sheet="A", document="doc-a"),
        _view("b", "200", page=1, sheet="B", document="doc-b"),
        _view("c", "300", page=4, sheet="C", document="doc-a"),
        _view("d", "400", page=5, sheet="D", document="doc-a"),
    ]
    registry = _registry(
        views,
        {"a": {"P1", "P2"}, "b": {"P1", "P2"}, "c": {"P1"}, "d": {"P1"}},
    )

    result = build_form_level_registry(registry)

    assert result["form_level_pairs"] == []


def test_never_pairs_adjacent_structures_with_distinct_context_and_reused_codes() -> None:
    views = [
        _view("a", "100", page=0, sheet="A", title="PLANTA DE FORMAS ESTRUTURA A"),
        _view("b", "200", page=1, sheet="B", title="PLANTA DE FORMAS ESTRUTURA B"),
    ]
    reused = {"P1", "P2", "P3", "P4"}

    result = build_form_level_registry(_registry(views, {"a": reused, "b": reused}))

    assert result["form_level_pairs"] == []


def test_duplicate_level_is_ambiguous() -> None:
    views = [
        _view("a", "100", page=0, sheet="S"),
        _view("b", "100", page=0, sheet="S"),
        _view("c", "200.5", page=0, sheet="S"),
    ]
    registry = _registry(views, {"a": {"P1"}, "b": {"P2"}, "c": {"P1", "P2"}})

    result = build_form_level_registry(registry)

    assert result["form_level_pairs"] == []
    assert {item["reason"] for item in result["form_level_ambiguities"]} == {
        "duplicate_level"
    }


def test_incompatible_level_notation_is_ambiguous() -> None:
    views = [
        _view("a", "100", page=0, sheet="S"),
        _view("b", "200.5", page=0, sheet="S"),
    ]
    registry = _registry(views, {"a": {"P1"}, "b": {"P1"}})

    result = build_form_level_registry(registry)

    assert result["form_level_pairs"] == []
    assert result["form_level_ambiguities"] == [
        {
            "document_id": "doc-1",
            "page_index": 0,
            "reason": "incompatible_level_notation",
            "view_ids": ["a", "b"],
        }
    ]
