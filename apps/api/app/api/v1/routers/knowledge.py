import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.domain.knowledge.models import (
    KnowledgeChunkCreate,
    KnowledgeDocumentCreate,
)
from app.rag.chunking import HeadingAwareChunker
from app.rag.embeddings import EmbeddingProvider, FakeEmbeddings, OpenAICompatibleEmbeddings
from app.rag.parsing import DocumentParser
from app.rag.retriever import KnowledgeRetriever, RetrievedChunk
from app.repositories.postgres.knowledge import SqlAlchemyKnowledgeRepository

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class DocumentSummaryResponse(BaseModel):
    id: str
    title: str
    source_path: str
    version: str
    access_scope: str
    is_approved: bool
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class IngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=100000)
    version: str = Field(default="1.0", max_length=32)
    access_scope: str = Field(default="PUBLIC")
    is_approved: bool = Field(default=True)


class UpdateApprovalRequest(BaseModel):
    is_approved: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    access_scope: str = Field(default="PUBLIC")
    must_be_approved: bool = Field(default=True)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResponse(BaseModel):
    query: str
    results_count: int
    chunks: list[RetrievedChunk]


def get_embeddings(settings: Settings) -> EmbeddingProvider:
    has_keys = bool(settings.llm_base_url and settings.llm_api_key)
    if settings.llm_provider in {"openai", "openrouter"} and has_keys:
        return OpenAICompatibleEmbeddings(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.embedding_model,
        )
    return FakeEmbeddings(dim=settings.embedding_dim)


@router.get("/documents", response_model=list[DocumentSummaryResponse])
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    approved_only: bool = False,
) -> list[DocumentSummaryResponse]:
    repo = SqlAlchemyKnowledgeRepository(db)
    docs = repo.list_documents(approved_only=approved_only, limit=100)
    summaries: list[DocumentSummaryResponse] = []
    for doc in docs:
        full_doc = repo.get_document_by_id(doc.id)
        chunk_count = len(full_doc.chunks) if full_doc else 0
        summaries.append(
            DocumentSummaryResponse(
                id=doc.id,
                title=doc.title,
                source_path=doc.source_path,
                version=doc.version,
                access_scope=doc.access_scope,
                is_approved=doc.is_approved,
                chunk_count=chunk_count,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
            )
        )
    return summaries


@router.post("/documents", response_model=DocumentSummaryResponse)
async def ingest_custom_document(
    body: IngestTextRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentSummaryResponse:
    repo = SqlAlchemyKnowledgeRepository(db)
    embeddings = get_embeddings(settings)
    parser = DocumentParser()
    chunker = HeadingAwareChunker()

    content_bytes = body.content.encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    parsed = parser._parse_markdown(body.content, body.title)
    title, sections = parsed
    from app.rag.parsing import ParsedDocument

    parsed_doc = ParsedDocument(
        title=body.title or title,
        source_path=f"manual://{body.title.lower().replace(' ', '-')}.md",
        content_hash=content_hash,
        raw_text=body.content,
        sections=sections,
    )
    chunk_data = chunker.chunk_document(parsed_doc)
    chunk_texts = [c.content for c in chunk_data]
    chunk_embeddings = await embeddings.embed_texts(chunk_texts) if chunk_texts else []

    chunk_creates: list[KnowledgeChunkCreate] = []
    for c, emb in zip(chunk_data, chunk_embeddings, strict=False):
        chunk_creates.append(
            KnowledgeChunkCreate(
                chunk_index=c.chunk_index,
                heading=c.heading,
                content=c.content,
                token_count=c.token_count,
                embedding=emb,
            )
        )

    doc_create = KnowledgeDocumentCreate(
        title=body.title,
        source_path=parsed_doc.source_path,
        content_hash=content_hash,
        version=body.version,
        effective_date=datetime.now(UTC),
        access_scope=body.access_scope,
        is_approved=body.is_approved,
        chunks=chunk_creates,
    )
    saved = repo.save_document(doc_create)
    return DocumentSummaryResponse(
        id=saved.id,
        title=saved.title,
        source_path=saved.source_path,
        version=saved.version,
        access_scope=saved.access_scope,
        is_approved=saved.is_approved,
        chunk_count=len(saved.chunks),
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


@router.patch("/documents/{document_id}/approval", response_model=DocumentSummaryResponse)
def update_document_approval(
    document_id: str,
    body: UpdateApprovalRequest,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentSummaryResponse:
    repo = SqlAlchemyKnowledgeRepository(db)
    updated = repo.update_approval(document_id, is_approved=body.is_approved)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    full_doc = repo.get_document_by_id(updated.id)
    chunk_count = len(full_doc.chunks) if full_doc else 0
    return DocumentSummaryResponse(
        id=updated.id,
        title=updated.title,
        source_path=updated.source_path,
        version=updated.version,
        access_scope=updated.access_scope,
        is_approved=updated.is_approved,
        chunk_count=chunk_count,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    repo = SqlAlchemyKnowledgeRepository(db)
    success = repo.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return {"deleted": True, "id": document_id}


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(
    body: SearchRequest,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SearchResponse:
    repo = SqlAlchemyKnowledgeRepository(db)
    embeddings = get_embeddings(settings)
    retriever = KnowledgeRetriever(
        repository=repo,
        embeddings=embeddings,
        default_top_k=body.top_k,
        default_similarity_threshold=0.0,
    )
    chunks = await retriever.search(
        query=body.query,
        top_k=body.top_k,
        access_scope=body.access_scope,
        must_be_approved=body.must_be_approved,
        threshold=0.0,
    )
    return SearchResponse(
        query=body.query,
        results_count=len(chunks),
        chunks=chunks,
    )
