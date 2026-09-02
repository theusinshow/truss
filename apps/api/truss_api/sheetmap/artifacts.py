from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from truss_api.core.settings import Settings
from truss_api.sheetmap.primitives import (
    EXTRACTOR_VERSION,
    PageExtraction,
    PageMetadata,
    TextSpanRecord,
    VectorPrimitive,
)
from truss_api.recovery.atomic import atomic_write_bytes


GZIP_LEVEL = 6


def _payload(extraction: PageExtraction) -> dict[str, object]:
    return {
        "extractor_version": EXTRACTOR_VERSION,
        "metadata": asdict(extraction.metadata),
        "primitives": [asdict(primitive) for primitive in extraction.primitives],
        "spans": [asdict(span) for span in extraction.spans],
    }


def artifact_hash(extraction: PageExtraction) -> str:
    canonical = json.dumps(_payload(extraction), sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def extraction_relative_path(
    project_id: str,
    revision_id: str,
    sheet_id: str,
    content_hash: str,
) -> str:
    return f"geometry/{project_id}/{revision_id}/{sheet_id}.{content_hash}.json.gz"


def write_extraction(
    extraction: PageExtraction,
    *,
    project_id: str,
    revision_id: str,
    sheet_id: str,
    settings: Settings,
) -> str:
    content_hash = artifact_hash(extraction)
    relative = extraction_relative_path(project_id, revision_id, sheet_id, content_hash)
    target = settings.data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)

    # Enderecado por conteudo: se o arquivo ja existe, ele e identico por definicao.
    if not target.exists():
        raw = json.dumps(_payload(extraction), separators=(",", ":")).encode("utf-8")
        atomic_write_bytes(
            target,
            gzip.compress(raw, GZIP_LEVEL),
            validator=lambda path: json.loads(
                gzip.decompress(path.read_bytes()).decode("utf-8")
            ),
        )

    return relative


def read_extraction(relative_path: str, settings: Settings) -> PageExtraction:
    source = Path(settings.data_dir / relative_path)
    payload = json.loads(gzip.decompress(source.read_bytes()).decode("utf-8"))
    metadata = payload["metadata"]

    return PageExtraction(
        metadata=PageMetadata(
            width_pt=metadata["width_pt"],
            height_pt=metadata["height_pt"],
            rotation=metadata["rotation"],
            mediabox=tuple(metadata["mediabox"]),
            cropbox=tuple(metadata["cropbox"]),
            rotation_matrix=tuple(metadata["rotation_matrix"]),
        ),
        primitives=[
            VectorPrimitive(
                kind=item["kind"],
                points=[tuple(point) for point in item["points"]],
                rect=tuple(item["rect"]),
                width=item["width"],
                color=tuple(item["color"]) if item["color"] else None,
                dashes=item["dashes"],
            )
            for item in payload["primitives"]
        ],
        spans=[
            TextSpanRecord(
                text=item["text"],
                bbox=tuple(item["bbox"]),
                font=item["font"],
                size=item["size"],
                dir=tuple(item["dir"]),
            )
            for item in payload["spans"]
        ],
    )
