import argparse
from pathlib import Path

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.rag.embeddings import FakeEmbeddings, OpenAICompatibleEmbeddings
from app.rag.ingestion import DocumentIngestionService
from app.repositories.postgres.knowledge import SqlAlchemyKnowledgeRepository


def build_embeddings(settings: object) -> FakeEmbeddings | OpenAICompatibleEmbeddings:
    llm_provider = getattr(settings, "llm_provider", "fake")
    base_url = getattr(settings, "llm_base_url", "")
    api_key = getattr(settings, "llm_api_key", "")
    embedding_model = getattr(settings, "embedding_model", "text-embedding-3-small")
    if llm_provider in {"openai", "openrouter"} and base_url and api_key:
        return OpenAICompatibleEmbeddings(
            base_url=base_url,
            api_key=api_key,
            model=embedding_model,
        )
    return FakeEmbeddings()


async def ingest(
    file_path: Path,
    title: str | None,
    version: str,
    access_scope: str,
    approve: bool,
) -> None:
    settings = get_settings()
    session = SessionLocal()
    try:
        repo = SqlAlchemyKnowledgeRepository(session)
        embeddings = build_embeddings(settings)
        service = DocumentIngestionService(repository=repo, embeddings=embeddings)

        print(f"Ingesting: {file_path}")
        doc = await service.ingest_file(
            file_path,
            title=title,
            version=version,
            access_scope=access_scope,
            is_approved=approve,
        )

        total_tokens = sum(c.token_count for c in doc.chunks)
        print(" Successfully ingested document:")
        print(f"  - Document ID:   {doc.id}")
        print(f"  - Title:         {doc.title}")
        print(f"  - Version:       {doc.version}")
        print(f"  - Chunks:        {len(doc.chunks)}")
        print(f"  - Total Tokens:  {total_tokens}")
        print(f"  - Access Scope:  {doc.access_scope}")
        print(f"  - Approved:      {doc.is_approved}")
        if not doc.is_approved:
            print("  [NOTE] Document is NOT approved and will not be retrieved by agents.")
    finally:
        session.close()


def main() -> None:
    import asyncio

    parser = argparse.ArgumentParser(
        description="Ingest and chunk facility documents into the knowledge base."
    )
    parser.add_argument("file", type=str, help="Path to document file (.md, .txt, or .pdf)")
    parser.add_argument(
        "--approve",
        action="store_true",
        default=False,
        help="Mark document as approved immediately for retrieval",
    )
    parser.add_argument(
        "--access-scope",
        type=str,
        default="PUBLIC",
        choices=["PUBLIC", "STAFF", "MANAGEMENT"],
        help="Access scope for this document (default: PUBLIC)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="1.0",
        help="Document version string (default: 1.0)",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Optional title override (defaults to document heading or filename)",
    )

    args = parser.parse_args()
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File '{file_path}' does not exist.")
        raise SystemExit(1)

    asyncio.run(
        ingest(
            file_path=file_path,
            title=args.title,
            version=args.version,
            access_scope=args.access_scope,
            approve=args.approve,
        )
    )


if __name__ == "__main__":
    main()
