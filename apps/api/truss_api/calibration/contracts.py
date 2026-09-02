from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from truss_api.audit.orchestrator import AUDIT_PIPELINE_VERSION
from truss_api.calibration.catalog import find_reference_pdf, load_ground_truths
from truss_api.rules.loader import PACKS_DIR
from truss_api.sheetmap.snapshot import SHEET_MAP_PIPELINE


MANIFEST_VERSION = "corpus-manifest-v0.1"
POLICY_VERSION = "corpus-calibration-policy-v0.1"


@dataclass(frozen=True)
class CorpusDocument:
    sha256: str
    filename: str
    page_count: int
    authority: str
    source: str
    path: Path

    def public(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("path")
        return payload


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_payload(payload: Any) -> str:
    return sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_corpus_manifest(
    *,
    approved_dir: Path,
    catalog_path: Path,
    ground_truth_dir: Path,
) -> tuple[dict[str, object], list[CorpusDocument]]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    by_hash = {str(item["sha256"]): item for item in catalog}
    documents: dict[str, CorpusDocument] = {}

    for path in sorted(approved_dir.glob("*.pdf")):
        content_hash = file_hash(path)
        entry = by_hash.get(content_hash)
        if entry is None:
            raise ValueError(f"Approved PDF is absent from catalog: {path.name}")
        documents[content_hash] = CorpusDocument(
            sha256=content_hash,
            filename=path.name,
            page_count=int(entry["pages"]),
            authority="delivered_reference",
            source="knowledge_inbox_approved",
            path=path,
        )

    for truth in load_ground_truths(ground_truth_dir):
        if not truth.is_human_verified:
            continue
        path = find_reference_pdf(truth)
        if path is None:
            raise ValueError(f"Human-verified reference PDF not found: {truth.filename}")
        content_hash = file_hash(path)
        if truth.sha256 and content_hash != truth.sha256:
            raise ValueError(f"Human-verified PDF hash mismatch: {truth.filename}")
        documents[content_hash] = CorpusDocument(
            sha256=content_hash,
            filename=truth.filename or path.name,
            page_count=int(truth.page_count or 0),
            authority="human_verified_ground_truth",
            source=truth.path.name,
            path=path,
        )

    ordered = sorted(documents.values(), key=lambda item: (item.sha256, item.filename))
    manifest: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "documents": [item.public() for item in ordered],
        "document_count": len(ordered),
        "page_count": sum(item.page_count for item in ordered),
    }
    manifest["hash"] = digest_payload(manifest)
    return manifest, ordered


def rule_pack_digest(packs_dir: Path = PACKS_DIR) -> str:
    files = [
        {"name": path.name, "sha256": file_hash(path)}
        for path in sorted(packs_dir.glob("*.v*.yml"))
    ]
    return digest_payload(files)


def preference_digest(preferences: Iterable[dict[str, object]]) -> str:
    normalized = sorted(
        (
            {
                "scope": str(item["scope"]),
                "sheet_type": str(item["sheet_type"]),
                "rule_id": str(item["rule_id"]),
                "action": str(item["action"]),
            }
            for item in preferences
        ),
        key=lambda item: (item["scope"], item["sheet_type"], item["rule_id"], item["action"]),
    )
    return digest_payload(normalized)


def analysis_key(manifest_hash: str, pack_digest: str) -> str:
    return digest_payload(
        {
            "manifest": manifest_hash,
            "sheetmap": SHEET_MAP_PIPELINE,
            "audit": AUDIT_PIPELINE_VERSION,
            "rule_packs": pack_digest,
            "policy": POLICY_VERSION,
        }
    )


def run_key(raw_analysis_key: str, active_preference_digest: str) -> str:
    return digest_payload(
        {"analysis_key": raw_analysis_key, "preferences": active_preference_digest}
    )
