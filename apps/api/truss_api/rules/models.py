from dataclasses import dataclass, field


BBox = tuple[float, float, float, float]

OUTCOME_PASS = "PASS"
OUTCOME_FAIL = "FAIL"
OUTCOME_UNKNOWN = "UNKNOWN"
OUTCOME_NOT_APPLICABLE = "NOT_APPLICABLE"
OUTCOME_SKIPPED = "SKIPPED"

VALID_OUTCOMES = frozenset(
    {OUTCOME_PASS, OUTCOME_FAIL, OUTCOME_UNKNOWN, OUTCOME_NOT_APPLICABLE, OUTCOME_SKIPPED}
)

# A politica humana separa o que qualquer projeto deveria cumprir do que e
# preferencia do proprietario. Os dois vivem em packs distintos para que uma
# preferencia nunca seja apresentada como norma.
SCOPE_GENERAL = "general"
SCOPE_PERSONAL = "personal"

VALID_SCOPES = frozenset({SCOPE_GENERAL, SCOPE_PERSONAL})


@dataclass(frozen=True)
class Rule:
    rule_id: str
    version: str
    check: str
    target: str
    severity: str
    category: str
    finding_type: str
    description: str
    applies_to_view_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class RulePack:
    pack_id: str
    version: str
    sheet_type: str
    technical_scope: str
    scope: str
    rules: list[Rule] = field(default_factory=list)


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    rule_version: str
    rule_pack_id: str
    rule_pack_version: str
    technical_scope: str
    scope: str
    target_kind: str
    target_id: str | None
    outcome: str
    confidence: float
    reason: str
    evidence: list[str]
    bbox: BBox | None
    severity: str
    category: str
    finding_type: str
    view_id: str | None = None
    element_code: str | None = None
    registry_hash: str | None = None
    # Contexto estavel adicional para regras que podem avaliar o mesmo codigo
    # em mais de um nivel da mesma folha. Participa apenas do dedupe.
    dedupe_discriminator: str | None = None
