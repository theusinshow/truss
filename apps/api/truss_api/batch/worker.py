import argparse
import json
import time

from truss_api.core.settings import Settings, get_settings
from truss_api.db.schema import initialize_database
from truss_api.recovery.errors import TrussError
from truss_api.recovery.operations import (
    run_ai_sheet_review_operation,
    run_deterministic_audit_operation,
    run_sheet_map_operation,
    run_visual_audit_operation,
)
from truss_api.batch import repository


LOCAL_AUTO_RETRY_CODES = {"STORAGE_IO_ERROR"}


def _frozen_settings(item: dict[str, object], settings: Settings) -> Settings:
    batch = item.get("batch") or {}
    config = batch.get("config") if isinstance(batch, dict) else {}
    if not isinstance(config, dict):
        return settings
    allowed = {
        "ai_provider",
        "openai_model",
        "vision_budget_usd_per_revision",
        "vision_max_calls_per_revision",
        "vision_max_candidates_per_sheet",
        "vision_cost_reserve_usd_per_call",
        "vision_max_output_tokens",
        "openai_reasoning_effort",
        "ai_review_global_max_pixels",
        "ai_review_tile_max_pixels",
        "ai_review_tile_overlap_ratio",
    }
    aliases = {"provider": "ai_provider", "model": "openai_model"}
    updates = {
        aliases.get(key, key): value
        for key, value in config.items()
        if aliases.get(key, key) in allowed and value is not None
    }
    return settings.model_copy(update=updates) if updates else settings


def _batch_config(item: dict[str, object]) -> dict[str, object]:
    batch = item.get("batch") or {}
    config = batch.get("config") if isinstance(batch, dict) else {}
    return config if isinstance(config, dict) else {}


def process_next_item(settings: Settings) -> bool:
    item = repository.claim_next_item(settings)
    if item is None:
        return False
    item_id = str(item["id"])
    token = str(item["run_token"])
    phase = str(item["phase"])
    sheet_id = str(item["sheet_id"])
    config = _batch_config(item)
    operation_settings = _frozen_settings(item, settings)
    try:
        if phase == "sheet_map":
            run_sheet_map_operation(sheet_id, operation_settings)
        elif phase == "deterministic_audit":
            run_deterministic_audit_operation(sheet_id, operation_settings)
        elif phase == "visual_audit":
            if config.get("ai_review") is True:
                run_ai_sheet_review_operation(sheet_id, operation_settings)
            else:
                run_visual_audit_operation(sheet_id, operation_settings)
        else:
            raise RuntimeError(f"unsupported batch phase: {phase}")
        repository.complete_item(item_id, token, settings)
    except Exception as error:
        if isinstance(error, TrussError):
            code = error.public.code
            message = error.public.message
            if code in LOCAL_AUTO_RETRY_CODES and repository.requeue_transient_item(
                item_id,
                token,
                settings,
                code=code,
                message=message,
            ):
                return True
        else:
            code = "BATCH_ITEM_FAILED"
            message = "A folha nao pode ser concluida nesta fase."
        repository.fail_item(
            item_id,
            token,
            settings,
            code=code,
            message=message,
            manual_retry=phase == "visual_audit",
        )
    return True


def run_worker(settings: Settings, *, once: bool = False) -> int:
    initialize_database(settings)
    repository.mark_running_batches_interrupted(settings)
    processed = 0
    while True:
        worked = process_next_item(settings)
        if worked:
            processed += 1
        if once:
            return processed
        if not worked:
            time.sleep(settings.batch_poll_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Worker local de lotes do Truss")
    parser.add_argument("--once", action="store_true", help="Processa no maximo um item")
    args = parser.parse_args()
    try:
        processed = run_worker(get_settings(), once=args.once)
        if args.once:
            print(json.dumps({"processed": processed}))
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
