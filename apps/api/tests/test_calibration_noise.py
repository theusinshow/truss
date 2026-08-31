"""Piso de ruido do checklist sobre projetos aprovados.

Num projeto entregue e aprovado todo achado e candidato a falso positivo. Este
e o numero que decide se a lista de achados e utilizavel.
"""

from pathlib import Path

import fitz
import pytest

from truss_api.calibration.catalog import find_reference_pdf, load_ground_truths
from truss_api.calibration.noise import measure_project
from tests.factories import make_forms_sheet_pdf_bytes


def test_a_complete_forms_sheet_produces_no_noise(tmp_path: Path) -> None:
    path = tmp_path / "obra.pdf"
    path.write_bytes(make_forms_sheet_pdf_bytes())

    noise = measure_project(path)

    assert noise.pages == 1
    assert noise.total_views == 3
    assert noise.total_findings == 0
    assert noise.findings_per_sheet == 0.0


def test_noise_is_attributed_to_the_rule_that_produced_it(tmp_path: Path) -> None:
    """Sem saber qual regra gera o ruido, nao da para corrigir a regra certa."""
    document = fitz.open(stream=make_forms_sheet_pdf_bytes(), filetype="pdf")
    page = document.load_page(0)
    # Um titulo que anuncia planta numa folha cujas views serao so detalhes.
    page.add_redact_annot(fitz.Rect(150, 560, 900, 640))
    page.apply_redactions()
    path = tmp_path / "sem-planta.pdf"
    document.save(path)
    document.close()

    noise = measure_project(path)

    assert noise.total_findings > 0
    assert all(scope and rule_id for scope, rule_id in noise.by_rule())


def test_measures_every_approved_project_in_the_catalog() -> None:
    """Roda de verdade sobre o material presente no clone.

    O numero impresso e o piso de ruido: em projeto aprovado, achado e
    candidato a falso positivo ate prova em contrario.
    """
    measured = 0

    for truth in load_ground_truths():
        pdf_path = find_reference_pdf(truth)
        if pdf_path is None:
            continue

        noise = measure_project(pdf_path, name=truth.name)
        measured += 1

        print(
            f"\n[{noise.name}] {noise.pages} folhas | {noise.total_views} views"
            f" | {noise.total_findings} achados"
            f" | {noise.findings_per_sheet:.2f} por folha"
        )
        for (scope, rule_id), count in noise.by_rule().most_common():
            print(f"    {count:3d}x {scope}/{rule_id}")

    if measured == 0:
        pytest.skip("nenhum PDF de calibracao presente neste clone")

    assert measured >= 1
