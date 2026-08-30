from pydantic import BaseModel, Field

from app.rag.embeddings import EmbeddingProvider
from app.repositories.interfaces.knowledge import KnowledgeRepository


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    heading: str
    content: str
    version: str = "1.0"
    score: float = Field(ge=0.0, le=1.0)


class KnowledgeRetriever:
    def __init__(
        self,
        *,
        repository: KnowledgeRepository,
        embeddings: EmbeddingProvider,
        default_top_k: int = 5,
        default_similarity_threshold: float = 0.25,
    ) -> None:
        self.repo = repository
        self.embeddings = embeddings
        self.default_top_k = default_top_k
        self.default_similarity_threshold = default_similarity_threshold

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        access_scope: str = "PUBLIC",
        must_be_approved: bool = True,
        threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        k = top_k if top_k is not None else self.default_top_k
        min_score = threshold if threshold is not None else self.default_similarity_threshold

        query_embedding = await self.embeddings.embed_query(normalized_query)
        scored_chunks = self.repo.search_chunks(
            query_embedding=query_embedding,
            query_text=normalized_query,
            top_k=k,
            access_scope=access_scope,
            must_be_approved=must_be_approved,
        )

        results: list[RetrievedChunk] = []
        doc_cache: dict[str, tuple[str, str]] = {}

        for chunk, score in scored_chunks:
            if score < min_score:
                continue

            if chunk.document_id not in doc_cache:
                doc = self.repo.get_document_by_id(chunk.document_id)
                doc_cache[chunk.document_id] = (
                    (doc.title, doc.version) if doc else ("Unknown Document", "1.0")
                )

            doc_title, doc_version = doc_cache[chunk.document_id]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=doc_title,
                    heading=chunk.heading,
                    content=chunk.content,
                    version=doc_version,
                    score=round(score, 4),
                )
            )

        return results
