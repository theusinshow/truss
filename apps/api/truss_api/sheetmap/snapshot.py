from dataclasses import asdict, is_dataclass
from hashlib import sha256
import json
from typing import Any


SHEET_MAP_PIPELINE = "sheetmap-v0.2"


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def snapshot_hash(
    *,
    sheet_type: str,
    sheet_code: str | None,
    title_block: dict[str, object],
    regions: list[object],
    views: list[object],
    extraction_hash: str,
) -> str:
    canonical = json.dumps(
        {
            "pipeline": SHEET_MAP_PIPELINE,
            "extraction": extraction_hash,
            "sheet_type": sheet_type,
            "sheet_code": sheet_code,
            "title_block": _plain(title_block),
            "regions": _plain(regions),
            "views": _plain(views),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()[:16]


def pipeline_version_for(content_hash: str) -> str:
    return f"{SHEET_MAP_PIPELINE}+{content_hash}"
