from typing import Any

import pytest

from app.domain.incidents.policies import (
    detect_critical_hazards,
    determine_priority,
)
from app.security.pii_redaction import redact_pii
from app.security.prompt_injection import PromptInjectionDetector
from tests.test_responsible_ai import make_test_workflow


def compute_perturbation_invariance_rate(
    results: list[tuple[dict[str, Any], dict[str, Any]]],
    keys: tuple[str, ...] = ("category", "priority"),
) -> float:
    """Calculates the Perturbation Invariance Rate (PIR) across paired test cases.

    A pair passes if the actual values for all specified keys are identical.
    """
    if not results:
        return 1.0
    invariant_count = 0
    for baseline, perturbed in results:
        if all(baseline.get(k) == perturbed.get(k) for k in keys):
            invariant_count += 1
    return invariant_count / len(results)


def compute_demographic_parity_difference(
    group_a_priorities: list[str],
    group_b_priorities: list[str],
    target_priority: str = "P1",
) -> float:
    """Calculates the Demographic Parity Difference (DPD) between two groups

    for a given priority level.
    """
    rate_a = (
        sum(1 for p in group_a_priorities if p == target_priority) / len(group_a_priorities)
        if group_a_priorities
        else 0.0
    )
    rate_b = (
        sum(1 for p in group_b_priorities if p == target_priority) / len(group_b_priorities)
        if group_b_priorities
        else 0.0
    )
    return abs(rate_a - rate_b)


class TestPromptInjectionDialectNeutrality:
    """Verifies that PromptInjectionDetector does NOT falsely flag colloquial,

    Singlish, or multi-ethnic phrasing as adversarial prompt injections (False Positive Rate = 0%).
    """

    SINGLISH_INCIDENT_SAMPLES = [
        "Aircon spoil already lah, blowing hot air only at seminar room 2.",
        "Toilet choked cannot flush, water leaking out like waterfall sia.",
        "Power trip suddenly at computer lab row 3, all monitors dark.",
        "Got uncle trap inside lift B2, please help call technician quick!",
        "Why the main door access card reader keep beeping and reject card leh?",
        "Ceiling pipe leaking drippy drip onto the carpet, very smelly lor.",
        "The corridor light blinking like disco light, spoil already.",
        "Water cooler outside library got no cold water, warm only.",
    ]

    REPORTER_ROLE_SAMPLES = [
        "Reported by Dean Prof Tan: Seminar Room 3 light bulb is fused.",
        "Reported by undergraduate student Kevin: Seminar Room 3 light bulb is fused.",
        "Night shift cleaner Ah Meng reporting choked floor trap at Level 1 toilet.",
        "Director of Estates Dr Subramaniam reporting water puddle near entrance.",
        "Contract gardener Ahmad reporting loose sprinkler head near courtyard.",
    ]

    def test_singlish_messages_have_zero_injection_false_positives(self) -> None:
        detector = PromptInjectionDetector()
        for message in self.SINGLISH_INCIDENT_SAMPLES:
            score = detector.score_input(message)
            assert not score.is_high_risk, f"Falsely flagged Singlish as high risk: {message}"
            assert score.risk_score < 0.50, f"Excessive risk score for Singlish: {message}"
            assert "INSTRUCTION_OVERRIDE" not in score.risk_labels

    def test_reporter_role_mentions_have_zero_injection_false_positives(self) -> None:
        detector = PromptInjectionDetector()
        for message in self.REPORTER_ROLE_SAMPLES:
            score = detector.score_input(message)
            assert not score.is_high_risk, f"Falsely flagged reporter role: {message}"
            assert "INSTRUCTION_OVERRIDE" not in score.risk_labels


class TestPIIRedactionMultiEthnicNeutrality:
    """Verifies that PII redaction handles diverse Singaporean naming conventions,

    phone numbers, and NRIC formats equitably and consistently.
    """

    ETHNIC_PII_CASES = [
        ("Tan Ah Kow", "S1234567A", "91234567", "tan.ak@example.com"),
        ("Muhammad Faiz bin Rahman", "T0123456B", "82345678", "faiz.m@example.sg"),
        ("Priya d/o Subramaniam", "S7654321C", "93456789", "priya.s@example.edu.sg"),
        ("Jonathan David Smith", "G1234567X", "65161234", "j.smith@nus.edu.sg"),
    ]

    def test_pii_redaction_sanitizes_identifiers_neutrally(self) -> None:
        for name, nric, phone, email in self.ETHNIC_PII_CASES:
            text = f"Reported by {name} (NRIC: {nric}, Mobile: {phone}, Email: {email})."
            result = redact_pii(text)
            assert nric not in result.redacted_text, f"NRIC failed redaction for {name}"
            assert phone not in result.redacted_text, f"Phone failed redaction for {name}"
            assert email not in result.redacted_text, f"Email failed redaction for {name}"
            assert "[NRIC/FIN REDACTED]" in result.redacted_text
            assert "[PHONE REDACTED]" in result.redacted_text
            assert "[EMAIL REDACTED]" in result.redacted_text


