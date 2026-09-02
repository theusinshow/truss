from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.recovery.errors import TrussError


SOURCE_AVAILABLE = "AVAILABLE"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
SOURCE_RESTORED = "SOURCE_RESTORED"
_REASON_CODE = re.compile(r"^[a-z0-9][a-z0-9_]{2,63}$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _table_exists(connection: sqlite3.Connection) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_source_events'"
        ).fetchone()
        is not None
    )


def list_document_sources(connection: sqlite3.Connection) -> list[dict[str, object]]:
    if _table_exists(connection):
        event_join = """
        LEFT JOIN document_source_events source_event
          ON source_event.id = (
              SELECT candidate.id
              FROM document_source_events candidate
              WHERE candidate.document_id = d.id
              ORDER BY candidate.sequence DESC
              LIMIT 1
          )
        """
        event_columns = """
            source_event.id,
            source_event.status,
            source_event.reason_code,
            source_event.note,
            source_event.created_at
        """
    else:
        event_join = ""
        event_columns = "NULL, NULL, NULL, NULL, NULL"
    rows = connection.execute(
        f"""
        SELECT
            d.id,
            d.project_id,
            d.revision_id,
            d.original_filename,
            d.stored_file_path,
            d.content_hash,
            d.file_size_bytes,
            d.page_count,
            {event_columns}
        FROM documents d
        {event_join}
        ORDER BY d.stored_file_path, d.id
        """
    ).fetchall()
    return [
        {
            "document_id": str(row[0]),
            "project_id": str(row[1]),
            "revision_id": str(row[2]),
            "original_filename": str(row[3]),
            "stored_file_path": str(row[4]),
            "content_hash": str(row[5]),
            "file_size_bytes": int(row[6]),
            "page_count": int(row[7]),
            "event_id": str(row[8]) if row[8] is not None else None,
            "source_status": str(row[9]) if row[9] is not None else SOURCE_AVAILABLE,
            "reason_code": str(row[10]) if row[10] is not None else None,
            "note": str(row[11]) if row[11] is not None else None,
            "declared_at": str(row[12]) if row[12] is not None else None,
        }
        for row in rows
    ]


def unavailable_manifest_entry(source: dict[str, object]) -> dict[str, object]:
    return {
        "document_id": str(source["document_id"]),
        "revision_id": str(source["revision_id"]),
        "original_filename": str(source["original_filename"]),
        "stored_file_path": str(source["stored_file_path"]).replace("\\", "/"),
        "content_hash": str(source["content_hash"]),
        "file_size_bytes": int(source["file_size_bytes"]),
        "page_count": int(source["page_count"]),
        "status": SOURCE_UNAVAILABLE,
        "reason_code": str(source["reason_code"]),
        "note": str(source.get("note") or ""),
        "declared_at": str(source["declared_at"]),
    }


def _source_path(settings: Settings, relative: str) -> Path:
    target = (settings.data_dir / relative).resolve()
    if not target.is_relative_to(settings.data_dir.resolve()):
        raise TrussError(
            code="ARTIFACT_PATH_INVALID",
            message="O caminho persistido do PDF original e inseguro.",
            action="Nao altere o registro; execute o diagnostico local.",
            status_code=500,
        )
    return target


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_reason(reason_code: str) -> str:
    normalized = reason_code.strip().lower()
    if not _REASON_CODE.fullmatch(normalized):
        raise TrussError(
            code="SOURCE_REASON_INVALID",
            message="O codigo do motivo da indisponibilidade e invalido.",
            action="Use 3 a 64 caracteres: letras minusculas, numeros e underscore.",
            status_code=400,
        )
    return normalized


