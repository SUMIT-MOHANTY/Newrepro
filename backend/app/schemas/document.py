from datetime import datetime
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class DocumentBase(BaseModel):
    filename: str
    content_preview: Optional[str] = None
    full_content: Optional[str] = None
    analysis_result: Optional[str] = None
    file_path: Optional[str] = ""
    screening_inputs: Optional[dict] = None
    project_token: Optional[str] = None
    revision_version: Optional[int] = None

    @field_validator("file_path", mode="before")
    @classmethod
    def default_file_path(cls, v):
        return "" if v is None else v


class DocumentCreate(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: int
    upload_date: Optional[datetime] = None
    owner_id: int

    class Config:
        from_attributes = True


class UrlExtractRequest(BaseModel):
    url: str


class ShareDocCreateRequest(BaseModel):
    title: str
    config: Optional[Dict[str, Any]] = None
    file_paths: Optional[List[Dict[str, Any]]] = None


__all__ = [
    "DocumentBase",
    "DocumentCreate",
    "DocumentResponse",
    "UrlExtractRequest",
    "ShareDocCreateRequest",
]
