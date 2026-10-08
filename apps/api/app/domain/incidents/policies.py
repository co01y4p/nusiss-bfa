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
        r"\b(?:gas\s+(?:smell|leak|odou?r)|lpg|natural\s+gas|"
        r"smell(?:s|ed|ing)?\s+(?:of\s+)?gas|gas\s+(?:is\s+)?leaking|leaking\s+gas)\b",
        re.IGNORECASE,
    ),
    "EXPOSED_LIVE_WIRE": re.compile(
        r"\b(?:live\s+wire|exposed\s+(?:wire|cable|conductor)|sparking\s+(?:wire|cable)|"
        r"sparks|sparking)\b",
        re.IGNORECASE,
    ),
    "LIFT_ENTRAPMENT": re.compile(
        r"\b(?:stuck|trapped|trap)\b.{0,40}\b(?:lift|elevator)\b|"
        r"\b(?:lift|elevator)\b.{0,40}\b(?:stuck|trapped|trap)\b",
        re.IGNORECASE,
    ),
    "ACTIVE_FLOODING": re.compile(r"\b(?:flood|flooded|flooding)\b", re.IGNORECASE),
}

# Named safety equipment and routine safety activities. "The fire extinguisher sticker
# is out of date" or "the smoke detector needs a battery" mention the hazard word but
# report no hazard, so these phrases are removed before matching. Alarm activations
# ("the fire alarm is going off") are deliberately NOT listed: they stay critical.
SAFETY_EQUIPMENT_PATTERN = re.compile(
    r"\b(?:fire\s+(?:extinguishers?|drills?|doors?|exits?|escapes?|safety|hose(?:\s+reels?)?|"
    r"blankets?|wardens?|certificates?)|smoke\s+detectors?)\b",
    re.IGNORECASE,
)


def detect_critical_hazards(text: str) -> set[str]:
    text = SAFETY_EQUIPMENT_PATTERN.sub(" ", text)
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
    if ai_priority == "P1" and not hazard_codes & CRITICAL_HAZARDS:
        # P1 is reserved for the listed life-safety hazards. A model P1 with no hazard
        # signal at all (neither in the text nor proposed by extraction) is capped at
        # P2 and still escalated to a manager, so nothing urgent is silently dropped.
        return "P2", ["AI_P1_WITHOUT_HAZARD_CAPPED"], True
    return ai_priority, ["AI_RECOMMENDATION"], ai_priority in {"P1", "P2"}


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "RECEIVED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"RESOLVED"},
    "RESOLVED": {"CLOSED", "IN_PROGRESS"},
    "CLOSED": set(),
}


def can_transition_status(current: str, target: str) -> bool:
    return current == target or target in ALLOWED_STATUS_TRANSITIONS.get(current, set())


# Placeholder locations carry no positional information; embedding them would make
# every location-less report "match" every other one at similarity 1.0.
_UNSPECIFIED_LOCATIONS = {
    "",
    "unspecified",
    "unknown",
    "not specified",
    "not provided",
    "n/a",
    "na",
    "none",
    "null",
}


def is_unspecified_location(location: str | None) -> bool:
    if location is None:
        return True
    return location.strip().strip(".").lower() in _UNSPECIFIED_LOCATIONS
