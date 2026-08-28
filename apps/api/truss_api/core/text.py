import re
import unicodedata


_WHITESPACE = re.compile(r"\s+")


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _WHITESPACE.sub(" ", without_accents).strip().upper()


def contains_term(haystack: str, term: str) -> bool:
    return normalize(term) in normalize(haystack)
