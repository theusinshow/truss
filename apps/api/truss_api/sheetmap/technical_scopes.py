from dataclasses import dataclass, replace
import re

from truss_api.core.text import normalize
from truss_api.sheetmap.views.models import DetectedView


SCOPE_FORMS = "formas"
SCOPE_REINFORCEMENT = "armaduras"
SCOPE_LOCATION = "locacao"
SCOPE_ROOF = "cobertura"
SCOPE_FOUNDATIONS = "fundacoes"

SCOPE_ORDER = (
    SCOPE_LOCATION,
    SCOPE_FOUNDATIONS,
    SCOPE_FORMS,
    SCOPE_REINFORCEMENT,
    SCOPE_ROOF,
)

SHEET_TYPE_TO_SCOPE = {
    "planta_formas": SCOPE_FORMS,
    "planta_armaduras": SCOPE_REINFORCEMENT,
    "planta_locacao": SCOPE_LOCATION,
    "planta_cobertura": SCOPE_ROOF,
    "planta_cobertura_madeira": SCOPE_ROOF,
    "planta_fundacoes": SCOPE_FOUNDATIONS,
}

SCOPE_TO_SHEET_TYPE = {
    SCOPE_FORMS: "planta_formas",
    SCOPE_REINFORCEMENT: "planta_armaduras",
    SCOPE_LOCATION: "planta_locacao",
    SCOPE_ROOF: "planta_cobertura",
    SCOPE_FOUNDATIONS: "planta_fundacoes",
}


@dataclass(frozen=True)
class DetectedTechnicalScope:
    technical_scope: str
    confidence: float
    provenance: str


def scope_for_sheet_type(sheet_type: str) -> str | None:
    return SHEET_TYPE_TO_SCOPE.get(sheet_type)


def sheet_type_for_scope(technical_scope: str) -> str | None:
    return SCOPE_TO_SHEET_TYPE.get(technical_scope)


def _contains(text: str, term: str) -> bool:
    return bool(re.search(rf"\b{re.escape(term)}\b", text))


def scopes_from_text(text: str) -> set[str]:
    """Escopos declarados pelo proprio titulo/carimbo, nunca pelo nome do arquivo."""
    normalized = normalize(text)
    scopes: set[str] = set()

    if _contains(normalized, "FORMA") or _contains(normalized, "FORMAS"):
        scopes.add(SCOPE_FORMS)

    if any(
        _contains(normalized, term)
        for term in ("ARMADURA", "ARMADURAS", "ARMACAO", "REFORCO")
    ):
        scopes.add(SCOPE_REINFORCEMENT)

    if _contains(normalized, "LOCACAO"):
        scopes.add(SCOPE_LOCATION)

    return scopes


def detect_technical_scopes(
    *,
    sheet_type: str,
    classification_confidence: float,
    title_block_text: str,
    views: list[DetectedView],
) -> list[DetectedTechnicalScope]:
    candidates: dict[str, DetectedTechnicalScope] = {}

    legacy_scope = scope_for_sheet_type(sheet_type)
    if legacy_scope:
        candidates[legacy_scope] = DetectedTechnicalScope(
            legacy_scope,
            classification_confidence,
            "sheet_type",
        )

    view_titles = " ".join(view.title.raw or "" for view in views)
    for technical_scope in scopes_from_text(f"{title_block_text} {view_titles}"):
        explicit = DetectedTechnicalScope(
            technical_scope, 0.92, "titulo_ou_carimbo"
        )
        current = candidates.get(technical_scope)
        if current is None or explicit.confidence > current.confidence:
            candidates[technical_scope] = explicit

    order = {scope: index for index, scope in enumerate(SCOPE_ORDER)}
    return sorted(
        candidates.values(),
        key=lambda item: (order.get(item.technical_scope, len(order)), item.technical_scope),
    )


def _scope_for_view(view: DetectedView, available: set[str]) -> str | None:
    explicit = scopes_from_text(view.title.raw or "") & available
    if len(explicit) == 1:
        return next(iter(explicit))
    if len(available) == 1:
        return next(iter(available))
    return None


def assign_view_scopes(
    views: list[DetectedView],
    scopes: list[DetectedTechnicalScope],
) -> list[DetectedView]:
    available = {item.technical_scope for item in scopes}

    def assign(view: DetectedView) -> DetectedView:
        technical_scope = view.technical_scope or _scope_for_view(view, available)
        return replace(
            view,
            technical_scope=technical_scope,
            subviews=[assign(subview) for subview in view.subviews],
        )

    return [assign(view) for view in views]
