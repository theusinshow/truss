from dataclasses import dataclass, field


BBox = tuple[float, float, float, float]

ELEMENT_KIND_PILLAR = "pillar"


@dataclass(frozen=True)
class DetectedElement:
    element_kind: str
    code_raw: str
    code: str
    bbox: BBox
    confidence: float
    provenance: str
    attributes: dict[str, object] = field(default_factory=dict)
    # Indice da view de primeiro nivel no snapshot em construcao. O repository
    # resolve o UUID somente ao persistir, depois que as views recebem ids.
    view_index: int | None = None
    technical_scope: str | None = None

