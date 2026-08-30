from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    id: str
    document_id: str
    chunk_index: int
    heading: str
    content: str
    token_count: int
    embedding: list[float] = Field(default_factory=list)
    created_at: datetime


class KnowledgeDocument(BaseModel):
    id: str
    title: str
    source_path: str
    content_hash: str
    version: str
    effective_date: datetime
    access_scope: str
    is_approved: bool
    created_at: datetime
    updated_at: datetime
    chunks: list[KnowledgeChunk] = Field(default_factory=list)


class KnowledgeChunkCreate(BaseModel):
    chunk_index: int
    heading: str
    content: str
    token_count: int
    embedding: list[float]


class KnowledgeDocumentCreate(BaseModel):
    title: str
    source_path: str
    content_hash: str
    version: str = "1.0"
    effective_date: datetime | None = None
    access_scope: str = "PUBLIC"
    is_approved: bool = False
    chunks: list[KnowledgeChunkCreate] = Field(default_factory=list)
