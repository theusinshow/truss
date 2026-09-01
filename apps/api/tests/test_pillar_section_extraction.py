from truss_api.sheetmap.elements.association import associate_elements
from truss_api.sheetmap.elements.pillars import extract_pillars
from truss_api.sheetmap.elements.sections import (
    SECTION_PROVENANCE,
    associate_pillar_sections,
    parse_section_span,
)
from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.models import DetectedView, MeasuredValue


def _span(text: str, bbox: tuple[float, float, float, float]) -> TextSpanRecord:
    return TextSpanRecord(
        text=text,
        bbox=bbox,
        font="Arial",
        size=10.0,
        dir=(1.0, 0.0),
    )


def _view(bbox: tuple[float, float, float, float]) -> DetectedView:
    return DetectedView(
        view_kind="plan",
        identifier=None,
        title=MeasuredValue(raw="PLANTA DE FORMAS"),
        declared_scale=MeasuredValue(raw="ESCALA 1:50", normalized="1:50"),
        level=MeasuredValue(raw="0.00", normalized="0.00"),
        bbox=bbox,
        confidence=0.9,
        provenance="test",
        technical_scope="formas",
    )


def _associated_pillars(
    spans: list[TextSpanRecord], views: list[DetectedView]
):
    return associate_elements(
        extract_pillars(spans),
        views,
        sheet_scopes=("formas",),
    )


def test_parses_standalone_section_preserving_order_unit_and_pdf_bbox() -> None:
    span = _span("40x20 CM", (11.0, 22.0, 44.0, 33.0))

    parsed = parse_section_span(span)

    assert parsed is not None
    assert parsed.raw == "40x20 CM"
    assert parsed.a_raw == "40"
    assert parsed.b_raw == "20"
    assert parsed.ordered_signature == (40, 20)
    assert parsed.signature == (20, 40)
    assert parsed.unit_raw == "CM"
    assert parsed.bbox == (11.0, 22.0, 44.0, 33.0)


def test_rejects_embedded_residual_fraction_date_scale_and_out_of_range_tokens() -> None:
    rejected = [
        "V300 20x60",
        "20x50 e=-0.07",
        "B8/30/100",
        "1/2",
        "01/09/2026",
        "ESCALA 1:50",
        "7x30",
        "301x20",
    ]

    assert [parse_section_span(_span(text, (0.0, 0.0, 1.0, 1.0))) for text in rejected] == [
        None
    ] * len(rejected)


def test_associates_section_to_lifecycle_pillar_in_same_view() -> None:
    views = [_view((0.0, 0.0, 100.0, 100.0))]
    code = _span("P1(MORRE)", (10.0, 10.0, 40.0, 20.0))
    section = _span("20x50", (10.0, 21.0, 40.0, 30.0))
    pillars = _associated_pillars([code], views)

    [enriched] = associate_pillar_sections([code, section], pillars, views)

    assert enriched.attributes["lifecycle_state"] == "morre"
    assert enriched.attributes["section_association_status"] == "matched"
    assert enriched.attributes["section_raw"] == "20x50"
    assert enriched.attributes["section_a_raw"] == "20"
    assert enriched.attributes["section_b_raw"] == "50"
    assert enriched.attributes["section_signature"] == [20, 50]
    assert enriched.attributes["section_ordered_signature"] == [20, 50]
    assert enriched.attributes["section_unit_raw"] is None
    assert enriched.attributes["section_bbox_pt"] == [10.0, 21.0, 40.0, 30.0]
    assert enriched.attributes["section_provenance"] == SECTION_PROVENANCE
    assert 0.0 <= enriched.attributes["section_confidence"] <= 1.0


def test_does_not_associate_dimension_embedded_in_beam_label() -> None:
    views = [_view((0.0, 0.0, 100.0, 100.0))]
    code = _span("P1", (10.0, 10.0, 30.0, 20.0))
    beam = _span("V300 20x60", (10.0, 21.0, 70.0, 30.0))
    pillars = _associated_pillars([code], views)

    [enriched] = associate_pillar_sections([code, beam], pillars, views)

    assert "section_association_status" not in enriched.attributes


