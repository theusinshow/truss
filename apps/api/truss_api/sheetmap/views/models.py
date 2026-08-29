from dataclasses import dataclass, field


VIEW_KIND_PLAN = "plan"
VIEW_KIND_SECTION = "section"
VIEW_KIND_DETAIL = "detail"
VIEW_KIND_PERSPECTIVE = "perspective"

VALID_VIEW_KINDS = frozenset(
    {VIEW_KIND_PLAN, VIEW_KIND_SECTION, VIEW_KIND_DETAIL, VIEW_KIND_PERSPECTIVE}
)

# Um detalhe agrupador cobre varias subviews sob um unico titulo, como
# "DETALHE 01/02/03/04 LAJE PRE-FABRICADA". As subviews internas nao precisam
# repetir o titulo completo.
VIEW_ROLE_GROUPING = "grouping_detail"
VIEW_ROLE_SUBVIEW = "subview"

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class MeasuredValue:
    """Texto bruto do PDF e valor normalizado, sempre separados.

    Normalizar nivel sem confirmacao humana e proibido: "-650" pode ser -6,50 m
    ou outra convencao. Quando nao houver confirmacao, `normalized` fica None.
    """

    raw: str | None
    normalized: str | None = None


@dataclass(frozen=True)
class DetectedView:
    view_kind: str
    identifier: str | None
    title: MeasuredValue
    declared_scale: MeasuredValue
    level: MeasuredValue
    bbox: BBox
    confidence: float
    provenance: str
    view_role: str | None = None
    subviews: list["DetectedView"] = field(default_factory=list)


@dataclass(frozen=True)
class ScaleAnchor:
    text: str
    scale: str | None
    bbox: BBox
    size: float
    is_numeric: bool


@dataclass(frozen=True)
class TitleCandidate:
    identifier: str | None
    title: str
    bbox: BBox
    size: float
    # `title` vem normalizado (maiusculas, sem acento) porque e o que casa com
    # padroes; `raw` preserva o que esta escrito na folha.
    raw: str = ""
