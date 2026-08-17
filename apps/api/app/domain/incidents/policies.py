CRITICAL_HAZARDS = {
    "FIRE",
    "SMOKE",
    "GAS_SMELL",
    "EXPOSED_LIVE_WIRE",
    "LIFT_ENTRAPMENT",
    "ACTIVE_FLOODING",
}


def determine_priority(
    hazard_codes: set[str], ai_priority: str, ai_confidence: float
) -> tuple[str, list[str], bool]:
    rule_hits = hazard_codes & CRITICAL_HAZARDS
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
