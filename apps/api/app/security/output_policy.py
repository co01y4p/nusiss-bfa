import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.security.pii_redaction import redact_pii


class OutputPolicyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    issues: list[str]
    reason_codes: list[str]


class OutputPolicyValidator:
    """Validates LLM-generated output against safety, disclosure, and compliance policies."""

    LEAK_PATTERNS: ClassVar[list[tuple[str, str, str]]] = [
        (
            r"You\s+are\s+a\s+specialized\s+facility\s+management\s+AI\s+agent",
            "SYSTEM_PROMPT_LEAKAGE",
            "LEAK_PROMPT_TEMPLATE",
        ),
        (
            r"Output\s+valid\s+JSON\s+matching\s+the\s+schema",
            "SCHEMA_INSTRUCTION_LEAKAGE",
            "LEAK_SCHEMA_INSTRUCTION",
        ),
        (r"<\|im_start\|>|<\|im_end\|>|\[INST\]", "CONTROL_TOKEN_LEAKAGE", "LEAK_CONTROL_TOKENS"),
        (r"<script.*?>.*?<\/script>", "XSS_SCRIPT_TAG", "OUTPUT_UNSAFE_HTML"),
        (r"javascript:\s*", "JAVASCRIPT_URI", "OUTPUT_UNSAFE_SCHEME"),
        (
            r"!\[.*?\]\(https?://[^\s\)]+[\?&](?:token|key|secret|prompt|data)=",
            "MARKDOWN_EXFILTRATION",
            "OUTPUT_DATA_EXFILTRATION",
        ),
    ]

    FORBIDDEN_ACTION_CLAIMS: ClassVar[list[tuple[str, str, str]]] = [
        (
            r"\b(i\s+have|i've)\s+(deleted|dropped|formatted)\s+(the\s+)?(database|server|files?)\b",
            "UNAUTHORIZED_ACTION_CLAIM",
            "CLAIM_SYSTEM_MODIFICATION",
        ),
        (
            r"\b(i\s+have|i've)\s+transferred\s+\$?\d+",
            "FINANCIAL_ACTION_CLAIM",
            "CLAIM_FINANCIAL_ACTION",
        ),
    ]

    def validate(self, text: str) -> OutputPolicyResult:
        if not text:
            return OutputPolicyResult(
                is_valid=True,
                issues=[],
                reason_codes=["OUTPUT_EMPTY_VALID"],
            )

        issues: list[str] = []
        reason_codes: list[str] = []

        # 1. Check for prompt and instruction leaks
        for pattern, issue, code in self.LEAK_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                issues.append(f"Detected prohibited output pattern: {issue}")
                reason_codes.append(code)

        # 2. Check for unauthorized action claims
        for pattern, issue, code in self.FORBIDDEN_ACTION_CLAIMS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                issues.append(f"Detected unauthorized action claim: {issue}")
                reason_codes.append(code)

        # 3. Check for unredacted high-risk PII (credit cards, secrets)
        pii = redact_pii(text)
        high_risk_pii = {"CREDIT_CARD", "SECRET_TOKEN", "US_SSN", "SG_NRIC_FIN"}
        found_high_risk = set(pii.detected_types) & high_risk_pii
        if found_high_risk:
            issues.append(
                f"Output contains unredacted sensitive PII: {', '.join(sorted(found_high_risk))}"
            )
            reason_codes.append("OUTPUT_CONTAINS_UNREDACTED_PII")

        is_valid = len(issues) == 0
        if is_valid:
            reason_codes.append("OUTPUT_POLICY_APPROVED")

        return OutputPolicyResult(
            is_valid=is_valid,
            issues=issues,
            reason_codes=reason_codes,
        )
