from pathlib import Path

from truss_api.calibration.sections import measure_sections
from tests.factories import make_pillar_section_transition_pdf_bytes


def test_section_measurement_runs_real_disposable_pipeline(tmp_path: Path) -> None:
    pdf = tmp_path / "sections.pdf"
    pdf.write_bytes(make_pillar_section_transition_pdf_bytes())

    measurement = measure_sections(pdf)

    assert measurement.pages == 2
    assert measurement.section_candidates == 8
    assert measurement.associated_sections == 8
    assert measurement.ambiguous_associations == 0
    assert measurement.resolved_view_codes == 8
    assert measurement.ambiguous_view_codes == 0
    assert measurement.sections_by_provenance == {"adjacent-label": 8}
    assert measurement.form_level_pairs == 1
    assert measurement.outcomes["PASS"] == 3
    assert measurement.outcomes["FAIL"] == 1
    assert len(measurement.attention_points) == 1
    assert measurement.attention_points[0]["element_code"] == "P1"
    assert measurement.artifact_bytes > 0
