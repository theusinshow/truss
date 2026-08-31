from truss_api.sheetmap.technical_scopes import (
    SCOPE_FORMS,
    SCOPE_REINFORCEMENT,
    assign_view_scopes,
    detect_technical_scopes,
)
from truss_api.sheetmap.snapshot import snapshot_hash
from truss_api.sheetmap.views.models import DetectedView, MeasuredValue


def _view(title: str) -> DetectedView:
    return DetectedView(
        view_kind="detail",
        identifier=None,
        title=MeasuredValue(raw=title),
        declared_scale=MeasuredValue(raw="ESCALA 1:20", normalized="1:20"),
        level=MeasuredValue(raw=None),
        bbox=(0.0, 0.0, 100.0, 100.0),
        confidence=0.9,
        provenance="anchor",
    )


def test_mixed_title_block_preserves_forms_and_reinforcement() -> None:
    scopes = detect_technical_scopes(
        sheet_type="desconhecido",
        classification_confidence=0.2,
        title_block_text="FORMAS LAJES TOPO, DET. TAMPA E DET. REFORCO NA ABERTURA",
        views=[],
    )

    assert {item.technical_scope for item in scopes} == {
        SCOPE_FORMS,
        SCOPE_REINFORCEMENT,
    }
    assert all(item.provenance == "titulo_ou_carimbo" for item in scopes)


def test_mixed_sheet_assigns_only_explicit_view_scopes() -> None:
    scopes = detect_technical_scopes(
        sheet_type="desconhecido",
        classification_confidence=0.2,
        title_block_text="FORMAS E ARMADURAS",
        views=[],
    )
    assigned = assign_view_scopes(
        [
            _view("PLANTA DE FORMAS - TOPO"),
            _view("ARMACAO POSITIVA DA LAJE"),
            _view("DETALHE DA TAMPA"),
        ],
        scopes,
    )

    assert [view.technical_scope for view in assigned] == [
        SCOPE_FORMS,
        SCOPE_REINFORCEMENT,
        None,
    ]


def test_single_scope_is_inherited_by_every_view() -> None:
    scopes = detect_technical_scopes(
        sheet_type="planta_formas",
        classification_confidence=0.97,
        title_block_text="PLANTA DE FORMAS",
        views=[],
    )

    assert assign_view_scopes([_view("CORTE A-A")], scopes)[0].technical_scope == SCOPE_FORMS


def test_technical_scopes_are_part_of_the_immutable_snapshot_hash() -> None:
    common = {
        "sheet_type": "desconhecido",
        "sheet_code": "EST-0300-A",
        "title_block": {},
        "regions": [],
        "views": [],
        "extraction_hash": "abc",
    }

    forms_only = snapshot_hash(
        **common,
        technical_scopes=[{"technical_scope": "formas"}],
    )
    mixed = snapshot_hash(
        **common,
        technical_scopes=[
            {"technical_scope": "formas"},
            {"technical_scope": "armaduras"},
        ],
    )

    assert forms_only != mixed


def test_raw_sheet_code_is_part_of_the_immutable_snapshot_hash() -> None:
    common = {
        "sheet_type": "planta_armaduras",
        "sheet_code": "EST-0210-A",
        "technical_scopes": [],
        "title_block": {},
        "regions": [],
        "views": [],
        "extraction_hash": "abc",
    }

    short = snapshot_hash(**common, sheet_code_raw="EST-0210-A")
    compound = snapshot_hash(
        **common, sheet_code_raw="XXXXX-SES-ETE-EST-0210-A"
    )

    assert short != compound
