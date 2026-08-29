from truss_api.sheetmap.primitives import TextSpanRecord
from truss_api.sheetmap.views.anchors import (
    find_level_near,
    find_scale_anchors,
    find_title_for,
    title_font_floor,
    view_kind_from_title,
)


def _span(text: str, x0: float, y0: float, size: float) -> TextSpanRecord:
    return TextSpanRecord(
        text=text,
        bbox=(x0, y0, x0 + len(text) * size * 0.5, y0 + size * 1.2),
        font="Helvetica",
        size=size,
        dir=(1.0, 0.0),
    )


def _sheet_spans() -> list[TextSpanRecord]:
    return [
        _span("1 CORTE A-A", 276, 580, 15.8),
        _span("ESCALA 1:50", 276, 599, 5.9),
        _span("CAIBRO 8X16", 300, 667, 11.2),
        _span("19", 800, 700, 7.9),
        _span("2 CORTE B-B", 276, 1252, 15.8),
        _span("ESCALA 1:50", 276, 1271, 5.9),
        _span("NIVEL -0.05", 320, 1300, 7.9),
    ]


def test_finds_every_scale_anchor() -> None:
    anchors = find_scale_anchors(_sheet_spans(), exclude=None)

    assert [anchor.scale for anchor in anchors] == ["1:50", "1:50"]


def test_ignores_scale_inside_the_excluded_title_block() -> None:
    spans = _sheet_spans() + [_span("ESCALA 1:20", 1800, 1500, 8.0)]

    anchors = find_scale_anchors(spans, exclude=(1700.0, 1400.0, 2384.0, 1684.0))

    assert len(anchors) == 2


def test_title_floor_separates_titles_from_dimension_text() -> None:
    floor = title_font_floor(_sheet_spans())

    assert 8.0 < floor <= 15.8


def test_associates_the_title_immediately_above_each_scale() -> None:
    """A tolerancia vertical importa: no material real o titulo termina a fracao
    de ponto do topo da escala, e um limite exato perde a associacao."""
    spans = _sheet_spans()
    floor = title_font_floor(spans)
    anchors = find_scale_anchors(spans, exclude=None)

    titles = [find_title_for(anchor, spans, floor) for anchor in anchors]

    assert [t.title for t in titles if t] == ["CORTE A-A", "CORTE B-B"]
    assert [t.identifier for t in titles if t] == ["1", "2"]


def test_returns_none_when_no_title_precedes_the_scale() -> None:
    spans = [_span("ESCALA 1:50", 100, 500, 5.9), _span("19", 100, 480, 7.9)]

    anchor = find_scale_anchors(spans, exclude=None)[0]

    assert find_title_for(anchor, spans, title_font_floor(spans)) is None


def test_finds_declared_level_inside_the_view_box() -> None:
    level = find_level_near((260.0, 1240.0, 900.0, 1400.0), _sheet_spans())

    assert level == "-0.05"


def test_view_kind_is_derived_from_the_title() -> None:
    assert view_kind_from_title("CORTE A-A") == "section"
    assert view_kind_from_title("DETALHE 01 LAJE") == "detail"
    assert view_kind_from_title("PLANTA DE FORMAS - TERREO") == "plan"
    assert view_kind_from_title(None) == "plan"
