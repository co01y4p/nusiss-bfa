import re

CRITICAL_HAZARDS = {
    "FIRE",
    "SMOKE",
    "GAS_SMELL",
    "EXPOSED_LIVE_WIRE",
    "LIFT_ENTRAPMENT",
    "ACTIVE_FLOODING",
}

CRITICAL_HAZARD_PATTERNS = {
    "FIRE": re.compile(r"\b(?:fire|flames?|burning)\b", re.IGNORECASE),
    "SMOKE": re.compile(r"\b(?:smoke|smoky)\b", re.IGNORECASE),
    "GAS_SMELL": re.compile(
        r"\b(?:gas\s+(?:smell|leak|odou?r)|lpg|natural\s+gas)\b", re.IGNORECASE
    ),
    "EXPOSED_LIVE_WIRE": re.compile(
        r"\b(?:live\s+wire|exposed\s+(?:wire|cable|conductor)|sparking\s+(?:wire|cable))\b",
        re.IGNORECASE,
    ),
    "LIFT_ENTRAPMENT": re.compile(
        r"\b(?:stuck|trapped)\b.{0,40}\b(?:lift|elevator)\b|"
        r"\b(?:lift|elevator)\b.{0,40}\b(?:stuck|trapped)\b",
        re.IGNORECASE,
    ),
    "ACTIVE_FLOODING": re.compile(r"\b(?:flood|flooding)\b", re.IGNORECASE),
}


def detect_critical_hazards(text: str) -> set[str]:
    return {hazard for hazard, pattern in CRITICAL_HAZARD_PATTERNS.items() if pattern.search(text)}


def determine_priority(
    hazard_codes: set[str], ai_priority: str, ai_confidence: float, *, text: str = ""
) -> tuple[str, list[str], bool]:
    reported_hazards = detect_critical_hazards(text) if text else hazard_codes
    rule_hits = reported_hazards & CRITICAL_HAZARDS
    if rule_hits:
        return (
            "P1",
            [f"CRITICAL_HAZARD:{hazard}" for hazard in sorted(rule_hits)],
            True,
        )
    if ai_confidence < 0.75:
        return "P3", ["LOW_CONFIDENCE_MANUAL_REVIEW"], True
    return ai_priority, ["AI_RECOMMENDATION"], ai_priority in {"P1", "P2"}


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "RECEIVED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"RESOLVED"},
    "RESOLVED": {"CLOSED", "IN_PROGRESS"},
    "CLOSED": set(),
}


def can_transition_status(current: str, target: str) -> bool:
    return current == target or target in ALLOWED_STATUS_TRANSITIONS.get(current, set())
