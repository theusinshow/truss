from truss_api.rules.models import VALID_SCOPES


class RulePackSchemaError(Exception):
    pass


REQUIRED_PACK_FIELDS = ("pack_id", "version", "sheet_type", "scope", "rules")
REQUIRED_RULE_FIELDS = (
    "rule_id",
    "version",
    "check",
    "target",
    "severity",
    "category",
    "finding_type",
    "description",
)
VALID_TARGETS = frozenset({"sheet", "view"})
VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})

# Vocabulario ja usado por `findings.type`; um pack nao pode inventar um paralelo.
VALID_FINDING_TYPES = frozenset(
    {"inconsistency", "attention", "missing_information", "unverifiable"}
)


def validate_pack(payload: dict) -> None:
    missing = [name for name in REQUIRED_PACK_FIELDS if name not in payload]
    if missing:
        raise RulePackSchemaError(f"campos ausentes no pack: {', '.join(missing)}")

    if payload["scope"] not in VALID_SCOPES:
        raise RulePackSchemaError(f"scope invalido: {payload['scope']}")

    if not isinstance(payload["rules"], list) or not payload["rules"]:
        raise RulePackSchemaError("pack precisa de ao menos uma regra")

    seen: set[str] = set()
    for rule in payload["rules"]:
        absent = [name for name in REQUIRED_RULE_FIELDS if name not in rule]
        if absent:
            raise RulePackSchemaError(
                f"regra {rule.get('rule_id', '?')} sem campos: {', '.join(absent)}"
            )

        if rule["rule_id"] in seen:
            raise RulePackSchemaError(f"rule_id duplicado: {rule['rule_id']}")
        seen.add(rule["rule_id"])

        if rule["target"] not in VALID_TARGETS:
            raise RulePackSchemaError(f"target invalido em {rule['rule_id']}")
        if rule["severity"] not in VALID_SEVERITIES:
            raise RulePackSchemaError(f"severity invalida em {rule['rule_id']}")
        if rule["finding_type"] not in VALID_FINDING_TYPES:
            raise RulePackSchemaError(f"finding_type invalido em {rule['rule_id']}")
