from pydantic import BaseModel


class SheetRegion(BaseModel):
    id: str
    region_kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float


class SheetView(BaseModel):
    id: str
    parent_view_id: str | None
    view_kind: str
    view_role: str | None
    identifier: str | None
    # Bruto e normalizado seguem separados ate o cliente: o viewer mostra o que
    # esta no PDF, nao uma interpretacao nao confirmada.
    title_raw: str | None
    title: str | None
    declared_scale_raw: str | None
    declared_scale: str | None
    level_raw: str | None
    level: str | None
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float
    provenance: str


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
    views: list[SheetView]
