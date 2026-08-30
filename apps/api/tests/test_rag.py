from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.assignment import AssignmentAgent
from app.agents.classification import ClassificationAgent
from app.agents.extraction import ExtractionAgent
from app.agents.intent import IntentAgent
from app.agents.priority import PriorityAgent
from app.agents.response import ResponseAgent
from app.agents.review import ReviewAgent
from app.agents.security import SecurityAgent
from app.core.config import Settings
from app.core.database import Base
from app.llm.fake import FakeStructuredLLM
from app.rag.chunking import HeadingAwareChunker
from app.rag.citation_validator import CitationValidator
from app.rag.embeddings import FakeEmbeddings
from app.rag.ingestion import DocumentIngestionService
from app.rag.parsing import DocumentParser, DocumentParsingError
from app.rag.retriever import KnowledgeRetriever, RetrievedChunk
from app.repositories.postgres.knowledge import SqlAlchemyKnowledgeRepository
from app.workflows.facility_graph import FacilityWorkflow
from tests.fakes import InMemoryIncidentRepository, InMemoryWorkflowRunRepository


def test_document_parser_markdown(tmp_path: Path) -> None:
    md_file = tmp_path / "test.md"
    content = "# Test Doc\n\n## Section 1\nContent 1.\n\n## Section 2\nContent 2."
    md_file.write_text(content, encoding="utf-8")
    parser = DocumentParser()
    parsed = parser.parse_file(md_file)
    assert parsed.title == "Test Doc"
    assert len(parsed.sections) == 2
    assert parsed.sections[0].heading == "Section 1"
    assert parsed.sections[0].content == "Content 1."
    assert parsed.sections[1].heading == "Section 2"


def test_document_parser_text(tmp_path: Path) -> None:
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("First paragraph.\n\nSecond paragraph.", encoding="utf-8")
    parser = DocumentParser()
    parsed = parser.parse_file(txt_file)
    assert len(parsed.sections) == 2
    assert "First paragraph" in parsed.sections[0].content


def test_document_parser_unsupported_type(tmp_path: Path) -> None:
    invalid_file = tmp_path / "file.exe"
    invalid_file.write_bytes(b"dummy")
    parser = DocumentParser()
    with pytest.raises(DocumentParsingError):
        parser.parse_file(invalid_file)


def test_heading_aware_chunker(tmp_path: Path) -> None:
    md_file = tmp_path / "rules.md"
    content = "# Facility Rules\n\n## Operating Hours\nOpen 07:00 to 22:00.\n\n## Access\nKeycard."
    md_file.write_text(content, encoding="utf-8")
    parser = DocumentParser()
    parsed = parser.parse_file(md_file)
    chunker = HeadingAwareChunker()
    chunks = chunker.chunk_document(parsed)

    assert len(chunks) == 2
    assert chunks[0].heading == "Operating Hours"
    assert "[Facility Rules > Operating Hours]" in chunks[0].content
    assert chunks[0].token_count > 0


@pytest.mark.asyncio
async def test_fake_embeddings_deterministic() -> None:
    provider = FakeEmbeddings(dim=1536)
    vec1 = await provider.embed_query("facility operating hours")
    vec2 = await provider.embed_query("facility operating hours")
    vec3 = await provider.embed_query("elevator emergency contact")

    assert len(vec1) == 1536
    assert vec1 == vec2
    assert vec1 != vec3


def test_citation_validator() -> None:
    validator = CitationValidator()
    chunks = [
        RetrievedChunk(
            chunk_id="chunk-123",
            document_id="doc-1",
            document_title="Hours",
            heading="Hours",
            content="Lobby is open from 07:00 to 22:00 daily.",
            score=0.9,
        )
    ]

    # Valid citation
    valid_res = validator.validate(
        response_text="The lobby is open from 07:00 to 22:00 daily.",
        citations=["chunk-123"],
        retrieved_chunks=chunks,
    )
    assert valid_res.is_valid
    assert valid_res.valid_citations == ["chunk-123"]
    assert not valid_res.invalid_citations

    # Hallucinated citation
    invalid_res = validator.validate(
        response_text="The lobby is open 24/7.",
        citations=["fake-chunk-999"],
        retrieved_chunks=chunks,
    )
    assert not invalid_res.is_valid
    assert "fake-chunk-999" in invalid_res.invalid_citations
    assert "HALLUCINATED_CITATION" in invalid_res.reason_codes


