from truss_api.sheetmap.elements.association import associate_elements
from truss_api.sheetmap.elements.models import ELEMENT_KIND_PILLAR
from truss_api.sheetmap.elements.pillars import extract_pillars
from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.models import DetectedView, MeasuredValue


def _span(text: str, bbox=(10.0, 20.0, 40.0, 32.0)) -> TextSpanRecord:
    return TextSpanRecord(
        text=text,
        bbox=bbox,
        font="Arial",
        size=10.0,
        dir=(1.0, 0.0),
    )


def _view(bbox, scope="formas") -> DetectedView:
    return DetectedView(
        view_kind="plan",
        identifier=None,
        title=MeasuredValue(raw="PLANTA DE FORMAS"),
        declared_scale=MeasuredValue(raw="ESCALA 1:50", normalized="1:50"),
        level=MeasuredValue(raw=None),
        bbox=bbox,
        confidence=0.9,
        provenance="test",
        technical_scope=scope,
    )


def test_extracts_pillar_codes_preserving_raw_text_and_pdf_bbox() -> None:
    elements = extract_pillars([_span("P1  P 12  P-12A")])

    assert [(item.code_raw, item.code) for item in elements] == [
        ("P1", "P1"),
        ("P 12", "P12"),
        ("P-12A", "P12A"),
    ]
    assert all(item.element_kind == ELEMENT_KIND_PILLAR for item in elements)
    assert all(item.bbox == (10.0, 20.0, 40.0, 32.0) for item in elements)
    assert all(item.provenance == "native-text/pillar-code-v1" for item in elements)


def test_equivalence_preserves_both_codes_and_source_expression() -> None:
    elements = extract_pillars([_span("P21=P38")])

    assert [item.code for item in elements] == ["P21", "P38"]
    assert all(item.attributes["source_text"] == "P21=P38" for item in elements)


def test_rejects_embedded_words_assignment_and_cross_line_fragments() -> None:
    spans = [
        _span("CP1 APOIO P=10 XP2"),
        _span("P", (10.0, 50.0, 16.0, 62.0)),
        _span("12", (18.0, 80.0, 30.0, 92.0)),
    ]

    assert extract_pillars(spans) == []


def test_joins_adjacent_fragments_on_the_same_line() -> None:
    spans = [
        _span("P", (10.0, 50.0, 16.0, 62.0)),
        _span("12", (18.0, 50.0, 30.0, 62.0)),
    ]

    [element] = extract_pillars(spans)

    assert element.code_raw == "P 12"
    assert element.code == "P12"
    assert element.bbox == (10.0, 50.0, 30.0, 62.0)


def test_association_uses_unique_containing_view() -> None:
    [element] = extract_pillars([_span("P12")])

    [associated] = associate_elements(
        [element],
        [_view((0.0, 0.0, 100.0, 100.0))],
        sheet_scopes=("formas",),
    )

    assert associated.view_index == 0
    assert associated.technical_scope == "formas"
    assert associated.attributes["association_status"] == "view_matched"


def test_overlapping_views_remain_ambiguous_on_a_mixed_sheet() -> None:
    [element] = extract_pillars([_span("P12")])

    [associated] = associate_elements(
        [element],
        [
            _view((0.0, 0.0, 100.0, 100.0), "formas"),
            _view((0.0, 0.0, 100.0, 100.0), "armaduras"),
        ],
        sheet_scopes=("formas", "armaduras"),
    )

    assert associated.view_index is None
    assert associated.technical_scope is None
    assert associated.attributes["association_status"] == "ambiguous_views"