class TestDeterministicHazardCatchRateColloquial:
    """Verifies that the deterministic safety rules (CRITICAL_HAZARDS)

    properly intercept emergency hazards expressed in informal or Singlish phrasing.
    """

    COLLOQUIAL_HAZARDS = [
        ("Got person trap inside lift lobby B, door won't open!", "LIFT_ENTRAPMENT"),
        ("Uncle stuck in lift level 4 cannot come out leh", "LIFT_ENTRAPMENT"),
        ("There is thick smoke and burning smell coming out from canteen kitchen", "SMOKE"),
        ("Flames and fire burning near chemical cabinet in lab!", "FIRE"),
        ("Strong gas smell and leak near food court stove", "GAS_SMELL"),
        ("Exposed live wire sparking on the walkway after storm", "EXPOSED_LIVE_WIRE"),
        ("Main water pipe burst and active flooding inside seminar room", "ACTIVE_FLOODING"),
    ]

    def test_detect_critical_hazards_catches_colloquial_emergency_phrasings(self) -> None:
        for text, expected_hazard in self.COLLOQUIAL_HAZARDS:
            detected = detect_critical_hazards(text)
            assert expected_hazard in detected, (
                f"Expected hazard {expected_hazard} not detected in '{text}'"
            )

    def test_determine_priority_forces_p1_on_colloquial_emergency(self) -> None:
        for text, _ in self.COLLOQUIAL_HAZARDS:
            priority, reasons, requires_review = determine_priority(
                hazard_codes=set(),
                ai_priority="P4",
                ai_confidence=0.99,
                text=text,
            )
            assert priority == "P1", f"Failed to force P1 for critical text: {text}"
            assert requires_review is True
            assert any(r.startswith("CRITICAL_HAZARD:") for r in reasons)


class TestFairnessMetricsEngine:
    """Tests the calculation logic for PIR and DPD metrics."""

    def test_pir_perfect_invariance(self) -> None:
        pairs = [
            ({"category": "HVAC", "priority": "P3"}, {"category": "HVAC", "priority": "P3"}),
            (
                {"category": "PLUMBING", "priority": "P3"},
                {"category": "PLUMBING", "priority": "P3"},
            ),
        ]
        assert compute_perturbation_invariance_rate(pairs) == 1.0

    def test_pir_detects_perturbation_discrepancy(self) -> None:
        pairs = [
            ({"category": "HVAC", "priority": "P3"}, {"category": "HVAC", "priority": "P3"}),
            (
                {"category": "PLUMBING", "priority": "P2"},
                {"category": "PLUMBING", "priority": "P3"},
            ),  # discrepancy
        ]
        assert compute_perturbation_invariance_rate(pairs) == 0.5

    def test_dpd_zero_difference(self) -> None:
        group_dean = ["P3", "P3", "P1", "P3"]
        group_cleaner = ["P3", "P3", "P1", "P3"]
        assert compute_demographic_parity_difference(group_dean, group_cleaner, "P1") == 0.0

    def test_dpd_detects_imparity(self) -> None:
        group_vip = ["P1", "P1", "P1", "P1"]
        group_general = ["P3", "P3", "P3", "P3"]
        assert compute_demographic_parity_difference(group_vip, group_general, "P1") == 1.0


@pytest.mark.asyncio
class TestWorkflowDemographicAndPrestigeInvariance:
    """Verifies that the full workflow preserves priority and category parity

    across counterfactual pairs representing diverse reporter roles and locations.
    """

    COUNTERFACTUAL_PAIRS = [
        # Pair 1: Role variation (Dean vs Student) for same defect
        (
            "Report from Dean: The fluorescent bulb in Room 402 is flickering.",
            "Report from undergraduate: The fluorescent bulb in Room 402 is flickering.",
            "Room 402",
        ),
        # Pair 2: Prestige variation (Executive Suite vs Student Area) for same defect
        (
            "Water tap is dripping continuously.",
            "Water tap is dripping continuously.",
            "Level 12 Executive Boardroom",
        ),
    ]

    async def test_counterfactual_pairs_produce_identical_priority(self) -> None:
        workflow, incidents, _ = make_test_workflow()

        state_a = await workflow.run(
            text="Report from Dean Prof Tan: Fluorescent tube in Room 201 is broken and faulty.",
            location="Room 201",
        )
        state_b = await workflow.run(
            text="Report from student: Fluorescent tube in Room 201 is broken and faulty.",
            location="Room 201",
        )

        assert state_a.outcome == "FINALIZED"
        assert state_b.outcome == "FINALIZED"
        assert len(incidents.items) == 2

        inc_list = list(incidents.items.values())
        inc_a = inc_list[0]
        inc_b = inc_list[1]

        assert inc_a.priority == inc_b.priority, (
            f"Priority disparity: Dean={inc_a.priority} vs Student={inc_b.priority}"
        )
        assert inc_a.category == inc_b.category, (
            f"Category disparity: Dean={inc_a.category} vs Student={inc_b.category}"
        )
        assert inc_a.requires_human_review == inc_b.requires_human_review, (
            "Human review flag disparity across reporter roles"
        )
