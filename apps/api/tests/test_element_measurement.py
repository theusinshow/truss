from pathlib import Path

from truss_api.calibration.elements import measure_pdf
from tests.factories import make_cross_sheet_pillar_pdf_bytes


def test_measurement_exercises_real_import_registry_and_audit(tmp_path: Path) -> None:
    pdf = tmp_path / "pilares.pdf"
    pdf.write_bytes(make_cross_sheet_pillar_pdf_bytes(detail_codes=("P1",)))

    result = measure_pdf(pdf)

    assert result.pages == 2
    assert result.elements_by_kind == {"pillar": 3}
    assert result.cross_sheet_outcomes == {"FAIL": 1, "PASS": 1}
    assert [item["element_code"] for item in result.candidate_findings] == ["P2"]
    assert result.artifact_bytes > 0

