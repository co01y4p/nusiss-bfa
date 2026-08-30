from datetime import UTC, datetime
from pathlib import Path

from app.domain.knowledge.models import (
    KnowledgeChunkCreate,
    KnowledgeDocument,
    KnowledgeDocumentCreate,
)
from app.rag.chunking import HeadingAwareChunker
from app.rag.embeddings import EmbeddingProvider
from app.rag.parsing import DocumentParser
from app.repositories.interfaces.knowledge import KnowledgeRepository


class DocumentIngestionService:
    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        embeddings: EmbeddingProvider,
        parser: DocumentParser | None = None,
        chunker: HeadingAwareChunker | None = None,
    ) -> None:
        self.repo = repository
        self.embeddings = embeddings
        self.parser = parser or DocumentParser()
        self.chunker = chunker or HeadingAwareChunker()

    async def ingest_file(
        self,
        file_path: str | Path,
        *,
        title: str | None = None,
        version: str = "1.0",
        effective_date: datetime | None = None,
        access_scope: str = "PUBLIC",
        is_approved: bool = False,
    ) -> KnowledgeDocument:
        parsed = self.parser.parse_file(file_path, title_override=title)
        chunk_data = self.chunker.chunk_document(parsed)

        if not chunk_data and parsed.raw_text.strip():
            # Create a single fallback chunk if document has content
            fallback_chunks = self.chunker.chunk_document(
                self.parser.parse_file(file_path, title_override=parsed.title)
            )
            if fallback_chunks:
                chunk_data = fallback_chunks

        chunk_texts = [c.content for c in chunk_data]
        embeddings = await self.embeddings.embed_texts(chunk_texts) if chunk_texts else []

        chunk_creates: list[KnowledgeChunkCreate] = []
        for c, emb in zip(chunk_data, embeddings, strict=False):
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
            title=parsed.title,
            source_path=parsed.source_path,
            content_hash=parsed.content_hash,
            version=version,
            effective_date=effective_date or datetime.now(UTC),
            access_scope=access_scope,
            is_approved=is_approved,
            chunks=chunk_creates,
        )

        return self.repo.save_document(doc_create)
