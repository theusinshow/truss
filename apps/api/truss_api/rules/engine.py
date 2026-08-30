from truss_api.core.text import normalize
from truss_api.rules.models import (
    OUTCOME_FAIL,
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_PASS,
    OUTCOME_UNKNOWN,
    BBox,
    Rule,
    RuleEvaluation,
    RulePack,
)


# Abaixo disso a segmentacao nao sustenta uma afirmacao de ausencia.
MIN_VIEW_CONFIDENCE = 0.6

# Declaracao nao numerica aceita numa view tecnica: vale quando as subviews
# estao em escalas diferentes. REPRESENTATIVA nao entra - e de perspectiva.
TECHNICAL_NON_NUMERIC_SCALE = "ESCALA INDICADA"

# Papeis que nao precisam repetir o titulo do detalhe agrupador.
ROLES_EXEMPT_FROM_TITLE = frozenset({"subview"})

# O que o titulo do carimbo anuncia como conteudo da folha. A categoria e a
# disciplina - "PLANTA DE FORMAS" numa folha de cortes de formas esta correta -
# entao quem se compara com as views e o titulo, nao a categoria.
ANNOUNCED_CONTENT: tuple[tuple[str, str], ...] = (
    ("CORTE", "section"),
    ("SECAO", "section"),
    ("DETALHE", "detail"),
    ("DETALHAMENTO", "detail"),
    ("PLANTA", "plan"),
)


def _bbox(view: dict) -> BBox:
    return (float(view["x0"]), float(view["y0"]), float(view["x1"]), float(view["y1"]))


def _sheet_bbox(snapshot: dict) -> BBox | None:
    frame = next(
        (r for r in snapshot.get("regions", []) if r["region_kind"] == "moldura"), None
    )
    if frame is None:
        return None

    return (float(frame["x0"]), float(frame["y0"]), float(frame["x1"]), float(frame["y1"]))


def _result(
    rule: Rule,
    pack: RulePack,
    *,
    target_kind: str,
    target_id: str | None,
    outcome: str,
    reason: str,
    evidence: list[str],
    bbox: BBox | None,
    confidence: float,
    finding_type: str | None = None,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        rule_pack_id=pack.pack_id,
        rule_pack_version=pack.version,
        scope=pack.scope,
        target_kind=target_kind,
        target_id=target_id,
        outcome=outcome,
        confidence=confidence,
        reason=reason,
        evidence=evidence,
        bbox=bbox,
        severity=rule.severity,
        category=rule.category,
        finding_type=finding_type or rule.finding_type,
    )


def evaluate(pack: RulePack, snapshot: dict) -> list[RuleEvaluation]:
    views = list(snapshot.get("views", []))
    results: list[RuleEvaluation] = []

    for rule in pack.rules:
        if rule.target == "sheet":
            results.append(_evaluate_sheet_rule(rule, pack, snapshot, views))
            continue

        for view in views:
            results.append(_evaluate_view_rule(rule, pack, view))

    return results


def _evaluate_sheet_rule(
    rule: Rule,
    pack: RulePack,
    snapshot: dict,
    views: list[dict],
) -> RuleEvaluation:
    bbox = _sheet_bbox(snapshot)

    if rule.check == "sheet_has_view":
        has_views = bool(views)
        return _result(
            rule,
            pack,
            target_kind="sheet",
            target_id=None,
            outcome=OUTCOME_PASS if has_views else OUTCOME_FAIL,
            reason="" if has_views else "Nenhuma view foi segmentada nesta folha.",
            evidence=[f"views detectadas: {len(views)}"],
            bbox=bbox,
            confidence=0.9,
        )

    if rule.check == "category_matches_views":
        title_block = snapshot.get("title_block", {})
        title = normalize(str(title_block.get("title") or ""))
        category = normalize(str(title_block.get("category") or ""))
        announced = sorted({kind for term, kind in ANNOUNCED_CONTENT if term in title})

        if not announced or not views:
            return _result(
                rule,
                pack,
                target_kind="sheet",
                target_id=None,
                outcome=OUTCOME_UNKNOWN,
                reason="O carimbo nao anuncia um conteudo reconhecivel, ou nao ha view para comparar.",
                evidence=[
                    f"categoria: {category or 'ausente'}",
                    f"titulo: {title or 'ausente'}",
                    f"views: {len(views)}",
                ],
                bbox=bbox,
                confidence=0.4,
                finding_type="unverifiable",
            )

        present = {view["view_kind"] for view in views}
        missing = [kind for kind in announced if kind not in present]
        coherent = not missing
        return _result(
            rule,
            pack,
            target_kind="sheet",
            target_id=None,
            outcome=OUTCOME_PASS if coherent else OUTCOME_FAIL,
            reason=(
                ""
                if coherent
                else f"O carimbo anuncia {', '.join(missing)}, mas nenhuma view e desse tipo."
            ),
            evidence=[
                f"categoria: {category}",
                f"titulo: {title}",
                f"anunciado: {announced}",
                f"tipos: {sorted(present)}",
            ],
            bbox=bbox,
            confidence=0.7,
        )

    if rule.check == "unique_view_identifiers":
        keys = [_identity_key(view) for view in views if _identity_key(view)]
        duplicated = sorted({key for key in keys if keys.count(key) > 1})
        return _result(
            rule,
            pack,
            target_kind="sheet",
            target_id=None,
            outcome=OUTCOME_FAIL if duplicated else OUTCOME_PASS,
            reason=(
                f"Identificadores repetidos: {', '.join(duplicated)}" if duplicated else ""
            ),
            evidence=[f"identificadores: {keys}"],
            bbox=bbox,
            confidence=0.85,
        )

    return _result(
        rule,
        pack,
        target_kind="sheet",
        target_id=None,
        outcome=OUTCOME_UNKNOWN,
        reason=f"Check nao implementado: {rule.check}",
        evidence=[],
        bbox=bbox,
        confidence=0.0,
        finding_type="unverifiable",
    )


