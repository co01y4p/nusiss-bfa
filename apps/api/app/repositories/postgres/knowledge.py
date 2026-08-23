import math
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.models import KnowledgeChunkModel, KnowledgeDocumentModel
from app.domain.knowledge.models import (
    KnowledgeChunk,
    KnowledgeChunkCreate,
    KnowledgeDocument,
    KnowledgeDocumentCreate,
)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _lexical_match_score(query_text: str, heading: str, content: str) -> float:
    if not query_text.strip():
        return 0.0
    keywords = [w.lower() for w in re.findall(r"\w+", query_text) if len(w) > 2]
    if not keywords:
        return 0.0
    target_text = (heading + " " + content).lower()
    matches = sum(1 for kw in keywords if kw in target_text)
    return matches / len(keywords)


def _chunk_to_domain(row: KnowledgeChunkModel) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=row.id,
        document_id=row.document_id,
        chunk_index=row.chunk_index,
        heading=row.heading,
        content=row.content,
        token_count=row.token_count,
        embedding=row.embedding or [],
        created_at=row.created_at,
    )


def _doc_to_domain(row: KnowledgeDocumentModel, include_chunks: bool = True) -> KnowledgeDocument:
    chunks = [_chunk_to_domain(c) for c in row.chunks] if include_chunks and row.chunks else []
    return KnowledgeDocument(
        id=row.id,
        title=row.title,
        source_path=row.source_path,
        content_hash=row.content_hash,
        version=row.version,
        effective_date=row.effective_date,
        access_scope=row.access_scope,
        is_approved=row.is_approved,
        created_at=row.created_at,
        updated_at=row.updated_at,
        chunks=chunks,
    )


class SqlAlchemyKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save_document(self, doc_in: KnowledgeDocumentCreate) -> KnowledgeDocument:
        # Check if existing document by hash
        existing = self.session.scalar(
            select(KnowledgeDocumentModel).where(
                KnowledgeDocumentModel.content_hash == doc_in.content_hash
            )
        )
        effective_date = doc_in.effective_date or datetime.now(UTC)
        if existing:
            existing.title = doc_in.title
            existing.source_path = doc_in.source_path
            existing.version = doc_in.version
            existing.effective_date = effective_date
            existing.access_scope = doc_in.access_scope
            existing.is_approved = doc_in.is_approved
            existing.updated_at = datetime.now(UTC)
            doc_row = existing
            # Clear old chunks
            doc_row.chunks.clear()
        else:
            doc_row = KnowledgeDocumentModel(
                title=doc_in.title,
                source_path=doc_in.source_path,
                content_hash=doc_in.content_hash,
                version=doc_in.version,
                effective_date=effective_date,
                access_scope=doc_in.access_scope,
                is_approved=doc_in.is_approved,
            )
            self.session.add(doc_row)
            self.session.flush()

        for chunk_in in doc_in.chunks:
            chunk_row = KnowledgeChunkModel(
                document_id=doc_row.id,
                chunk_index=chunk_in.chunk_index,
                heading=chunk_in.heading,
                content=chunk_in.content,
                token_count=chunk_in.token_count,
                embedding=chunk_in.embedding,
            )
            doc_row.chunks.append(chunk_row)

        self.session.commit()
        self.session.refresh(doc_row)
        return _doc_to_domain(doc_row, include_chunks=True)

    def get_document_by_id(self, document_id: str) -> KnowledgeDocument | None:
        row = self.session.scalar(
            select(KnowledgeDocumentModel)
            .options(selectinload(KnowledgeDocumentModel.chunks))
            .where(KnowledgeDocumentModel.id == document_id)
        )
        return _doc_to_domain(row) if row else None

    def get_document_by_hash(self, content_hash: str) -> KnowledgeDocument | None:
        row = self.session.scalar(
            select(KnowledgeDocumentModel)
            .options(selectinload(KnowledgeDocumentModel.chunks))
            .where(KnowledgeDocumentModel.content_hash == content_hash)
        )
        return _doc_to_domain(row) if row else None

    def update_approval(self, document_id: str, is_approved: bool) -> KnowledgeDocument | None:
        row = self.session.get(KnowledgeDocumentModel, document_id)
        if row is None:
            return None
        row.is_approved = is_approved
        row.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(row)
        return _doc_to_domain(row)

    def delete_document(self, document_id: str) -> bool:
        row = self.session.get(KnowledgeDocumentModel, document_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def save_chunks(
        self, document_id: str, chunks: list[KnowledgeChunkCreate]
    ) -> list[KnowledgeChunk]:
        created: list[KnowledgeChunkModel] = []
        for c in chunks:
            row = KnowledgeChunkModel(
                document_id=document_id,
                chunk_index=c.chunk_index,
                heading=c.heading,
                content=c.content,
                token_count=c.token_count,
                embedding=c.embedding,
            )
            self.session.add(row)
            created.append(row)
        self.session.commit()
        for r in created:
            self.session.refresh(r)
        return [_chunk_to_domain(r) for r in created]

    def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None:
        row = self.session.get(KnowledgeChunkModel, chunk_id)
        return _chunk_to_domain(row) if row else None

    def search_chunks(
        self,
        *,
        query_embedding: list[float],
        query_text: str = "",
        top_k: int = 5,
        access_scope: str = "PUBLIC",
        must_be_approved: bool = True,
    ) -> list[tuple[KnowledgeChunk, float]]:
        stmt = (
            select(KnowledgeChunkModel, KnowledgeDocumentModel)
            .join(
                KnowledgeDocumentModel,
                KnowledgeChunkModel.document_id == KnowledgeDocumentModel.id,
            )
            .where(KnowledgeDocumentModel.access_scope == access_scope)
        )
        if must_be_approved:
            stmt = stmt.where(KnowledgeDocumentModel.is_approved.is_(True))

        now = datetime.now(UTC)
        stmt = stmt.where(KnowledgeDocumentModel.effective_date <= now)

        rows = self.session.execute(stmt).all()
        scored: list[tuple[KnowledgeChunk, float]] = []

        for chunk_row, _ in rows:
            chunk_embedding = chunk_row.embedding or []
            v_sim = _cosine_similarity(query_embedding, chunk_embedding)
            l_sim = _lexical_match_score(query_text, chunk_row.heading, chunk_row.content)

            # Hybrid score: 0.7 vector similarity + 0.3 lexical keyword similarity
            score = (0.7 * v_sim) + (0.3 * l_sim) if query_embedding else l_sim
            domain_chunk = _chunk_to_domain(chunk_row)
            scored.append((domain_chunk, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def list_documents(
        self, *, approved_only: bool = False, limit: int = 100, offset: int = 0
    ) -> list[KnowledgeDocument]:
        stmt = select(KnowledgeDocumentModel).order_by(KnowledgeDocumentModel.created_at.desc())
        if approved_only:
            stmt = stmt.where(KnowledgeDocumentModel.is_approved.is_(True))
        stmt = stmt.limit(limit).offset(offset)
        rows = self.session.scalars(stmt).all()
        return [_doc_to_domain(r, include_chunks=False) for r in rows]