def _current_event(connection: sqlite3.Connection, document_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id, document_id, sequence, status, reason_code, note, created_at
        FROM document_source_events
        WHERE document_id = ?
        ORDER BY sequence DESC
        LIMIT 1
        """,
        (document_id,),
    ).fetchone()


def _event_dict(row: sqlite3.Row) -> dict[str, object]:
    return dict(row)


def declare_source_unavailable(
    document_id: str,
    *,
    reason_code: str,
    note: str,
    settings: Settings,
) -> dict[str, object]:
    reason = _validate_reason(reason_code)
    with transaction(settings) as connection:
        document = connection.execute(
            "SELECT stored_file_path, content_hash FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            raise TrussError(
                code="DOCUMENT_NOT_FOUND",
                message="O documento informado nao existe.",
                action="Consulte o diagnostico e use um document_id valido.",
                status_code=404,
            )
        source = _source_path(settings, str(document["stored_file_path"]))
        if source.is_file():
            if _hash_file(source) == str(document["content_hash"]):
                raise TrussError(
                    code="PDF_SOURCE_AVAILABLE",
                    message="O PDF original ainda esta disponivel e integro.",
                    action="Nao declare indisponibilidade para este documento.",
                    status_code=409,
                )
            raise TrussError(
                code="ARTIFACT_CORRUPT",
                message="Existe um arquivo no caminho original, mas o hash diverge.",
                action="Preserve o arquivo e investigue a divergencia antes de declarar a fonte.",
                status_code=409,
            )
        current = _current_event(connection, document_id)
        if current is not None and str(current["status"]) == SOURCE_UNAVAILABLE:
            return _event_dict(current)
        event_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO document_source_events (
                id, document_id, sequence, status, reason_code, note, created_at
            ) VALUES (
                ?, ?,
                (SELECT COALESCE(MAX(sequence), 0) + 1 FROM document_source_events WHERE document_id = ?),
                ?, ?, ?, ?
            )
            """,
            (
                event_id,
                document_id,
                document_id,
                SOURCE_UNAVAILABLE,
                reason,
                note.strip(),
                _now(),
            ),
        )
        created = _current_event(connection, document_id)
        assert created is not None
        return _event_dict(created)


def declare_source_restored(
    document_id: str,
    *,
    reason_code: str,
    note: str,
    settings: Settings,
) -> dict[str, object]:
    reason = _validate_reason(reason_code)
    with transaction(settings) as connection:
        document = connection.execute(
            "SELECT stored_file_path, content_hash FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        if document is None:
            raise TrussError(
                code="DOCUMENT_NOT_FOUND",
                message="O documento informado nao existe.",
                action="Use um document_id valido.",
                status_code=404,
            )
        source = _source_path(settings, str(document["stored_file_path"]))
        if not source.is_file():
            raise TrussError(
                code="PDF_SOURCE_MISSING",
                message="O PDF original ainda nao foi restaurado.",
                action="Reponha exatamente o arquivo esperado antes de registrar a restauracao.",
                status_code=409,
            )
        if _hash_file(source) != str(document["content_hash"]):
            raise TrussError(
                code="ARTIFACT_CORRUPT",
                message="O arquivo reposto nao corresponde ao hash historico.",
                action="Use o PDF original exato; nao substitua a revisao por outra versao.",
                status_code=409,
            )
        current = _current_event(connection, document_id)
        if current is None:
            raise TrussError(
                code="SOURCE_DECLARATION_MISSING",
                message="Este documento nao possui declaracao de indisponibilidade.",
                action="Nao e necessario registrar restauracao para uma fonte ja disponivel.",
                status_code=409,
            )
        if str(current["status"]) == SOURCE_RESTORED:
            return _event_dict(current)
        event_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO document_source_events (
                id, document_id, sequence, status, reason_code, note, created_at
            ) VALUES (
                ?, ?,
                (SELECT COALESCE(MAX(sequence), 0) + 1 FROM document_source_events WHERE document_id = ?),
                ?, ?, ?, ?
            )
            """,
            (
                event_id,
                document_id,
                document_id,
                SOURCE_RESTORED,
                reason,
                note.strip(),
                _now(),
            ),
        )
        created = _current_event(connection, document_id)
        assert created is not None
        return _event_dict(created)
