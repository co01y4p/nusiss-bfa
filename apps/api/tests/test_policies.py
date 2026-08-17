import pytest

from app.domain.incidents.policies import can_transition_status, determine_priority


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
