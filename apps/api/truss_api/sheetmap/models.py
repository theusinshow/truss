from pydantic import BaseModel


class SheetRegion(BaseModel):
    id: str
    region_kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


class SheetMap(BaseModel):
    id: str
    sheet_id: str
    project_id: str
    revision_id: str
    pipeline_version: str
    status: str
    geometry_path: str
    sheet_code: str | None
    sheet_type: str
    paper_format: str
    orientation: str
    title_block: dict
    built_at: str
    regions: list[SheetRegion]
