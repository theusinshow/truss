from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RevisionSource = Literal["manual", "registered_external", "pdf_placeholder"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)


class RevisionCreate(BaseModel):
    revision_code: str | None = Field(default=None, min_length=1, max_length=40)
    notes: str = Field(default="", max_length=1000)
    source_type: RevisionSource = "manual"
    original_filename: str | None = Field(default=None, max_length=255)
    original_file_path: str | None = Field(default=None, max_length=1000)
    content_hash: str | None = Field(default=None, max_length=128)


class Revision(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    revision_code: str
    notes: str
    source_type: RevisionSource
    original_filename: str | None
    original_file_path: str | None
    content_hash: str | None
    created_at: datetime


class Project(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class ProjectSummary(Project):
    revisions_count: int
    latest_revision_code: str | None


class ProjectDetail(Project):
    revisions: list[Revision]
