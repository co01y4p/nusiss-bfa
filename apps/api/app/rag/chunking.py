from dataclasses import dataclass

from app.rag.parsing import ParsedDocument


@dataclass
class ChunkData:
    chunk_index: int
    heading: str
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    """Fast approximation of token count (~4 characters or 0.75 words per token)."""
    words = len(text.split())
    chars = len(text)
    # Average of character-based and word-based estimation
    return max(1, int((chars / 4.0 + words * 1.3) / 2.0))


class HeadingAwareChunker:
    def __init__(
        self,
        min_tokens: int = 200,
        target_tokens: int = 500,
        max_tokens: int = 800,
        overlap_percentage: float = 0.12,
    ) -> None:
        self.min_tokens = min_tokens
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_percentage = overlap_percentage

    def chunk_document(self, doc: ParsedDocument) -> list[ChunkData]:
        chunks: list[ChunkData] = []
        chunk_idx = 0

        for section in doc.sections:
            heading = section.heading.strip()
            content = section.content.strip()
            if not content:
                continue

            section_tokens = estimate_tokens(content)

            if section_tokens <= self.max_tokens:
                formatted_content = f"[{doc.title} > {heading}]\n{content}"
                chunks.append(
                    ChunkData(
                        chunk_index=chunk_idx,
                        heading=heading,
                        content=formatted_content,
                        token_count=estimate_tokens(formatted_content),
                    )
                )
                chunk_idx += 1
            else:
                # Split large section into overlapping windows
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                if not paragraphs:
                    paragraphs = [content]

                current_paras: list[str] = []
                current_tokens = 0

                for para in paragraphs:
                    para_tokens = estimate_tokens(para)

                    if current_tokens + para_tokens > self.target_tokens and current_paras:
                        chunk_text = "\n\n".join(current_paras)
                        formatted_content = f"[{doc.title} > {heading}]\n{chunk_text}"
                        chunks.append(
                            ChunkData(
                                chunk_index=chunk_idx,
                                heading=heading,
                                content=formatted_content,
                                token_count=estimate_tokens(formatted_content),
                            )
                        )
                        chunk_idx += 1

                        # Retain ~10-15% overlap from tail paragraphs
                        overlap_budget = int(self.target_tokens * self.overlap_percentage)
                        overlap_paras: list[str] = []
                        accumulated = 0
                        for p in reversed(current_paras):
                            p_tok = estimate_tokens(p)
                            if accumulated + p_tok <= overlap_budget:
                                overlap_paras.insert(0, p)
                                accumulated += p_tok
                            else:
                                break

                        current_paras = overlap_paras + [para]
                        current_tokens = sum(estimate_tokens(p) for p in current_paras)
                    else:
                        current_paras.append(para)
                        current_tokens += para_tokens

                if current_paras:
                    chunk_text = "\n\n".join(current_paras)
                    formatted_content = f"[{doc.title} > {heading}]\n{chunk_text}"
                    chunks.append(
                        ChunkData(
                            chunk_index=chunk_idx,
                            heading=heading,
                            content=formatted_content,
                            token_count=estimate_tokens(formatted_content),
                        )
                    )
                    chunk_idx += 1

        return chunks
