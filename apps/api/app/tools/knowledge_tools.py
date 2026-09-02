from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from app.rag.retriever import KnowledgeRetriever

if TYPE_CHECKING:
    from app.tools.registry import ToolRegistry


class SearchKnowledgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)
    access_scope: str = Field(default="PUBLIC")


def register_knowledge_tools(registry: "ToolRegistry", retriever: KnowledgeRetriever) -> None:
    async def search_knowledge(args: SearchKnowledgeInput) -> list[dict[str, Any]]:
        chunks = await retriever.search(
            args.query,
            top_k=args.top_k,
            access_scope=args.access_scope,
            must_be_approved=True,
        )
        return [c.model_dump(mode="json") for c in chunks]

    registry.register(
        name="search_approved_knowledge",
        description="Search approved facility knowledge base documents with pgvector embeddings",
        input_schema=SearchKnowledgeInput,
        required_role="PUBLIC",
        handler=search_knowledge,
    )
