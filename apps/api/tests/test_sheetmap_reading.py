"""Regioes, carimbo e classificacao.

Cobre as tres armadilhas medidas no projeto real, todas de falha silenciosa:
o carimbo nao e um retangulo, a regiao precisa alcancar o canto da moldura, e a
categoria so casa com extracao em granularidade de linha.
"""

from truss_api.sheetmap.classifier import SHEET_TYPE_UNKNOWN, classify_sheet_type
from truss_api.sheetmap.geometry import GeometryRect, PageGeometry
from truss_api.sheetmap.regions import (
    REGION_DRAWING,
    REGION_FRAME,
    REGION_TABLE,
    REGION_TITLE_BLOCK,
    DetectedRegion,
    TextBox,
    detect_frame,
    detect_regions,
    detect_title_block,
    drawing_zones,
    is_title_block_anchor,
)
from truss_api.sheetmap.title_block import TitleBlockFields, parse_title_block


def _geometry() -> PageGeometry:
    return PageGeometry(
        width_pt=1000,
        height_pt=800,
        rects=[
            GeometryRect(0, 0, 1000, 800),
            GeometryRect(20, 10, 970, 770),
            GeometryRect(300, 300, 500, 450),
        ],
        line_count=1200,
        curve_count=30,
    )


def _title_block_boxes() -> list[TextBox]:
    return [
        TextBox("EST-0060-A", 700, 700, 820, 715),
        TextBox("CPF: 951.770.276-00", 700, 720, 850, 735),
        TextBox("L33", 100, 100, 130, 115),
    ]


def test_detect_frame_picks_largest_rect_below_full_page() -> None:
    frame = detect_frame(_geometry())

    assert frame.region_kind == REGION_FRAME
    assert (frame.x0, frame.y0, frame.x1, frame.y1) == (20, 10, 970, 770)


def test_title_block_is_anchored_by_text_and_reaches_the_frame_corner() -> None:
    frame = detect_frame(_geometry())

    title_block = detect_title_block(_title_block_boxes(), _geometry(), frame)

    assert title_block is not None
    assert (title_block.x0, title_block.y0) == (700, 700)
    assert (title_block.x1, title_block.y1) == (frame.x1, frame.y1)


def test_title_block_ignores_anchors_outside_the_bottom_right_corner() -> None:
    boxes = [TextBox("EST-0060-A", 40, 40, 160, 55)]

    assert detect_title_block(boxes, _geometry(), detect_frame(_geometry())) is None


def test_detect_regions_returns_frame_title_block_and_drawing_zones() -> None:
    regions = detect_regions(_geometry(), _title_block_boxes())

    kinds = [region.region_kind for region in regions]
    assert kinds[0] == REGION_FRAME
    assert REGION_TITLE_BLOCK in kinds
    assert kinds.count(REGION_DRAWING) >= 1

    frame = regions[0]
    drawing = [region for region in regions if region.region_kind == REGION_DRAWING]
    assert max(zone.y1 for zone in drawing) == frame.y1, (
        "a zona de desenho nao pode parar no topo do carimbo"
    )


def test_drawing_zone_is_not_truncated_at_the_title_block_top() -> None:
    """A zona de desenho nao pode perder a faixa lateral ao lado do carimbo."""
    frame = DetectedRegion(REGION_FRAME, 20, 10, 970, 770, 0.95)
    title_block = DetectedRegion(REGION_TITLE_BLOCK, 700, 700, 970, 770, 0.9)

    zones = drawing_zones(frame, [title_block])

    total_area = sum((z.x1 - z.x0) * (z.y1 - z.y0) for z in zones)
    truncated_area = (frame.x1 - frame.x0) * (title_block.y0 - frame.y0)

    assert total_area > truncated_area
    assert all(z.region_kind == REGION_DRAWING for z in zones)


def test_drawing_zones_do_not_overlap_occupied_regions() -> None:
    frame = DetectedRegion(REGION_FRAME, 0, 0, 1000, 1000, 0.95)
    table = DetectedRegion(REGION_TABLE, 800, 0, 1000, 400, 0.8)

    zones = drawing_zones(frame, [table])

    for zone in zones:
        assert not (zone.x0 < 1000 and zone.x1 > 800 and zone.y0 < 400 and zone.y1 > 0)


def _region_and_boxes(lines: list[str]):
    frame = detect_frame(_geometry())
    boxes = [
        TextBox(line, 710, 700 + index * 10, 960, 708 + index * 10)
        for index, line in enumerate(lines)
    ]
    region = detect_title_block(
        boxes + [TextBox("CPF: 000", 710, 690, 900, 698)], _geometry(), frame
    )
    return region, boxes


def test_parse_title_block_is_insensitive_to_line_order() -> None:
    """No PDF real a categoria vem antes de PROJETO ESTRUTURAL em algumas paginas
    e depois em outras, por isso os campos sao achados por conteudo."""
    region, boxes = _region_and_boxes(
        [
            "EST-0060-A",
            "PLANTA DE LOCAÇÃO DAS FUNDAÇÕES",
            "PLANTA DE LOCAÇÃO",
            "PROJETO ESTRUTURAL",
        ]
    )

    fields = parse_title_block(region, boxes)

    assert fields.sheet_code == "EST-0060-A"
    assert fields.sheet_code_raw == "EST-0060-A"
    assert fields.revision_code == "A"
    assert fields.category == "PLANTA DE LOCACAO"
    assert fields.title == "PLANTA DE LOCACAO DAS FUNDACOES"


def test_parse_title_block_preserves_compound_raw_code_separately() -> None:
    region, boxes = _region_and_boxes(
        ["XXXXX-SES-ETE-EST-0210-A", "PLANTA DE ARMADURAS"]
    )

    fields = parse_title_block(region, boxes)

    assert fields.sheet_code_raw == "XXXXX-SES-ETE-EST-0210-A"
    assert fields.sheet_code == "EST-0210-A"
    assert fields.revision_code == "A"


def test_raw_code_without_revision_does_not_invent_canonical_identity() -> None:
    region, boxes = _region_and_boxes(
        ["SES-ETE-EST-0020", "PLANTA DE FORMAS"]
    )

    fields = parse_title_block(region, boxes)

    assert fields.sheet_code_raw == "SES-ETE-EST-0020"
    assert fields.sheet_code is None
    assert fields.revision_code is None
    assert is_title_block_anchor("SES-ETE-EST-0020") is True


def test_classify_prefers_title_block_category_over_sheet_text() -> None:
    fields = TitleBlockFields("EST-0060-A", "A", "PLANTA DE FORMAS", "DETALHE")

    result = classify_sheet_type(fields, "RELACAO DO ACO FORMA PLANTA DE ARMADURAS")

    assert result.sheet_type == "planta_formas"
    assert result.source == "carimbo"


def test_classify_falls_back_to_sheet_text_then_to_unknown() -> None:
    empty = TitleBlockFields(None, None, None, None)

    fallback = classify_sheet_type(empty, "Planta de Armaduras das Lajes")
    unknown = classify_sheet_type(empty, "L33 h=13 L40")

    assert fallback.sheet_type == "planta_armaduras"
    assert fallback.source == "texto"
    assert unknown.sheet_type == SHEET_TYPE_UNKNOWN
