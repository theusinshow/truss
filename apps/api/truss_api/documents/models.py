from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Sheet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    project_id: str
    revision_id: str
    page_index: int
    sheet_number: int
    width_pt: float
    height_pt: float
    rotation: int
    label: str
    render_path: str | None
    thumbnail_path: str | None
    created_at: datetime


class TextBlock(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sheet_id: str
    document_id: str
    project_id: str
    revision_id: str
    block_index: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    created_at: datetime


class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    revision_id: str
    original_filename: str
    stored_file_path: str
    content_hash: str
    mime_type: str
    file_size_bytes: int
    page_count: int
    created_at: datetime


class DocumentDetail(Document):
    sheets: list[Sheet]
