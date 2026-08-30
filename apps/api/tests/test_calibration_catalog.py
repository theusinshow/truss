"""Catalogo de gabaritos de calibracao.

Um gabarito por projeto. O catalogo existe para que acrescentar um projeto seja
soltar um PDF e um YAML na pasta, sem tocar em nenhum teste.
"""

from pathlib import Path

import pytest
import yaml

from truss_api.calibration.catalog import (
    REPO_ROOT,
    GroundTruth,
    find_reference_pdf,
    load_ground_truths,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_discovers_every_ground_truth_in_the_repository() -> None:
    truths = load_ground_truths()

    names = {truth.path.name for truth in truths}
    assert "juliano-corbellini-r05.yml" in names
    assert "rancho-queimado-r01.yml" in names


def test_a_ground_truth_without_a_declared_status_is_never_human_verified(
    tmp_path: Path,
) -> None:
    """O gabarito da F1 foi gerado da saida do proprio pipeline.

    Tratar um arquivo sem `status` como verificado transformaria um detector de
    regressao em prova de correcao.
    """
    _write(
        tmp_path / "legado.yml",
        {"document": {"filename": "x.pdf", "page_count": 2}, "sheets": []},
    )

    truth = load_ground_truths(tmp_path)[0]

    assert truth.status == "legacy"
    assert truth.is_human_verified is False


def test_reads_status_thresholds_and_sheets_of_a_v3_ground_truth(tmp_path: Path) -> None:
    _write(
        tmp_path / "obra.yml",
        {
            "version": 3,
            "status": "human_verified",
            "document": {"filename": "obra.pdf", "sha256": "abc", "page_count": 4},
            "thresholds": {"view_attribute_accuracy": 0.9},
            "sheets": [{"page_index": 0, "views": []}],
        },
    )

    truth = load_ground_truths(tmp_path)[0]

    assert truth.is_human_verified is True
    assert truth.sha256 == "abc"
    assert truth.thresholds["view_attribute_accuracy"] == 0.9
    assert len(truth.sheets) == 1


def test_finds_the_pdf_by_content_hash_even_when_the_name_was_sanitized(
    tmp_path: Path,
) -> None:
    """A importacao troca espacos por hifens e prefixa o hash.

    Procurar pelo nome declarado no gabarito falha justamente no arquivo que o
    proprio Truss guardou.
    """
    from hashlib import sha256

    content = b"%PDF-1.4 conteudo de teste"
    digest = sha256(content).hexdigest()
    stored = tmp_path / "originals" / "p" / "r"
    stored.mkdir(parents=True)
    (stored / f"{digest[:16]}-Nome-Com-Hifens.pdf").write_bytes(content)

    truth = GroundTruth(
        path=tmp_path / "obra.yml",
        version=3,
        status="human_verified",
        filename="Nome Com Espacos.pdf",
        sha256=digest,
        page_count=1,
        thresholds={},
        sheets=[],
        payload={},
    )

    found = find_reference_pdf(truth, search_roots=[tmp_path])

    assert found is not None
    assert found.name.endswith("Nome-Com-Hifens.pdf")


def test_falls_back_to_the_declared_name_when_no_hash_is_declared(tmp_path: Path) -> None:
    (tmp_path / "obra.pdf").write_bytes(b"%PDF-1.4 x")

    truth = GroundTruth(
        path=tmp_path / "obra.yml",
        version=1,
        status="legacy",
        filename="obra.pdf",
        sha256=None,
        page_count=1,
        thresholds={},
        sheets=[],
        payload={},
    )

    assert find_reference_pdf(truth, search_roots=[tmp_path]) == tmp_path / "obra.pdf"


def test_returns_none_when_the_pdf_is_absent_so_the_suite_can_skip(tmp_path: Path) -> None:
    truth = GroundTruth(
        path=tmp_path / "obra.yml",
        version=3,
        status="human_verified",
        filename="ausente.pdf",
        sha256="0" * 64,
        page_count=1,
        thresholds={},
        sheets=[],
        payload={},
    )

    assert find_reference_pdf(truth, search_roots=[tmp_path]) is None


def test_the_base_project_pdf_is_found_by_its_declared_hash() -> None:
    """Prova que o casamento por hash funciona no material real do repositorio."""
    truth = next(
        t for t in load_ground_truths() if t.path.name == "juliano-corbellini-r05.yml"
    )

    found = find_reference_pdf(truth)

    if found is None:
        pytest.skip("PDF do projeto-base ausente neste clone.")

    assert found.exists()
    assert found.is_relative_to(REPO_ROOT)
