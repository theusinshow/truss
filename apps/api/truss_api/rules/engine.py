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
from truss_api.sheetmap.elements.registry import pillar_detail_views


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
    view_id: str | None = None,
    element_code: str | None = None,
    registry_hash: str | None = None,
) -> RuleEvaluation:
    return RuleEvaluation(
        rule_id=rule.rule_id,
        rule_version=rule.version,
        rule_pack_id=pack.pack_id,
        rule_pack_version=pack.version,
        technical_scope=pack.technical_scope,
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
        view_id=view_id,
        element_code=element_code,
        registry_hash=registry_hash,
    )


def evaluate(
    pack: RulePack,
    snapshot: dict,
    registry: dict[str, object] | None = None,
) -> list[RuleEvaluation]:
    views = _views_for_pack(pack, snapshot)
    results: list[RuleEvaluation] = []

    for rule in pack.rules:
        if rule.target == "sheet":
            results.append(_evaluate_sheet_rule(rule, pack, snapshot, views))
            continue

        if rule.target == "element":
            results.extend(_evaluate_element_rule(rule, pack, snapshot, registry))
            continue

        for view in views:
            results.append(_evaluate_view_rule(rule, pack, view))

    return results


def _evaluate_element_rule(
    rule: Rule,
    pack: RulePack,
    snapshot: dict,
    registry: dict[str, object] | None,
) -> list[RuleEvaluation]:
    if rule.check != "pillar_has_detail":
        return [
            _result(
                rule,
                pack,
                target_kind="element",
                target_id=None,
                outcome=OUTCOME_UNKNOWN,
                reason=f"Check nao implementado: {rule.check}",
                evidence=[],
                bbox=_sheet_bbox(snapshot),
                confidence=0.0,
                finding_type="unverifiable",
            )
        ]

    source = [
        element
        for element in snapshot.get("elements", [])
        if element.get("element_kind") == "pillar"
        and element.get("technical_scope") == pack.technical_scope
        and element.get("view_id")
    ]
    by_code: dict[str, dict] = {}
    for element in source:
        by_code.setdefault(str(element["code"]), element)

    if not by_code:
        return [
            _result(
                rule,
                pack,
                target_kind="element",
                target_id=None,
                outcome=OUTCOME_NOT_APPLICABLE,
                reason="Nenhum pilar associado a uma view de formas nesta folha.",
                evidence=["pilares fonte: 0"],
                bbox=_sheet_bbox(snapshot),
                confidence=1.0,
            )
        ]

    registry_hash = str((registry or {}).get("registry_hash") or "") or None
    targets = pillar_detail_views(registry or {})
    target_ids = {str(view["id"]) for view in targets}
    target_map_ids = {
        str(view["sheet_map_id"]) for view in targets if view.get("sheet_map_id")
    }
    target_occurrences = [
        item
        for item in (registry or {}).get("occurrences", [])
        if item.get("element_kind") == "pillar"
        and (
            str(item.get("view_id") or "") in target_ids
            or (
                bool(item.get("sheet_map_id"))
                and str(item["sheet_map_id"]) in target_map_ids
            )
        )
        and float(item.get("confidence") or 0.0) >= MIN_VIEW_CONFIDENCE
    ]
    target_codes = {str(item["code"]) for item in target_occurrences}
    target_sheets = sorted(
        {
            str(view.get("sheet_code") or view.get("sheet_code_raw") or f"pagina {int(view.get('page_index') or 0) + 1}")
            for view in targets
        }
    )

    results: list[RuleEvaluation] = []
    for code, element in sorted(by_code.items()):
        source_evidence = (
            f"origem: {element.get('code_raw')} em sheet_map={snapshot.get('id')} "
            f"view={element.get('view_id')}"
        )
        common = [
            source_evidence,
            f"alvos pesquisados: {target_sheets or ['nenhum']}",
            f"codigos nos alvos: {sorted(target_codes)}",
            f"registry_hash: {registry_hash or 'ausente'}",
        ]

        if not targets:
            outcome = OUTCOME_UNKNOWN
            reason = "Nenhum detalhamento de pilares confiavel foi reconhecido nesta revisao."
            finding_type = "unverifiable"
            confidence = 0.35
        elif not target_codes:
            outcome = OUTCOME_UNKNOWN
            reason = "O detalhamento de pilares foi reconhecido, mas seus codigos nao puderam ser extraidos."
            finding_type = "unverifiable"
            confidence = 0.4
        elif code in target_codes:
            outcome = OUTCOME_PASS
            reason = ""
            finding_type = None
            confidence = min(float(element.get("confidence") or 0.0), 0.9)
        else:
            outcome = OUTCOME_FAIL
            reason = (
                f"{code} foi lido na forma, mas nao foi localizado nos detalhamentos "
                "de pilares desta revisao."
            )
            finding_type = None
            target_confidence = min(float(view.get("confidence") or 0.0) for view in targets)
            confidence = min(float(element.get("confidence") or 0.0), target_confidence) * 0.85

        results.append(
            _result(
                rule,
                pack,
                target_kind="element",
                target_id=str(element.get("id") or ""),
                outcome=outcome,
                reason=reason,
                evidence=common,
                bbox=_bbox(element),
                confidence=confidence,
                finding_type=finding_type,
                view_id=str(element.get("view_id") or "") or None,
                element_code=code,
                registry_hash=registry_hash,
            )
        )

    return results