def test_requires_section_and_pillar_to_belong_to_same_unique_view() -> None:
    views = [
        _view((0.0, 0.0, 100.0, 100.0)),
        _view((100.0, 0.0, 200.0, 100.0)),
    ]
    code = _span("P1", (80.0, 10.0, 99.0, 20.0))
    section = _span("20x50", (101.0, 10.0, 130.0, 20.0))
    pillars = _associated_pillars([code], views)

    [enriched] = associate_pillar_sections([code, section], pillars, views)

    assert enriched.view_index == 0
    assert "section_association_status" not in enriched.attributes


def test_nearest_pillar_must_have_minimum_uniqueness_margin() -> None:
    views = [_view((0.0, 0.0, 100.0, 100.0))]
    p1 = _span("P1", (0.0, 0.0, 10.0, 10.0))
    p2 = _span("P2", (12.0, 0.0, 22.0, 10.0))
    section = _span("20x50", (9.0, 11.0, 15.0, 20.0))
    pillars = _associated_pillars([p1, p2], views)

    enriched = associate_pillar_sections([p1, p2, section], pillars, views)

    assert all("section_association_status" not in item.attributes for item in enriched)


def test_distinct_sections_for_one_occurrence_remain_ambiguous() -> None:
    views = [_view((0.0, 0.0, 100.0, 100.0))]
    code = _span("P30", (10.0, 10.0, 40.0, 20.0))
    first = _span("19x30", (10.0, 20.0, 40.0, 29.0))
    second = _span("19x40", (10.0, 21.0, 40.0, 30.0))
    pillars = _associated_pillars([code], views)

    [enriched] = associate_pillar_sections([code, first, second], pillars, views)

    assert enriched.attributes["section_association_status"] == "ambiguous"
    assert enriched.attributes["section_candidate_count"] == 2
    assert enriched.attributes["section_candidate_signatures"] == [[19, 30], [19, 40]]
    assert [item["bbox_pt"] for item in enriched.attributes["section_candidates"]] == [
        [10.0, 20.0, 40.0, 29.0],
        [10.0, 21.0, 40.0, 30.0],
    ]
    assert "section_signature" not in enriched.attributes


def test_reversed_duplicate_reinforces_same_size_without_losing_printed_order() -> None:
    views = [_view((0.0, 0.0, 100.0, 100.0))]
    code = _span("P1", (10.0, 10.0, 40.0, 20.0))
    nearest = _span("30x14", (10.0, 20.5, 40.0, 29.5))
    duplicate = _span("14x30", (10.0, 21.0, 40.0, 30.0))
    pillars = _associated_pillars([code], views)

    [enriched] = associate_pillar_sections(
        [code, nearest, duplicate], pillars, views
    )

    assert enriched.attributes["section_association_status"] == "matched"
    assert enriched.attributes["section_signature"] == [14, 30]
    assert enriched.attributes["section_ordered_signature"] == [30, 14]
    assert enriched.attributes["section_evidence_count"] == 2


def test_incompatible_explicit_and_missing_units_are_ambiguous() -> None:
    views = [_view((0.0, 0.0, 100.0, 100.0))]
    code = _span("P1", (10.0, 10.0, 40.0, 20.0))
    explicit = _span("20x40 cm", (10.0, 20.5, 40.0, 29.5))
    missing = _span("20x40", (10.0, 21.0, 40.0, 30.0))
    pillars = _associated_pillars([code], views)

    [enriched] = associate_pillar_sections(
        [code, explicit, missing], pillars, views
    )

    assert enriched.attributes["section_association_status"] == "ambiguous"
    assert enriched.attributes["section_candidate_units"] == [None, "cm"]
    assert "section_unit_raw" not in enriched.attributes
