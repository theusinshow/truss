from datetime import UTC, datetime
import json
from uuid import uuid4

from truss_api.core.settings import Settings
from truss_api.db.connection import transaction
from truss_api.vision.models import VisionAnalysis, VisionProviderResponse


VISION_CACHE_NAMESPACE = "vision"
VISION_USAGE_OPERATION = "vision.legibility"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def get_cached_response(cache_key: str, settings: Settings) -> VisionProviderResponse | None:
    with transaction(settings) as connection:
        row = connection.execute(
            "SELECT value FROM cache_entries WHERE cache_key = ? AND namespace = ?",
            (cache_key, VISION_CACHE_NAMESPACE),
        ).fetchone()
    if row is None:
        return None

    payload = json.loads(str(row["value"]))
    return VisionProviderResponse(
        provider=str(payload["provider"]),
        model=str(payload["model"]),
        analysis=VisionAnalysis.model_validate(payload["analysis"]),
        input_tokens=payload.get("input_tokens"),
        output_tokens=payload.get("output_tokens"),
        estimated_cost_usd=float(payload.get("estimated_cost_usd") or 0.0),
    )


def save_cached_response(
    cache_key: str,
    response: VisionProviderResponse,
    settings: Settings,
) -> None:
    payload = {
        "provider": response.provider,
        "model": response.model,
        "analysis": response.analysis.model_dump(),
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "estimated_cost_usd": response.estimated_cost_usd,
    }
    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO cache_entries (id, cache_key, namespace, value, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid4()), cache_key, VISION_CACHE_NAMESPACE, json.dumps(payload), _now()),
        )


def revision_usage(revision_id: str, settings: Settings) -> tuple[int, float]:
    with transaction(settings) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS calls, COALESCE(SUM(estimated_cost_usd), 0) AS cost
            FROM ai_usage_events
            WHERE revision_id = ? AND operation = ?
            """,
            (revision_id, VISION_USAGE_OPERATION),
        ).fetchone()
    return int(row["calls"]), float(row["cost"])


def record_usage(
    response: VisionProviderResponse,
    *,
    project_id: str,
    revision_id: str,
    sheet_id: str,
    settings: Settings,
) -> None:
    with transaction(settings) as connection:
        connection.execute(
            """
            INSERT INTO ai_usage_events (
                id, provider, model, operation, project_id, revision_id, sheet_id,
                input_tokens, output_tokens, estimated_cost_usd, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                response.provider,
                response.model,
                VISION_USAGE_OPERATION,
                project_id,
                revision_id,
                sheet_id,
                response.input_tokens,
                response.output_tokens,
                response.estimated_cost_usd,
                _now(),
            ),
        )
