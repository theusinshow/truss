from __future__ import annotations

import json
from pathlib import Path

import fitz

from truss_api.calibration import repository
from truss_api.calibration.contracts import file_hash
from truss_api.core.settings import REPO_ROOT, Settings


class CalibrationPreviewError(Exception):
    pass


def render_evidence_preview(evidence_id: str, settings: Settings) -> Path:
    context = repository.evidence_preview_context(evidence_id, settings)
    document_hash = str(context.get("document_sha256") or "")
    page_index = context.get("page_index")
    if not document_hash or page_index is None:
        raise CalibrationPreviewError("Evidence has no page locator")

    report_path = settings.data_dir / str(context["artifact_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    allowed = {str(item["sha256"]) for item in report["manifest"]["documents"]}
    if document_hash not in allowed:
        raise CalibrationPreviewError("Evidence document is outside this run manifest")

    roots = (
        REPO_ROOT / "data" / "knowledge-inbox" / "approved",
        REPO_ROOT / "docs" / "projeto_base",
        REPO_ROOT / "data" / "originals",
    )
    source = next(
        (
            path
            for root in roots
            if root.exists()
            for path in sorted(root.rglob("*.pdf"))
            if file_hash(path) == document_hash
        ),
        None,
    )
    if source is None:
        raise CalibrationPreviewError("Local PDF for evidence was not found")

    output = settings.calibration_dir / "previews" / document_hash / f"{evidence_id}.png"
    if output.exists():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(source) as pdf:
        if int(page_index) < 0 or int(page_index) >= pdf.page_count:
            raise CalibrationPreviewError("Evidence page is outside the PDF")
        page = pdf.load_page(int(page_index))
        values = [context.get(key) for key in ("x0", "y0", "x1", "y1")]
        clip = page.rect
        if all(value is not None for value in values):
            x0, y0, x1, y1 = (float(value) for value in values)
            candidate = fitz.Rect(x0 - 24, y0 - 24, x1 + 24, y1 + 24) & page.rect
            if not candidate.is_empty:
                clip = candidate
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), clip=clip, alpha=False)
        pixmap.save(output)
    return output
