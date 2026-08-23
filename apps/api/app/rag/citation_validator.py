import re
from dataclasses import dataclass, field

from app.rag.retriever import RetrievedChunk


@dataclass
class CitationValidationResult:
    is_valid: bool
    valid_citations: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)


class CitationValidator:
    """Validates citations in LLM-generated responses against actual retrieved chunks."""

    def validate(
        self,
        *,
        response_text: str,
        citations: list[str],
        retrieved_chunks: list[RetrievedChunk],
    ) -> CitationValidationResult:
        issues: list[str] = []
        reason_codes: list[str] = []
        valid_citations: list[str] = []
        invalid_citations: list[str] = []

        chunk_map = {chunk.chunk_id: chunk for chunk in retrieved_chunks}

        # 1. Validate citation IDs existence
        for cit in citations:
            clean_id = cit.strip()
            if clean_id in chunk_map:
                valid_citations.append(clean_id)
            else:
                invalid_citations.append(clean_id)
                issues.append(f"Cited chunk ID does not exist in retrieved context: '{clean_id}'")

        if invalid_citations:
            reason_codes.append("HALLUCINATED_CITATION")

        # 2. Check in-text citations vs declared citations
        in_text_ids = re.findall(r"\[([a-f0-9\-]{8,36})\]", response_text, re.IGNORECASE)
        for text_id in in_text_ids:
            if text_id not in chunk_map and text_id not in invalid_citations:
                invalid_citations.append(text_id)
                issues.append(f"In-text citation references non-existent chunk ID: '{text_id}'")
                if "HALLUCINATED_CITATION" not in reason_codes:
                    reason_codes.append("HALLUCINATED_CITATION")

        # 3. Grounding check: if citations were provided, verify substantive overlap
        if valid_citations:
            combined_cited_text = " ".join(
                chunk_map[cid].content.lower() for cid in valid_citations
            )
            response_words = [
                w.lower()
                for w in re.findall(r"\b[a-zA-Z]{4,}\b", response_text)
                if w.lower() not in {
                    "this", "that", "with", "from", "have", "been", "were", "your",
                    "please", "contact", "facility", "building", "information", "report"
                }
            ]
            if response_words:
                matched_words = [w for w in response_words if w in combined_cited_text]
                overlap_ratio = len(matched_words) / len(response_words)
                if overlap_ratio < 0.25 and len(response_words) >= 6:
                    issues.append(
                        "Response contains claims that have low keyword support in cited chunks."
                    )
                    reason_codes.append("WEAK_EVIDENCE_GROUNDING")

        is_valid = len(invalid_citations) == 0 and "WEAK_EVIDENCE_GROUNDING" not in reason_codes
        if is_valid and not reason_codes:
            reason_codes.append("CITATIONS_VERIFIED")

        return CitationValidationResult(
            is_valid=is_valid,
            valid_citations=valid_citations,
            invalid_citations=invalid_citations,
            issues=issues,
            reason_codes=reason_codes,
        )
