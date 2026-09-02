import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class RedactionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_text: str
    redacted_text: str
    has_pii: bool
    detected_types: list[str]
    redactions_count: int = Field(ge=0)


class PIIRedactor:
    """Detects and redacts sensitive Personally Identifiable Information (PII)."""

    PATTERNS: ClassVar[list[tuple[str, str, str]]] = [
        # Singapore NRIC / FIN (e.g. S1234567A, T1234567B, F1234567C, G1234567D, M1234567X)
        (r"\b[STFGMstfgm]\d{7}[A-Za-z]\b", "[NRIC/FIN REDACTED]", "SG_NRIC_FIN"),
        # Credit card numbers (13-19 digits, with optional hyphens/spaces)
        (r"\b(?:\d{4}[-\s]?){3}\d{4}\b|\b\d{15,16}\b", "[CREDIT_CARD REDACTED]", "CREDIT_CARD"),
        # US SSN (e.g. 123-45-6789)
        (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN REDACTED]", "US_SSN"),
        # Email addresses
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", "[EMAIL REDACTED]", "EMAIL"),
        # Phone numbers (SG 8-digit or international +XX)
        (
            r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?[3689]\d{3}[-.\s]?\d{4}\b|\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b",
            "[PHONE REDACTED]",
            "PHONE",
        ),
        # IPv4 addresses
        (
            r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
            "[IP_ADDRESS REDACTED]",
            "IP_ADDRESS",
        ),
        # API Keys / Bearer tokens (e.g. sk-..., bearer ...)
        (
            r"\b(?:sk-[a-zA-Z0-9]{20,}|bearer\s+[a-zA-Z0-9\-._~+/]+=*)\b",
            "[SECRET REDACTED]",
            "SECRET_TOKEN",
        ),
    ]

    def redact(self, text: str) -> RedactionResult:
        if not text:
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                has_pii=False,
                detected_types=[],
                redactions_count=0,
            )

        redacted = text
        detected: set[str] = set()
        total_count = 0

        for pattern, replacement, pii_type in self.PATTERNS:
            matches = list(re.finditer(pattern, redacted, flags=re.IGNORECASE))
            if matches:
                detected.add(pii_type)
                total_count += len(matches)
                redacted = re.sub(pattern, replacement, redacted, flags=re.IGNORECASE)

        return RedactionResult(
            original_text=text,
            redacted_text=redacted,
            has_pii=bool(detected),
            detected_types=sorted(detected),
            redactions_count=total_count,
        )

    def redact_payload(self, data: Any) -> Any:
        """Recursively redacts strings within dicts, lists, or primitive values."""
        if isinstance(data, str):
            return self.redact(data).redacted_text
        if isinstance(data, dict):
            return {k: self.redact_payload(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.redact_payload(item) for item in data]
        return data


_default_redactor = PIIRedactor()


def redact_pii(text: str) -> RedactionResult:
    return _default_redactor.redact(text)


def redact_payload(data: Any) -> Any:
    return _default_redactor.redact_payload(data)
