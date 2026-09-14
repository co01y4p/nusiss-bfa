import uuid
from datetime import UTC, datetime
from typing import Any

from app.domain.incidents.models import Incident, IncidentStatus


class InMemoryIncidentRepository:
    def __init__(self) -> None:
        self.items: dict[str, Incident] = {}

    def create(self, *, description: str, location: str) -> Incident:
        incident_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        incident = Incident(
            id=incident_id,
            reference_code=f"BFA-{len(self.items) + 1:010d}",
            description=description,
            location=location,
            status=IncidentStatus.RECEIVED,
            created_at=now,
            updated_at=now,
        )
        self.items[incident_id] = incident
        return incident

    def get_by_id(self, incident_id: str) -> Incident | None:
        return self.items.get(incident_id)

    def get_by_reference(self, reference_code: str) -> Incident | None:
        return next(
            (item for item in self.items.values() if item.reference_code == reference_code.upper()),
            None,
        )

    def list_recent(self, *, limit: int = 200, offset: int = 0) -> list[Incident]:
        return list(self.items.values())[offset : offset + limit]

    def find_similar(
        self,
        *,
        location: str,
        since: datetime,
        exclude_id: str | None = None,
        limit: int = 5,
    ) -> list[Incident]:
        needle = location.strip().lower()
        matches = [
            item
            for item in self.items.values()
            if item.id != exclude_id
            and needle in item.location.lower()
            and item.created_at >= since
        ]
        matches.sort(key=lambda item: item.created_at, reverse=True)
        return matches[:limit]

    def update_status(self, incident_id: str, status: str) -> Incident | None:
        incident = self.items.get(incident_id)
        if incident is None:
            return None
        updated = incident.model_copy(
            update={"status": IncidentStatus(status), "updated_at": datetime.now(UTC)}
        )
        self.items[incident_id] = updated
        return updated

    def update_triage(
        self,
        incident_id: str,
        *,
        location: str,
        category: str,
        priority: str,
        assigned_team: str,
        requires_human_review: bool,
    ) -> Incident | None:
        incident = self.items.get(incident_id)
        if incident is None:
            return None
        updated = incident.model_copy(
            update={
                "location": location,
                "category": category,
                "priority": priority,
                "assigned_team": assigned_team,
                "requires_human_review": requires_human_review,
                "updated_at": datetime.now(UTC),
            }
        )
        self.items[incident_id] = updated
        return updated


class InMemoryWorkflowRunRepository:
    def __init__(self) -> None:
        self.runs: list[dict[str, object]] = []

    def save(
        self,
        *,
        incident_id: str | None,
        input_text: str,
        outcome: str,
        final_response: str,
        trace: list[dict[str, object]],
    ) -> str:
        run_id = str(uuid.uuid4())
        self.runs.append(
            {
                "id": run_id,
                "incident_id": incident_id,
                "input_text": input_text,
                "outcome": outcome,
                "final_response": final_response,
                "trace": trace,
                "created_at": datetime.now(UTC),
            }
        )
        return run_id

    def get_for_incident(self, incident_id: str) -> dict[str, object] | None:
        return next(
            (run for run in reversed(self.runs) if run["incident_id"] == incident_id),
            None,
        )


class InMemoryKnowledgeRepository:
    def __init__(self) -> None:
        self.documents: dict[str, Any] = {}
        self.chunks: dict[str, Any] = {}

    def save_document(self, doc_in: Any) -> Any:
        from app.domain.knowledge.models import KnowledgeChunk, KnowledgeDocument

        doc_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        chunk_models = []
        for c in doc_in.chunks:
            cid = str(uuid.uuid4())
            chunk = KnowledgeChunk(
                id=cid,
                document_id=doc_id,
                chunk_index=c.chunk_index,
                heading=c.heading,
                content=c.content,
                token_count=c.token_count,
                embedding=c.embedding,
                created_at=now,
            )
            self.chunks[cid] = chunk
            chunk_models.append(chunk)

        doc = KnowledgeDocument(
            id=doc_id,
            title=doc_in.title,
            source_path=doc_in.source_path,
            content_hash=doc_in.content_hash,
            version=doc_in.version,
            effective_date=doc_in.effective_date or now,
            access_scope=doc_in.access_scope,
            is_approved=doc_in.is_approved,
            created_at=now,
            updated_at=now,
            chunks=chunk_models,
        )
        self.documents[doc_id] = doc
        return doc

    def get_document_by_id(self, document_id: str) -> Any | None:
        return self.documents.get(document_id)

    def get_document_by_hash(self, content_hash: str) -> Any | None:
        return next((d for d in self.documents.values() if d.content_hash == content_hash), None)

    def update_approval(self, document_id: str, is_approved: bool) -> Any | None:
        doc = self.documents.get(document_id)
        if doc is None:
            return None
        updated = doc.model_copy(
            update={"is_approved": is_approved, "updated_at": datetime.now(UTC)}
        )
        self.documents[document_id] = updated
        return updated

    def delete_document(self, document_id: str) -> bool:
        if document_id not in self.documents:
            return False
        del self.documents[document_id]
        self.chunks = {k: v for k, v in self.chunks.items() if v.document_id != document_id}
        return True

    def save_chunks(self, document_id: str, chunks: list[Any]) -> list[Any]:
        from app.domain.knowledge.models import KnowledgeChunk

        created = []
        now = datetime.now(UTC)
        for c in chunks:
            cid = str(uuid.uuid4())
            chunk = KnowledgeChunk(
                id=cid,
                document_id=document_id,
                chunk_index=c.chunk_index,
                heading=c.heading,
                content=c.content,
                token_count=c.token_count,
                embedding=c.embedding,
                created_at=now,
            )
            self.chunks[cid] = chunk
            created.append(chunk)
        return created

    def get_chunk(self, chunk_id: str) -> Any | None:
        return self.chunks.get(chunk_id)

    def search_chunks(
        self,
        *,
        query_embedding: list[float],
        query_text: str = "",
        top_k: int = 5,
        access_scope: str = "PUBLIC",
        must_be_approved: bool = True,
    ) -> list[tuple[Any, float]]:
        import math
        import re

        scored = []
        for chunk in self.chunks.values():
            doc = self.documents.get(chunk.document_id)
            if not doc or doc.access_scope != access_scope:
                continue
            if must_be_approved and not doc.is_approved:
                continue

            v_sim = 0.0
            if query_embedding and chunk.embedding:
                dot = sum(a * b for a, b in zip(query_embedding, chunk.embedding, strict=False))
                na = math.sqrt(sum(a * a for a in query_embedding))
                nb = math.sqrt(sum(b * b for b in chunk.embedding))
                if na > 0 and nb > 0:
                    v_sim = dot / (na * nb)

            l_sim = 0.0
            if query_text:
                kws = [w.lower() for w in re.findall(r"\w+", query_text) if len(w) > 2]
                if kws:
                    text = (chunk.heading + " " + chunk.content).lower()
                    matches = sum(1 for kw in kws if kw in text)
                    l_sim = matches / len(kws)

            score = 0.7 * v_sim + 0.3 * l_sim if query_embedding else l_sim
            scored.append((chunk, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def list_documents(
        self, *, approved_only: bool = False, limit: int = 100, offset: int = 0
    ) -> list[Any]:
        docs = list(self.documents.values())
        if approved_only:
            docs = [d for d in docs if d.is_approved]
        return docs[offset : offset + limit]