def _identity_key(view: dict) -> str | None:
    """Chave de identidade de uma view para deteccao de duplicidade.

    Agrupamentos equivalentes como `P21=P38` e `P28=P37` sao detalhamentos
    intencionalmente equivalentes, nao duplicidade - entao o titulo entra na
    chave quando ele declara a equivalencia.
    """
    title = normalize(str(view.get("title_raw") or ""))
    identifier = view.get("identifier")

    if "=" in title:
        return title

    if identifier:
        return str(identifier)

    return title or None


def _has_technical_scale(view: dict) -> bool:
    if view.get("declared_scale"):
        return True

    return TECHNICAL_NON_NUMERIC_SCALE in normalize(str(view.get("declared_scale_raw") or ""))


def _evaluate_view_rule(rule: Rule, pack: RulePack, view: dict) -> RuleEvaluation:
    view_id = str(view.get("id") or "")
    bbox = _bbox(view)

    if rule.applies_to_view_kinds and view["view_kind"] not in rule.applies_to_view_kinds:
        return _result(
            rule,
            pack,
            target_kind="view",
            target_id=view_id,
            outcome=OUTCOME_NOT_APPLICABLE,
            reason=f"Regra vale para {', '.join(rule.applies_to_view_kinds)}.",
            evidence=[f"view_kind: {view['view_kind']}"],
            bbox=bbox,
            confidence=1.0,
        )

    if rule.check == "view_has_title" and view.get("view_role") in ROLES_EXEMPT_FROM_TITLE:
        return _result(
            rule,
            pack,
            target_kind="view",
            target_id=view_id,
            outcome=OUTCOME_NOT_APPLICABLE,
            reason="Subview nao precisa repetir o titulo do detalhe agrupador.",
            evidence=[f"view_role: {view.get('view_role')}"],
            bbox=bbox,
            confidence=1.0,
        )

    checks = {
        "view_has_title": ("title_raw", lambda v: bool(v.get("title_raw"))),
        "view_has_technical_scale": ("declared_scale_raw", _has_technical_scale),
        "view_has_level": ("level_raw", lambda v: bool(v.get("level_raw"))),
    }

    if rule.check not in checks:
        return _result(
            rule,
            pack,
            target_kind="view",
            target_id=view_id,
            outcome=OUTCOME_UNKNOWN,
            reason=f"Check nao implementado: {rule.check}",
            evidence=[],
            bbox=bbox,
            confidence=0.0,
            finding_type="unverifiable",
        )

    field, predicate = checks[rule.check]

    # Confianca baixa na segmentacao torna a ausencia nao verificavel, nao um erro.
    if float(view.get("confidence", 1.0)) < MIN_VIEW_CONFIDENCE:
        return _result(
            rule,
            pack,
            target_kind="view",
            target_id=view_id,
            outcome=OUTCOME_UNKNOWN,
            reason="Segmentacao da view pouco confiavel para afirmar ausencia.",
            evidence=[f"confianca da view: {view.get('confidence')}"],
            bbox=bbox,
            confidence=0.3,
            finding_type="unverifiable",
        )

    satisfied = predicate(view)
    return _result(
        rule,
        pack,
        target_kind="view",
        target_id=view_id,
        outcome=OUTCOME_PASS if satisfied else OUTCOME_FAIL,
        reason="" if satisfied else rule.description,
        evidence=[f"{field}: {view.get(field) or 'ausente'}"],
        bbox=bbox,
        confidence=0.85,
    )
