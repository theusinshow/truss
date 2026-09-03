from truss_api.comparisons.layers import LAYER_DELTA_LIMIT, diff_layers
from truss_api.sheetmap.primitives import (
    PageExtraction,
    PageMetadata,
    TextSpanRecord,
    VectorPrimitive,
)


METADATA = PageMetadata(
    width_pt=1000,
    height_pt=800,
    rotation=0,
    mediabox=(0, 0, 1000, 800),
    cropbox=(0, 0, 1000, 800),
    rotation_matrix=(1, 0, 0, 1, 0, 0),
)


def _span(text: str, x: float, *, font: str = "Helvetica") -> TextSpanRecord:
    return TextSpanRecord(
        text=text,
        bbox=(x, 100, x + 80, 112),
        font=font,
        size=10,
        dir=(1, 0),
    )


def _vector(
    kind: str,
    x: float,
    *,
    width: float = 1,
) -> VectorPrimitive:
    return VectorPrimitive(
        kind=kind,
        points=[(x, 200), (x + 40, 200)],
        rect=(x, 200, x + 40, 201),
        width=width,
        color=(0, 0, 0),
        dashes="[] 0",
    )


def _page(
    *,
    spans: list[TextSpanRecord] | None = None,
    primitives: list[VectorPrimitive] | None = None,
) -> PageExtraction:
    return PageExtraction(
        metadata=METADATA,
        spans=spans or [],
        primitives=primitives or [],
    )


def test_text_delta_classifies_added_removed_modified_and_moved() -> None:
    base = _page(
        spans=[
            _span("SEM ALTERACAO", 10),
            _span("MOVER", 100),
            _span("VIGA V1 20x40", 300),
            _span("REMOVIDO", 500),
        ]
    )
    target = _page(
        spans=[
            _span("SEM ALTERACAO", 10),
            _span("MOVER", 180),
            _span("VIGA V1 20x45", 300),
            _span("ADICIONADO", 700),
        ]
    )

    result = diff_layers(base, target)

    assert result.counts["text"] == {
        "total": 4,
        "added": 1,
        "removed": 1,
        "modified": 1,
        "moved": 1,
    }
    assert {delta["change_type"] for delta in result.deltas} == {
        "added",
        "removed",
        "modified",
        "moved",
    }
    modified = next(delta for delta in result.deltas if delta["change_type"] == "modified")
    assert modified["before_value"] == "VIGA V1 20x40"
    assert modified["after_value"] == "VIGA V1 20x45"
    assert modified["base_bbox"]["x0"] == 300


def test_duplicate_text_is_not_guessed_as_a_movement() -> None:
    result = diff_layers(
        _page(spans=[_span("DUPLICADO", 10), _span("DUPLICADO", 30)]),
        _page(spans=[_span("DUPLICADO", 100), _span("DUPLICADO", 120)]),
    )

    assert result.counts["text"]["moved"] == 0
    assert result.counts["text"]["modified"] == 0
    assert result.counts["text"]["added"] == 2
    assert result.counts["text"]["removed"] == 2


def test_vector_delta_classifies_added_removed_modified_and_moved() -> None:
    base = _page(
        primitives=[
            _vector("l", 10),
            _vector("qu", 100),
            _vector("l", 300, width=1),
            _vector("re", 500),
        ]
    )
    target = _page(
        primitives=[
            _vector("l", 10),
            _vector("qu", 180),
            _vector("l", 300, width=2),
            _vector("c", 700),
        ]
    )

    result = diff_layers(base, target)

    assert result.counts["vector"] == {
        "total": 4,
        "added": 1,
        "removed": 1,
        "modified": 1,
        "moved": 1,
    }


def test_layer_delta_limit_preserves_full_counts() -> None:
    base = _page(
        spans=[_span(f"ITEM {index}", float(index * 2)) for index in range(LAYER_DELTA_LIMIT + 1)]
    )

    result = diff_layers(base, _page())

    assert result.truncated is True
    assert result.counts["text"]["removed"] == LAYER_DELTA_LIMIT + 1
    assert len(result.deltas) == LAYER_DELTA_LIMIT
