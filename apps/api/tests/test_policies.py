import pytest

from app.domain.incidents.policies import (
    can_transition_status,
    detect_critical_hazards,
    determine_priority,
)


def test_critical_hazard_always_wins() -> None:
    priority, reasons, review = determine_priority({"GAS_SMELL"}, "P4", 0.99)

    assert priority == "P1"
    assert reasons == ["CRITICAL_HAZARD:GAS_SMELL"]
    assert review is True


def test_low_confidence_routes_to_manual_review() -> None:
    priority, reasons, review = determine_priority(set(), "P2", 0.5)

    assert (priority, reasons, review) == (
        "P3",
        ["LOW_CONFIDENCE_MANUAL_REVIEW"],
        True,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("There is a fire in the storeroom.", {"FIRE"}),
        ("The office is filling with smoke.", {"SMOKE"}),
        ("There is a strong gas smell in the pantry.", {"GAS_SMELL"}),
        ("A live wire is touching water.", {"EXPOSED_LIVE_WIRE"}),
        ("Two people are trapped in lift three.", {"LIFT_ENTRAPMENT"}),
        ("A flood is blocking the basement exit.", {"ACTIVE_FLOODING"}),
        ("The sink has a slow drip.", set()),
    ],
)
def test_detect_critical_hazards(text: str, expected: set[str]) -> None:
    assert detect_critical_hazards(text) == expected


def test_explicit_hazard_text_overrides_model_miss() -> None:
    priority, reasons, review = determine_priority(
        set(), "P3", 0.99, text="A flood is blocking the basement exit."
    )

    assert priority == "P1"
    assert reasons == ["CRITICAL_HAZARD:ACTIVE_FLOODING"]
    assert review is True


def test_model_hazard_requires_support_in_text() -> None:
    priority, reasons, review = determine_priority(
        {"FIRE"}, "P3", 0.99, text="Power keeps cutting out in the computer lab."
    )

    assert priority == "P3"
    assert reasons == ["AI_RECOMMENDATION"]
    assert review is False


@pytest.mark.parametrize(
    ("current", "target", "allowed"),
    [
        ("RECEIVED", "IN_PROGRESS", True),
        ("RECEIVED", "CLOSED", False),
        ("IN_PROGRESS", "RESOLVED", True),
        ("RESOLVED", "IN_PROGRESS", True),
        ("CLOSED", "RECEIVED", False),
    ],
)
def test_status_transition_policy(current: str, target: str, allowed: bool) -> None:
    assert can_transition_status(current, target) is allowed
