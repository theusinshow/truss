from hashlib import sha256
import re
import unicodedata


POLICY_VERSION = "learning-policy-v0.1"
UNCLASSIFIED_SHEET_TYPES = {"", "unknown", "nao_classificada", "not_verifiable"}


def is_classified_sheet_type(sheet_type: str) -> bool:
    return sheet_type.strip().lower() not in UNCLASSIFIED_SHEET_TYPES


def normalize_manual_description(description: str) -> str:
    normalized = unicodedata.normalize("NFKC", description).casefold().strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" \t\r\n.,;:!?-_()[]{}\"'")


def stable_key(material: str) -> str:
    return sha256(material.encode("utf-8")).hexdigest()


def automatic_key(sheet_type: str, rule_id: str) -> str:
    return stable_key(f"auto|{sheet_type.strip().lower()}|{rule_id.strip()}")


def manual_key(
    sheet_type: str,
    category: str,
    finding_type: str,
    description: str,
) -> tuple[str, str]:
    normalized = normalize_manual_description(description)
    material = "|".join(
        [
            "manual",
            sheet_type.strip().lower(),
            category.strip().lower(),
            finding_type.strip().lower(),
            normalized,
        ]
    )
    return stable_key(material), normalized
