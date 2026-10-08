import pytest

from app.agents.priority import PriorityAgent
from app.domain.incidents.policies import (
    can_transition_status,
    detect_critical_hazards,
    determine_priority,
)
from app.llm.fake import FakeStructuredLLM


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
        ("I can smell gas in the kitchen.", {"GAS_SMELL"}),
        ("Sparks are coming out of the plug socket.", {"EXPOSED_LIVE_WIRE"}),
        ("The basement car park is flooded.", {"ACTIVE_FLOODING"}),
        ("The fire alarm is going off on Level 3.", {"FIRE"}),
        ("The smoke detector in room 204 keeps beeping for a battery change.", set()),
        ("The fire extinguisher sticker in the corridor is out of date.", set()),
        ("We are having a fire drill at 3pm.", set()),
        ("The fire door is jammed and there is smoke behind it.", {"SMOKE"}),
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


@pytest.mark.asyncio
async def test_priority_model_sees_unconfirmed_hazards_as_suspected_only() -> None:
    llm = FakeStructuredLLM(
        handlers={
            "PrioritySignalOutput": {
                "priority": "P3",
                "confidence": 0.9,
                "reason_codes": ["ADVISORY_P3_LOCALIZED"],
            }
        }
    )
    agent = PriorityAgent(llm, model="fake", timeout_seconds=1)

    decision = await agent.decide(
        {
            "text": "Fix the dripping washroom tap in Room 102 IMMEDIATELY!",
            "hazard_codes": ["EXPOSED_LIVE_WIRE"],
            "category": "PLUMBING",
        }
    )

    sent = llm.calls[0]["payload"]
    assert sent["hazard_codes"] == []
    assert sent["suspected_hazards"] == ["EXPOSED_LIVE_WIRE"]
    assert decision.priority.value == "P3"


def test_model_p1_without_any_hazard_signal_is_capped_and_escalated() -> None:
    priority, reasons, review = determine_priority(
        set(), "P1", 0.95, text="Power trip at row 4 sockets, all wall plugs have no power."
    )

    assert priority == "P2"
    assert reasons == ["AI_P1_WITHOUT_HAZARD_CAPPED"]
    assert review is True


def test_model_p1_backed_by_an_extracted_hazard_is_kept() -> None:
    priority, reasons, _ = determine_priority(
        {"EXPOSED_LIVE_WIRE"},
        "P1",
        0.95,
        text="Water is pouring from the ceiling onto the electrical switchboard.",
    )

    assert priority == "P1"
    assert reasons == ["AI_RECOMMENDATION"]
