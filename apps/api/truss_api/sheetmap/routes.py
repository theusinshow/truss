from fastapi import APIRouter, Depends, HTTPException, status

from truss_api.core.settings import Settings, get_settings
from truss_api.sheetmap import repository
from truss_api.sheetmap.models import SheetMap


router = APIRouter(tags=["sheet-map"])


@router.get("/sheets/{sheet_id}/sheet-map", response_model=SheetMap)
def get_sheet_map(
    sheet_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return repository.get_sheet_map(sheet_id, settings)
    except repository.SheetMapNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sheet map not found",
        ) from error