@pytest.mark.asyncio
async def test_ingestion_and_retriever_pipeline(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        repo = SqlAlchemyKnowledgeRepository(session)
        embeddings = FakeEmbeddings(dim=1536)
        ingestion_service = DocumentIngestionService(repository=repo, embeddings=embeddings)

        doc_file = tmp_path / "building-hours.md"
        content = "# Building Hours\n\n## Main Lobby\nOpen 07:00 to 22:00.\n\n## Desk\nOpen 08:30."
        doc_file.write_text(content, encoding="utf-8")

        # Ingest as unapproved first
        doc = await ingestion_service.ingest_file(
            doc_file, title="Building Hours", is_approved=False
        )
        assert doc.id is not None
        assert len(doc.chunks) == 2
        assert not doc.is_approved

        retriever = KnowledgeRetriever(
            repository=repo, embeddings=embeddings, default_similarity_threshold=0.0
        )

        # Unapproved document should NOT be retrievable
        results = await retriever.search("What are the lobby hours?", must_be_approved=True)
        assert len(results) == 0

        # Approve the document
        repo.update_approval(doc.id, is_approved=True)

        # Now approved document IS retrievable
        results = await retriever.search("What are the lobby hours?", must_be_approved=True)
        assert len(results) > 0
        assert any("Main Lobby" in r.heading for r in results)
        assert results[0].chunk_id is not None
    finally:
        session.close()


@pytest.mark.asyncio
async def test_workflow_faq_grounded_rag(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        repo = SqlAlchemyKnowledgeRepository(session)
        embeddings = FakeEmbeddings(dim=1536)
        ingestion_service = DocumentIngestionService(repository=repo, embeddings=embeddings)

        doc_file = tmp_path / "operating-hours.md"
        content = (
            "# Operating Hours\n\n## Gym Hours\nThe fitness center is open from 06:00 to 23:00."
        )
        doc_file.write_text(content, encoding="utf-8")
        await ingestion_service.ingest_file(doc_file, is_approved=True)

        retriever = KnowledgeRetriever(
            repository=repo, embeddings=embeddings, default_similarity_threshold=0.0
        )
        llm = FakeStructuredLLM()

        workflow = FacilityWorkflow(
            settings=Settings(),
            incident_repository=InMemoryIncidentRepository(),
            workflow_repository=InMemoryWorkflowRunRepository(),
            security=SecurityAgent(llm, model="fake", timeout_seconds=5.0),
            intent=IntentAgent(llm, model="fake", timeout_seconds=5.0),
            extraction=ExtractionAgent(llm, model="fake", timeout_seconds=5.0),
            classification=ClassificationAgent(llm, model="fake", timeout_seconds=5.0),
            priority=PriorityAgent(llm, model="fake", timeout_seconds=5.0),
            assignment=AssignmentAgent(llm, model="fake", timeout_seconds=5.0),
            response=ResponseAgent(llm, model="fake", timeout_seconds=5.0),
            review=ReviewAgent(llm, model="fake", timeout_seconds=5.0),
            retriever=retriever,
            citation_validator=CitationValidator(),
        )

        state = await workflow.run(text="What are the gym hours?")
        assert state.outcome == "FINALIZED"
        resp_lower = state.final_response.lower()
        assert "fitness center" in resp_lower or "gym" in resp_lower

        # Verify retrieval and citation trace steps exist
        trace_nodes = [t.node for t in state.trace]
        assert "faq_retrieval" in trace_nodes
        assert "faq_response" in trace_nodes
        assert "citation_validation" in trace_nodes
    finally:
        session.close()


@pytest.mark.asyncio
async def test_workflow_faq_unapproved_document_fallback(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        repo = SqlAlchemyKnowledgeRepository(session)
        embeddings = FakeEmbeddings(dim=1536)
        ingestion_service = DocumentIngestionService(repository=repo, embeddings=embeddings)

        doc_file = tmp_path / "secret-rules.md"
        doc_file.write_text("# Secret Rules\n\n## Access\nSecret roof access.", encoding="utf-8")
        # Ingest without approval
        await ingestion_service.ingest_file(doc_file, is_approved=False)

        retriever = KnowledgeRetriever(
            repository=repo, embeddings=embeddings, default_similarity_threshold=0.0
        )
        llm = FakeStructuredLLM()

        workflow = FacilityWorkflow(
            settings=Settings(),
            incident_repository=InMemoryIncidentRepository(),
            workflow_repository=InMemoryWorkflowRunRepository(),
            security=SecurityAgent(llm, model="fake", timeout_seconds=5.0),
            intent=IntentAgent(llm, model="fake", timeout_seconds=5.0),
            extraction=ExtractionAgent(llm, model="fake", timeout_seconds=5.0),
            classification=ClassificationAgent(llm, model="fake", timeout_seconds=5.0),
            priority=PriorityAgent(llm, model="fake", timeout_seconds=5.0),
            assignment=AssignmentAgent(llm, model="fake", timeout_seconds=5.0),
            response=ResponseAgent(llm, model="fake", timeout_seconds=5.0),
            review=ReviewAgent(llm, model="fake", timeout_seconds=5.0),
            retriever=retriever,
            citation_validator=CitationValidator(),
        )

        state = await workflow.run(text="What is the roof access policy?")
        assert state.outcome == "FINALIZED"
        assert state.final_response == (
            "I do not have enough approved facility information to answer that question."
        )
    finally:
        session.close()
