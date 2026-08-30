from typing import Protocol

from app.domain.knowledge.models import (
    KnowledgeChunk,
    KnowledgeChunkCreate,
    KnowledgeDocument,
    KnowledgeDocumentCreate,
)


class KnowledgeRepository(Protocol):
    def save_document(self, doc_in: KnowledgeDocumentCreate) -> KnowledgeDocument: ...

    def get_document_by_id(self, document_id: str) -> KnowledgeDocument | None: ...

    def get_document_by_hash(self, content_hash: str) -> KnowledgeDocument | None: ...

    def update_approval(self, document_id: str, is_approved: bool) -> KnowledgeDocument | None: ...

    def delete_document(self, document_id: str) -> bool: ...

    def save_chunks(
        self, document_id: str, chunks: list[KnowledgeChunkCreate]
    ) -> list[KnowledgeChunk]: ...

    def get_chunk(self, chunk_id: str) -> KnowledgeChunk | None: ...

    def search_chunks(
        self,
        *,
        query_embedding: list[float],
        query_text: str = "",
        top_k: int = 5,
        access_scope: str = "PUBLIC",
        must_be_approved: bool = True,
    ) -> list[tuple[KnowledgeChunk, float]]: ...

    def list_documents(
        self, *, approved_only: bool = False, limit: int = 100, offset: int = 0
    ) -> list[KnowledgeDocument]: ...
