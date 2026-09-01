from pathlib import Path

from truss_api.calibration.continuity import measure_continuity
from tests.factories import make_pillar_continuity_pdf_bytes


def test_continuity_measurement_runs_real_disposable_pipeline(tmp_path: Path) -> None:
    pdf = tmp_path / "continuity.pdf"
    pdf.write_bytes(make_pillar_continuity_pdf_bytes())

    measurement = measure_continuity(pdf)

    assert measurement.pages == 2
    assert measurement.lifecycle_by_state == {"morre": 1}
    assert measurement.associated_lifecycle_by_state == {"morre": 1}
    assert measurement.form_levels == 2
    assert measurement.level_pairs_by_provenance == {
        "adjacent-sheet-code-overlap-v1": 1
    }
    assert measurement.outcomes["FAIL"] == 1
    assert len(measurement.candidate_findings) == 1
