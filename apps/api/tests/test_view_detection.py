import fitz

from tests.factories import make_forms_sheet_pdf_bytes
from truss_api.sheetmap.geometry import geometry_from_extraction
from truss_api.sheetmap.primitives import (
    PageExtraction,
    PageMetadata,
    TextSpanRecord,
    extract_page,
)
from truss_api.sheetmap.regions import (
    REGION_DRAWING,
    REGION_FRAME,
    REGION_TABLE,
    DetectedRegion,
    detect_regions,
    extract_line_boxes,
)
from truss_api.sheetmap.views.detector import _assign_titles, detect_forms_views
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


def _detect() -> list:
    document = fitz.open(stream=make_forms_sheet_pdf_bytes(), filetype="pdf")
    page = document.load_page(0)
    extraction = extract_page(page)
    regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
    return detect_forms_views(extraction, regions)


def test_detects_one_view_per_scale_anchor() -> None:
    assert len(_detect()) == 3


def test_each_view_carries_title_scale_and_kind() -> None:
    views = {view.title.raw: view for view in _detect()}

    assert views["PLANTA DE FORMAS - TERREO"].declared_scale.normalized == "1:50"
    assert views["PLANTA DE FORMAS - TERREO"].declared_scale.raw == "ESCALA 1:50"
    assert views["PLANTA DE FORMAS - TERREO"].view_kind == "plan"
    assert views["CORTE A-A"].view_kind == "section"
    assert views["DETALHE 01 LAJE"].view_kind == "detail"


def test_plan_view_captures_the_declared_level_without_normalizing_it() -> None:
    plan = next(view for view in _detect() if view.view_kind == "plan")

    assert plan.level.raw == "-0.05"
    assert plan.level.normalized is None


def test_views_do_not_include_the_title_block() -> None:
    for view in _detect():
        assert view.bbox[0] < 1700 or view.bbox[1] < 1400


def test_a_table_does_not_become_a_view() -> None:
    """Um quadro de pilares com escala proxima nao pode virar view."""
    document = fitz.open(stream=make_forms_sheet_pdf_bytes(), filetype="pdf")
    page = document.load_page(0)
    extraction = extract_page(page)
    regions = detect_regions(geometry_from_extraction(extraction), extract_line_boxes(page))
    regions.append(DetectedRegion(REGION_TABLE, 190, 190, 950, 640, 0.7))

    views = detect_forms_views(extraction, regions)

    assert all(not (190 <= v.bbox[0] <= 950 and 190 <= v.bbox[1] <= 640) for v in views)


def test_every_view_records_provenance() -> None:
    assert all(view.provenance for view in _detect())


def test_two_anchors_never_claim_the_same_title() -> None:
    """Regressao medida na pagina 8 do projeto-base.

    A ancora 1:20 do detalhe e a ancora 1:50 da planta vizinha escolhiam ambas
    "PLANTA DE FORMAS - TOPO RESERVATORIO", porque cada ancora buscava seu
    titulo isoladamente. Um titulo pertence a exatamente uma view.
    """
    spans = [
        _span("PLANTA DE FORMAS - TOPO RESERVATORIO", 300, 100, 15.8),
        _span("ESCALA 1:50", 300, 130, 5.9),
        _span("DETALHE 01 LAJE PRE-FABRICADA", 900, 100, 15.8),
        _span("ESCALA 1:20", 900, 130, 5.9),
    ]

    titles = _assign_titles(find_scale_anchors(spans, exclude=None), spans)

    assert [title.title if title else None for title in titles] == [
        "PLANTA DE FORMAS - TOPO RESERVATORIO",
        "DETALHE 01 LAJE PRE-FABRICADA",
    ]


def test_level_comes_from_the_view_own_title_before_the_bounding_box() -> None:
    """Regressao medida na pagina 5 do projeto-base.

    A bbox de uma view alcanca o titulo da view vizinha, e `find_level_near`
    devolve a primeira ocorrencia na ordem do documento - que pode ser a do
    vizinho. A regra de checklist entao passava afirmando "nivel declarado" com
    o valor errado. A politica humana diz que a planta declara o nivel no
    titulo, entao o titulo tem precedencia sobre a varredura espacial.
    """
    # O span do vizinho vem primeiro na ordem do documento, embora esteja mais
    # abaixo na folha: e exatamente a ordenacao que produzia o valor errado.
    spans = [
        _span("PLANTA DE FORMAS - FUNDO PISCINA (NIVEL -167)", 1800, 1390, 15.8),
        _span("ESCALA 1:50", 1800, 1420, 5.9),
        _span("PLANTA DE FORMAS - INTERMEDIARIA PISCINA (NIVEL -350)", 700, 1000, 15.8),
        _span("ESCALA 1:50", 700, 1030, 5.9),
    ]
    extraction = PageExtraction(
        metadata=PageMetadata(
            width_pt=2384.0,
            height_pt=1684.0,
            rotation=0,
            mediabox=(0.0, 0.0, 2384.0, 1684.0),
            cropbox=(0.0, 0.0, 2384.0, 1684.0),
            rotation_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        ),
        spans=spans,
    )
    regions = [
        DetectedRegion(REGION_FRAME, 0, 0, 2384, 1684, 0.95),
        DetectedRegion(REGION_DRAWING, 0, 0, 2384, 1684, 0.95),
    ]

    levels = {
        view.title.raw: view.level.raw for view in detect_forms_views(extraction, regions)
    }

    assert levels["PLANTA DE FORMAS - INTERMEDIARIA PISCINA (NIVEL -350)"] == "-350"
    assert levels["PLANTA DE FORMAS - FUNDO PISCINA (NIVEL -167)"] == "-167"
