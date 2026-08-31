from functools import lru_cache
from pathlib import Path

import yaml

from truss_api.rules.models import SCOPE_GENERAL, Rule, RulePack
from truss_api.rules.schema import validate_pack
from truss_api.sheetmap.technical_scopes import sheet_type_for_scope, scope_for_sheet_type


PACKS_DIR = Path(__file__).resolve().parent / "packs"


def _to_pack(payload: dict) -> RulePack:
    validate_pack(payload)

    return RulePack(
        pack_id=payload["pack_id"],
        version=payload["version"],
        sheet_type=payload["sheet_type"],
        technical_scope=scope_for_sheet_type(payload["sheet_type"]) or payload["sheet_type"],
        scope=payload["scope"],
        rules=[
            Rule(
                rule_id=rule["rule_id"],
                version=rule["version"],
                check=rule["check"],
                target=rule["target"],
                severity=rule["severity"],
                category=rule["category"],
                finding_type=rule["finding_type"],
                description=rule["description"],
                applies_to_view_kinds=tuple(rule.get("applies_to_view_kinds", ())),
            )
            for rule in payload["rules"]
        ],
    )


@lru_cache(maxsize=8)
def load_packs(sheet_type: str) -> tuple[RulePack, ...]:
    """Todos os packs que valem para um tipo de folha, um por escopo.

    O escopo esta dentro do arquivo, nao no nome: um pack declara para que tipo
    de folha e com que autoridade ele vale.
    """
    packs = [
        _to_pack(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(PACKS_DIR.glob("*.v*.yml"))
    ]

    return tuple(pack for pack in packs if pack.sheet_type == sheet_type)


def load_pack(sheet_type: str, scope: str = SCOPE_GENERAL) -> RulePack | None:
    return next(
        (pack for pack in load_packs(sheet_type) if pack.scope == scope),
        None,
    )


def load_packs_for_scopes(technical_scopes: list[str]) -> tuple[RulePack, ...]:
    packs: list[RulePack] = []
    seen: set[tuple[str, str]] = set()

    for technical_scope in technical_scopes:
        sheet_type = sheet_type_for_scope(technical_scope)
        if not sheet_type:
            continue
        for pack in load_packs(sheet_type):
            key = (pack.pack_id, pack.scope)
            if key not in seen:
                packs.append(pack)
                seen.add(key)

    return tuple(packs)
