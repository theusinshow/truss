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
    dedupe_discriminator: str | None = None,
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
        dedupe_discriminator=dedupe_discriminator,
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
    if rule.check == "pillar_lifecycle_continuity":
        return _evaluate_pillar_lifecycle_rule(rule, pack, snapshot, registry)

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


def _evaluate_pillar_lifecycle_rule(
    rule: Rule,
    pack: RulePack,
    snapshot: dict,
    registry: dict[str, object] | None,
) -> list[RuleEvaluation]:
    explicit = [
        element
        for element in snapshot.get("elements", [])
        if element.get("element_kind") == "pillar"
        and element.get("technical_scope") == pack.technical_scope
        and str((element.get("attributes") or {}).get("lifecycle_state") or "")
        in {"morre", "nasce", "passa"}
    ]
    if not explicit:
        return [
            _result(
                rule,
                pack,
                target_kind="element",
                target_id=None,
                outcome=OUTCOME_NOT_APPLICABLE,
                reason="Nenhum pilar com lifecycle explicito foi localizado nesta folha.",
                evidence=["estados explicitos: 0"],
                bbox=_sheet_bbox(snapshot),
                confidence=1.0,
            )
        ]

    registry = registry or {}
    registry_hash = str(registry.get("registry_hash") or "") or None
    levels = {
        str(item["view_id"]): item for item in registry.get("form_levels", [])
    }
    next_pair = {
        str(item["lower_view_id"]): item
        for item in registry.get("form_level_pairs", [])
    }
    previous_pair = {
        str(item["upper_view_id"]): item
        for item in registry.get("form_level_pairs", [])
    }
    occurrences_by_view: dict[str, list[dict]] = {}
    for occurrence in registry.get("occurrences", []):
        view_id = str(occurrence.get("view_id") or "")
        if (
            view_id
            and occurrence.get("element_kind") == "pillar"
            and occurrence.get("technical_scope") == pack.technical_scope
            and float(occurrence.get("confidence") or 0.0) >= MIN_VIEW_CONFIDENCE
        ):
            occurrences_by_view.setdefault(view_id, []).append(occurrence)

    grouped: dict[tuple[str, str], list[dict]] = {}
    for element in explicit:
        key = (str(element.get("code") or ""), str(element.get("view_id") or ""))
        grouped.setdefault(key, []).append(element)

    results: list[RuleEvaluation] = []
    for (code, source_view_id), elements in sorted(grouped.items()):
        source = elements[0]
        attributes = source.get("attributes") or {}
        states = {
            str((item.get("attributes") or {}).get("lifecycle_state") or "")
            for item in elements
        }
        source_level = levels.get(source_view_id)
        state = next(iter(states)) if len(states) == 1 else "ambiguous"
        pair = (
            previous_pair.get(source_view_id)
            if state == "nasce"
            else next_pair.get(source_view_id)
        )
        target_view_id = None
        if pair is not None:
            target_view_id = str(
                pair["lower_view_id"] if state == "nasce" else pair["upper_view_id"]
            )
        target_level = levels.get(target_view_id or "")
        target_occurrences = occurrences_by_view.get(target_view_id or "", [])
        target_codes = {str(item["code"]) for item in target_occurrences}
        matching_target = [
            item for item in target_occurrences if str(item.get("code") or "") == code
        ]

        source_raw = str(attributes.get("source_text") or source.get("code_raw") or code)
        common = [
            f"estado: {state}",
            f"origem: {source_raw} em sheet_map={snapshot.get('id')} view={source_view_id or 'ambigua'}",
            f"nivel origem: {(source_level or {}).get('level_raw') or 'ausente'}",
            (
                "alvo: "
                f"folha={(target_level or {}).get('sheet_code') or (target_level or {}).get('sheet_code_raw') or 'ausente'} "
                f"view={target_view_id or 'ausente'} "
                f"nivel={(target_level or {}).get('level_raw') or 'ausente'}"
            ),
            f"pareamento: {(pair or {}).get('provenance') or 'ausente'}",
            f"codigos no alvo: {sorted(target_codes)}",
            f"registry_hash: {registry_hash or 'ausente'}",
        ]
        if matching_target:
            common.append(
                "ocorrencias alvo: "
                + str(
                    [
                        {
                            "sheet_id": item.get("sheet_id"),
                            "view_id": item.get("view_id"),
                            "bbox": [
                                item.get("x0"),
                                item.get("y0"),
                                item.get("x1"),
                                item.get("y1"),
                            ],
                        }
                        for item in matching_target
                    ]
                )
            )

        if state == "ambiguous":
            outcome = OUTCOME_UNKNOWN
            reason = f"{code} possui estados de lifecycle conflitantes na mesma view."
            finding_type = "unverifiable"
            confidence = 0.3
        elif not source_view_id or source_level is None:
            outcome = OUTCOME_UNKNOWN
            reason = f"O nivel de origem de {code} nao pode ser associado com seguranca."
            finding_type = "unverifiable"
            confidence = 0.35
        elif pair is None or target_level is None:
            outcome = OUTCOME_UNKNOWN
            direction = "anterior" if state == "nasce" else "seguinte"
            reason = f"Nenhum nivel {direction} confiavel foi pareado para {code}."
            finding_type = "unverifiable"
            confidence = 0.4
        elif not target_codes:
            outcome = OUTCOME_UNKNOWN
            reason = (
                "O nivel alvo foi reconhecido, mas seus pilares nao puderam "
                "ser extraidos por view."
            )
            finding_type = "unverifiable"
            confidence = 0.4
        else:
            present = code in target_codes
            contradiction = present if state in {"morre", "nasce"} else not present
            outcome = OUTCOME_FAIL if contradiction else OUTCOME_PASS
            finding_type = None
            source_raw_level = str(source_level["level_raw"])
            target_raw_level = str(target_level["level_raw"])
            if not contradiction:
                reason = ""
            elif state == "morre":
                reason = (
                    f"{code} esta marcado como MORRE no nivel {source_raw_level}, mas tambem "
                    f"foi localizado no proximo nivel observado, {target_raw_level}."
                )
            elif state == "nasce":
                reason = (
                    f"{code} esta marcado como NASCE no nivel {source_raw_level}, mas tambem "
                    f"foi localizado no nivel anterior observado, {target_raw_level}."
                )
            else:
                reason = (
                    f"{code} esta marcado como PASSA no nivel {source_raw_level}, mas nao foi "
                    f"localizado no proximo nivel observado, {target_raw_level}."
                )
            state_confidence = float(attributes.get("lifecycle_confidence") or 0.0)
            confidence = min(
                float(source.get("confidence") or 0.0),
                state_confidence,
                float(pair.get("confidence") or 0.0),
            ) * (0.9 if contradiction else 1.0)

        results.append(
            _result(
                rule,
                pack,
                target_kind="element",
                target_id=str(source.get("id") or ""),
                outcome=outcome,
                reason=reason,
                evidence=common,
                bbox=_bbox(source),
                confidence=confidence,
                finding_type=finding_type,
                view_id=source_view_id or None,
                element_code=code,
                registry_hash=registry_hash,
                dedupe_discriminator=(
                    f"{state}|{(source_level or {}).get('level_raw') or 'unknown'}"
                ),
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
