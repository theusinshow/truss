from truss_api.core.text import contains_term, normalize


def test_normalize_strips_accents_case_and_whitespace() -> None:
    assert normalize("  Planta de Locação\n  das Fundações  ") == (
        "PLANTA DE LOCACAO DAS FUNDACOES"
    )


def test_contains_term_is_accent_insensitive_in_both_directions() -> None:
    assert contains_term("PLANTA DE LOCACAO", "Locação") is True
    assert contains_term("Planta de Locação", "LOCACAO") is True
    assert contains_term("PLANTA DE FORMAS", "ARMADURAS") is False
