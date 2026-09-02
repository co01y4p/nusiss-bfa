import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class InjectionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_score: float = Field(ge=0.0, le=1.0)
    is_high_risk: bool
    risk_labels: list[str]
    reason_codes: list[str]
    matched_patterns: list[str] = Field(default_factory=list)


class PromptInjectionDetector:
    """Detects direct and indirect prompt injection attempts using pattern-based heuristics."""

    # High severity patterns (immediate high risk >= 0.8)
    DIRECT_OVERRIDE_PATTERNS: ClassVar[list[tuple[str, str, float]]] = [
        (r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", "INSTRUCTION_OVERRIDE", 0.95),
        (
            r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?)",
            "INSTRUCTION_OVERRIDE",
            0.95,
        ),
        (
            r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions?|rules?|prompts?)",
            "INSTRUCTION_OVERRIDE",
            0.95,
        ),
        (
            r"reveal\s+(your\s+)?(system\s+prompt|initial\s+prompt|secret\s+instructions?)",
            "SYSTEM_PROMPT_LEAK",
            0.90,
        ),
        (
            r"show\s+(me\s+)?(your\s+)?(system\s+prompt|internal\s+instructions?)",
            "SYSTEM_PROMPT_LEAK",
            0.90,
        ),
        (r"output\s+(your\s+)?(system\s+prompt|full\s+prompt)", "SYSTEM_PROMPT_LEAK", 0.90),
        (
            r"what\s+(is|are)\s+your\s+(system\s+prompt|system\s+instructions?)",
            "SYSTEM_PROMPT_LEAK",
            0.85,
        ),
        (r"print\s+everything\s+above", "SYSTEM_PROMPT_LEAK", 0.90),
        (
            r"you\s+are\s+now\s+(in\s+)?(developer\s+mode|dan\s+mode|unrestricted\s+mode|jailbreak)",
            "JAILBREAK_ROLEPLAY",
            0.95,
        ),
        (
            r"act\s+as\s+(an?\s+)?(unfiltered|unrestricted|evil|jailbroken|godmode)\s+ai",
            "JAILBREAK_ROLEPLAY",
            0.95,
        ),
        (
            r"pretend\s+you\s+have\s+no\s+(rules|restrictions|filters|guidelines)",
            "JAILBREAK_ROLEPLAY",
            0.90,
        ),
        (
            r"bypass\s+(all\s+)?(safety|content|ethical)\s+(filters?|policies?|guidelines?)",
            "FILTER_BYPASS",
            0.95,
        ),
        (r"do\s+anything\s+now\b", "JAILBREAK_ROLEPLAY", 0.90),
    ]

    # Delimiter and prompt boundary manipulation patterns (moderate to high risk)
    DELIMITER_PATTERNS: ClassVar[list[tuple[str, str, float]]] = [
        (r"<\|im_start\|>|<\|im_end\|>", "CHATML_INJECTION", 0.90),
        (r"\[INST\]|\[/INST\]", "LLAMA_PROMPT_INJECTION", 0.90),
        (r"<system>|<\/system>|<system_prompt>", "XML_SYSTEM_TAG_INJECTION", 0.90),
        (r"###\s*(System|Instruction|Assistant):", "MARKDOWN_SYSTEM_INJECTION", 0.85),
        (r"```json\s*\{\s*\"role\":\s*\"system\"", "JSON_ROLE_INJECTION", 0.85),
    ]

    # Exfiltration vectors
    EXFILTRATION_PATTERNS: ClassVar[list[tuple[str, str, float]]] = [
        (
            r"!\[.*?\]\(https?://[^\s\)]+[\?&](key|secret|token|prompt|pwd|data)=",
            "IMAGE_EXFILTRATION",
            0.90,
        ),
        (r"fetch\(['\"]https?://[^\s'\"]+[\?&]data=", "SCRIPT_EXFILTRATION", 0.85),
    ]

    # Indirect injection patterns inside retrieved RAG chunks
    INDIRECT_RAG_PATTERNS: ClassVar[list[tuple[str, str, float]]] = [
        (r"\[\s*AI\s+INSTRUCTION\s*\]", "INDIRECT_AI_INSTRUCTION", 0.90),
        (r"ATTENTION\s+ASSISTANT:", "INDIRECT_AI_INSTRUCTION", 0.90),
        (r"IMPORTANT\s+SYSTEM\s+OVERRIDE:", "INDIRECT_SYSTEM_OVERRIDE", 0.95),
        (r"NOTE\s+TO\s+AI:\s*ignore\s+above", "INDIRECT_INSTRUCTION_OVERRIDE", 0.95),
        (
            r"When\s+answering\s+(the\s+user|this\s+query),\s+(always\s+)?(tell\s+them|say|output)\s+that",
            "INDIRECT_COERCION",
            0.80,
        ),
        (
            r"Do\s+not\s+mention\s+this\s+to\s+the\s+user,\s+instead\s+output",
            "INDIRECT_COERCION",
            0.85,
        ),
    ]

    def score_input(self, text: str) -> InjectionScore:
        """Evaluates direct prompt injection risks in user text."""
        normalized = text.strip().lower()
        if not normalized:
            return InjectionScore(
                risk_score=0.0,
                is_high_risk=False,
                risk_labels=[],
                reason_codes=["INPUT_EMPTY_SAFE"],
            )

        highest_score = 0.0
        labels: set[str] = set()
        matched: list[str] = []

        all_direct = (
            self.DIRECT_OVERRIDE_PATTERNS + self.DELIMITER_PATTERNS + self.EXFILTRATION_PATTERNS
        )

        for pattern, label, weight in all_direct:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                highest_score = max(highest_score, weight)
                labels.add(label)
                matched.append(pattern)

        # Repetition / length anomalies (excessive control tokens)
        if normalized.count("\n") > 50 or len(text) > 6000:
            highest_score = max(highest_score, 0.4)
            labels.add("PAYLOAD_ANOMALY")

        is_high = highest_score >= 0.8
        reason_codes = (
            [f"DETECTED_{label}" for label in sorted(labels)] if labels else ["HEURISTICS_PASS"]
        )

        return InjectionScore(
            risk_score=round(highest_score, 2),
            is_high_risk=is_high,
            risk_labels=sorted(labels),
            reason_codes=reason_codes,
            matched_patterns=matched,
        )

    def score_chunk(self, chunk_text: str) -> InjectionScore:
        """Evaluates indirect prompt injection risks inside retrieved RAG chunks."""
        normalized = chunk_text.strip()
        if not normalized:
            return InjectionScore(
                risk_score=0.0,
                is_high_risk=False,
                risk_labels=[],
                reason_codes=["CHUNK_EMPTY_SAFE"],
            )

        highest_score = 0.0
        labels: set[str] = set()
        matched: list[str] = []

        # Check direct override patterns in chunk
        for pattern, label, weight in self.DIRECT_OVERRIDE_PATTERNS:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                highest_score = max(highest_score, weight)
                labels.add(f"RAG_{label}")
                matched.append(pattern)

        # Check delimiter patterns in chunk
        for pattern, label, weight in self.DELIMITER_PATTERNS:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                highest_score = max(highest_score, weight)
                labels.add(f"RAG_{label}")
                matched.append(pattern)

        # Check indirect specific patterns
        for pattern, label, weight in self.INDIRECT_RAG_PATTERNS:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                highest_score = max(highest_score, weight)
                labels.add(label)
                matched.append(pattern)

        is_high = highest_score >= 0.75
        reason_codes = (
            [f"DETECTED_{label}" for label in sorted(labels)]
            if labels
            else ["CHUNK_HEURISTICS_PASS"]
        )

        return InjectionScore(
            risk_score=round(highest_score, 2),
            is_high_risk=is_high,
            risk_labels=sorted(labels),
            reason_codes=reason_codes,
            matched_patterns=matched,
        )