def _snapshot_scopes(snapshot: dict) -> set[str]:
    return {
        str(item.get("technical_scope"))
        for item in snapshot.get("technical_scopes", [])
        if item.get("technical_scope")
    }


def _views_for_pack(pack: RulePack, snapshot: dict) -> list[dict]:
    views = list(snapshot.get("views", []))
    scopes = _snapshot_scopes(snapshot)

    # Snapshot legado ou folha de escopo unico: o comportamento anterior e
    # preservado, inclusive para views que ainda nao carregam o novo campo.
    if len(scopes) <= 1:
        return [
            view
            for view in views
            if not view.get("technical_scope")
            or view.get("technical_scope") == pack.technical_scope
        ]

    # Em folha mista, uma regra nunca atravessa para a view do outro escopo.
    # View ambigua fica fora e sustenta UNKNOWN nas regras de folha.
    return [
        view for view in views if view.get("technical_scope") == pack.technical_scope
    ]


def _has_ambiguous_views(pack: RulePack, snapshot: dict) -> bool:
    return (
        len(_snapshot_scopes(snapshot)) > 1
        and pack.technical_scope in _snapshot_scopes(snapshot)
        and any(not view.get("technical_scope") for view in snapshot.get("views", []))
    )


def _evaluate_sheet_rule(
    rule: Rule,
    pack: RulePack,
    snapshot: dict,
    views: list[dict],
) -> RuleEvaluation:
    bbox = _sheet_bbox(snapshot)

    if rule.check == "sheet_has_view":
        has_views = bool(views)
        ambiguous = not has_views and _has_ambiguous_views(pack, snapshot)
        return _result(
            rule,
            pack,
            target_kind="sheet",
            target_id=None,
            outcome=(OUTCOME_PASS if has_views else OUTCOME_UNKNOWN if ambiguous else OUTCOME_FAIL),
            reason=(
                ""
                if has_views
                else "Ha views sem escopo tecnico confiavel nesta folha mista."
                if ambiguous
                else "Nenhuma view foi segmentada nesta folha."
            ),
            evidence=[f"views detectadas: {len(views)}"],
            bbox=bbox,
            confidence=0.4 if ambiguous else 0.9,
            finding_type="unverifiable" if ambiguous else None,
        )

    if rule.check == "category_matches_views":
        title_block = snapshot.get("title_block", {})
        title = normalize(str(title_block.get("title") or ""))
        category = normalize(str(title_block.get("category") or ""))

        if len(_snapshot_scopes(snapshot)) > 1:
            return _result(
                rule,
                pack,
                target_kind="sheet",
                target_id=None,
                outcome=OUTCOME_UNKNOWN,
                reason="O carimbo da folha mista nao esta segmentado por escopo tecnico.",
                evidence=[
                    f"escopos: {sorted(_snapshot_scopes(snapshot))}",
                    f"titulo: {title or 'ausente'}",
                ],
                bbox=bbox,
                confidence=0.4,
                finding_type="unverifiable",
            )

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
