from truss_api.sheetmap.elements.registry import (
    _element_digest,
    build_pillar_section_registry,
)


def _occurrence(
    code: str,
    *,
    view_id: str = "view-a",
    signature: tuple[int, int] | None = (20, 40),
    ordered: tuple[int, int] | None = None,
    unit: str | None = None,
    raw: str | None = None,
    occurrence_id: str = "occ-1",
    bbox: tuple[float, float, float, float] = (10.0, 20.0, 30.0, 40.0),
) -> dict[str, object]:
    attributes: dict[str, object] = {"association_status": "view_matched"}
    if signature is not None:
        ordered = ordered or signature
        attributes.update(
            {
                "section_association_status": "matched",
                "section_raw": raw or f"{ordered[0]}x{ordered[1]}",
                "section_signature": list(signature),
                "section_ordered_signature": list(ordered),
                "section_unit_raw": unit,
                "section_bbox_pt": [bbox[0], bbox[3] + 1, bbox[2], bbox[3] + 10],
                "section_provenance": "native-text/pillar-section-v1:adjacent-label",
                "section_confidence": 0.9,
            }
        )
    return {
        "id": occurrence_id,
        "element_kind": "pillar",
        "code_raw": code,
        "code": code,
        "view_id": view_id,
        "technical_scope": "formas",
        "document_id": "doc-1",
        "sheet_id": "sheet-1",
        "sheet_code": "EST-0010-A",
        "page_index": 0,
        "x0": bbox[0],
        "y0": bbox[1],
        "x1": bbox[2],
        "y1": bbox[3],
        "confidence": 0.95,
        "provenance": "test",
        "attributes": attributes,
    }


def test_resolves_unique_section_with_traceable_evidence() -> None:
    [section] = build_pillar_section_registry([_occurrence("P1")])

    assert section["view_id"] == "view-a"
    assert section["code"] == "P1"
    assert section["status"] == "resolved"
    assert section["resolution"] == "unique"
    assert section["section_signature"] == [20, 40]
    assert section["section_bbox_pt"] == [10.0, 41.0, 30.0, 50.0]
    assert section["code_bbox_pt"] == [10.0, 20.0, 30.0, 40.0]
    assert section["evidence_count"] == 1
    assert section["evidence"][0]["occurrence_id"] == "occ-1"


def test_reversed_duplicates_reinforce_same_size_and_preserve_both_orders() -> None:
    first = _occurrence("P1", ordered=(20, 40), occurrence_id="occ-1")
    second = _occurrence(
        "P1",
        ordered=(40, 20),
        occurrence_id="occ-2",
        bbox=(50.0, 20.0, 70.0, 40.0),
    )

    [section] = build_pillar_section_registry([first, second])

    assert section["status"] == "resolved"
    assert section["resolution"] == "reinforced"
    assert section["section_signature"] == [20, 40]
    assert [item["section_ordered_signature"] for item in section["evidence"]] == [
        [20, 40],
        [40, 20],
    ]
    assert section["section_confidence"] == 0.92


def test_divergent_duplicate_sections_remain_ambiguous() -> None:
    first = _occurrence("P1", occurrence_id="occ-1")
    second = _occurrence(
        "P1",
        signature=(14, 40),
        occurrence_id="occ-2",
        bbox=(50.0, 20.0, 70.0, 40.0),
    )

    [section] = build_pillar_section_registry([first, second])

    assert section["status"] == "ambiguous"
    assert section["section_signatures"] == [[14, 40], [20, 40]]
    assert section["evidence_count"] == 2
    assert "section_signature" not in section


def test_explicit_and_missing_units_are_not_merged() -> None:
    first = _occurrence("P1", unit=None, occurrence_id="occ-1")
    second = _occurrence(
        "P1",
        unit="cm",
        occurrence_id="occ-2",
        bbox=(50.0, 20.0, 70.0, 40.0),
    )

    [section] = build_pillar_section_registry([first, second])

    assert section["status"] == "ambiguous"
    assert section["section_units"] == [None, "cm"]


def test_same_code_in_different_views_is_resolved_independently() -> None:
    lower = _occurrence("P1", view_id="lower", signature=(20, 40))
    upper = _occurrence(
        "P1", view_id="upper", signature=(14, 40), occurrence_id="occ-2"
    )

    sections = build_pillar_section_registry([lower, upper])

    assert [(item["view_id"], item["section_signature"]) for item in sections] == [
        ("lower", [20, 40]),
        ("upper", [14, 40]),
    ]


def test_missing_section_does_not_create_a_registry_entry() -> None:
    occurrence = _occurrence("P1", signature=None)

    assert build_pillar_section_registry([occurrence]) == []


def test_occurrence_level_ambiguity_preserves_candidate_coordinates() -> None:
    occurrence = _occurrence("P30", signature=None)
    occurrence["attributes"].update(
        {
            "section_association_status": "ambiguous",
            "section_provenance": "native-text/pillar-section-v1:adjacent-label",
            "section_candidates": [
                {
                    "raw": "19x30",
                    "signature": [19, 30],
                    "ordered_signature": [19, 30],
                    "unit_raw": None,
                    "bbox_pt": [10.0, 41.0, 30.0, 50.0],
                },
                {
                    "raw": "19x40",
                    "signature": [19, 40],
                    "ordered_signature": [19, 40],
                    "unit_raw": None,
                    "bbox_pt": [10.0, 42.0, 30.0, 51.0],
                },
            ],
        }
    )

    [section] = build_pillar_section_registry([occurrence])

    assert section["status"] == "ambiguous"
    assert [item["section_bbox_pt"] for item in section["evidence"]] == [
        [10.0, 41.0, 30.0, 50.0],
        [10.0, 42.0, 30.0, 51.0],
    ]


def test_section_attributes_participate_in_element_fingerprint() -> None:
    first = _occurrence("P1", signature=(20, 40))
    second = _occurrence("P1", signature=(14, 40))

    assert _element_digest([first]) != _element_digest([second])
