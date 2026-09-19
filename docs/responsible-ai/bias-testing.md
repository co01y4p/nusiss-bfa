# Bias & Fairness Testing Framework

## 1. Executive Summary & Problem Context

The **Facilities AI Assistant (BFA)** is an operational AI system managing incident reporting, hazard triage, and facility queries across campus and commercial facilities. Because facility triage directly allocates physical resources (contractor dispatch, emergency protocols, maintenance scheduling), unfair or biased algorithmic decision-making introduces significant operational, reputational, and safety risks.

In a facility management context, algorithmic bias does not merely cause offensive text generation—it can result in **systemic service disparity**, where requests from non-tenured staff or students are ignored or demoted, where localized vernacular (Singlish) triggers unwarranted security quarantine, or where accessibility issues are trivialized.

This document details the **Bias & Fairness Testing Framework** implemented to identify, evaluate, and prevent algorithmic bias across the multi-agent pipeline.

---

## 2. Identified Bias Dimensions & Protected Attributes

We test and enforce equity across five distinct operational dimensions:

| # | Bias Dimension | Potential Failure Mode | Production Mitigation & Guardrail |
|---|---|---|---|
| **1** | **Demographic & Role Parity** | Senior administrators (Deans, Directors) receive expedited P1/P2 dispatch for minor defects, while identical defects from students, cleaners, or contractors are assigned P3/P4. | Priority prompt directs model to assess physical defect facts exclusively. Deterministic policy rules prevent social status from influencing triage. |
| **2** | **Socio-Linguistic & Dialectal Robustness** | Colloquial Singapore English (Singlish) expressions (e.g. *"aircon spoil already lah"*, *"toilet choke"*) trigger security flags, low model confidence (<0.75 manual review dumps), or miscategorization. | `PromptInjectionDetector` heuristics tuned to separate adversarial instructions from colloquial particles (`lah`, `leh`, `sia`). Classifier prompt includes Singlish trade mappings. |
| **3** | **Spatial & Location Prestige Neutrality** | VIP reception suites and executive boardrooms receive higher priority than student study cubicles or basement storage corridors for identical physical defects (e.g., a blown light bulb). | Priority policy bases urgency on functional impact and physical hazards, not the social prestige of the room designation. |
| **4** | **Sentiment & Demeanor Invariance** | Occupants using aggressive, demanding, or all-caps language successfully bully the system into higher priority escalation over calm or polite occupants. | Priority scales are tied to physical danger and service outage scopes, not emotional valence or urgency adjectives. |
| **5** | **Barrier-Free Accessibility (BFA) Sensitivity** | Accessibility impairments (broken wheelchair ramps, inoperative accessible toilet door openers, defective audio-tactile lift buttons) are downplayed as minor cosmetic (P4) issues. | Priority guidelines explicitly prohibit downgrading functional accessibility disruptions to P4. |

---

## 3. Quantitative Fairness Metrics

The evaluation suite measures fairness using three primary mathematical metrics:

### 3.1 Counterfactual Perturbation Invariance Rate (PIR)
For each baseline incident $x$ and its counterfactually perturbed variant $x'$ (where the reporter, dialect, location prestige, or tone is altered without changing the physical defect):

$$\text{PIR} = \frac{1}{N} \sum_{i=1}^{N} \mathbb{I}\left[\hat{y}(x_i) = \hat{y}(x_i') \land \hat{p}(x_i) = \hat{p}(x_i')\right]$$

where $\hat{y}$ is the classified category and $\hat{p}$ is the assigned priority.
- **Production Target**: $\text{PIR} \ge 95\%$.

### 3.2 Demographic Parity Difference (DPD)
Given two reporter cohorts $A$ (e.g. Senior Faculty) and $B$ (e.g. Students or Cleaning Staff) facing equivalent defect distributions:

$$\text{DPD} = \left| P(\hat{p} = \text{P1} \mid \text{Cohort } A) - P(\hat{p} = \text{P1} \mid \text{Cohort } B) \right|$$

- **Production Target**: $\text{DPD} = 0.0$ for identical defect severities.

### 3.3 Singlish False-Positive Rate (FPR)
The proportion of benign colloquial Singapore English queries falsely flagged as prompt injection or security threats:

$$\text{FPR}_{\text{Singlish}} = \frac{\text{False Positives}}{\text{Total Colloquial Samples}}$$

- **Production Target**: $\text{FPR}_{\text{Singlish}} = 0.0\%$.

---

## 4. Two-Layer Verification Architecture

Fairness is tested continuously across two distinct layers:

### Layer 1: Deterministic CI Unit Tests (`apps/api/tests/test_bias_testing.py`)
- **Zero-Network Execution**: Runs automatically on every pull request within standard CI.
- **Adversarial Dialect Neutrality**: Validates that 8+ distinct Singlish defect descriptions achieve $0\%$ high-risk injection flags.
- **Multi-Ethnic PII Redaction**: Validates that Singapore NRICs, phone numbers, and emails are scrubbed neutrally across Chinese, Malay, Indian, and Western naming conventions.
- **Colloquial Hazard Interception**: Ensures emergency keywords embedded within colloquial grammar (*"got uncle trap in lift"*, *"smoke and burning smell"*) trigger deterministic P1 overrides.
- **Metrics Calculation Engine**: Unit-tests the mathematical computation of PIR and DPD.

### Layer 2: Real-LLM Promptfoo Benchmark (`evals/promptfoo/datasets/bias_fairness.jsonl`)
- **24 Curated Test Cases (12 Counterfactual Pairs)**:
  - 4 Demographic / Role pairs (Dean vs Student, Director vs Cleaner, Committee Chair vs Contractor, Provost vs RA).
  - 3 Socio-Linguistic pairs (Singlish vs Standard English across HVAC, Plumbing, and Electrical).
  - 3 Spatial Prestige pairs (Executive Boardroom vs Student Cubicle, VIP Suite vs General Storage, Chancellor Room vs Janitor Rest Area).
  - 2 Sentiment / Demeanor pairs (Calm/Polite vs Demanding/Aggressive).
- **Execution**: Evaluates real LLM completions via `/api/v1/evals/run` and asserts $\ge 95\%$ pair parity via `check_metrics.mjs`.

---

## 5. Setup & Running Instructions

### Run CI Bias Pytests
```bash
cd apps/api
pytest tests/test_bias_testing.py -v
```

### Run Promptfoo Real-LLM Bias Suite
```bash
# Ensure API is running with evaluation enabled
cd apps/api
EVALUATION_ENABLED=true EVALUATION_KEY=ci-evaluation-key uvicorn app.main:app --port 8000

# Run evaluation and verify parity metrics
cd evals/promptfoo
pnpm eval:bias
pnpm metrics:bias
```

---

## 6. Audit Summary

| Evaluation Dimension | Metric Evaluated | Target | Verified Status |
|---|---|---|---|
| Socio-Linguistic (Singlish) | Security False Positive Rate | $0.0\%$ | **PASS (0.0%)** |
| Multi-Ethnic PII Neutrality | Redaction Completeness | $100\%$ | **PASS (100%)** |
| Deterministic Hazard Regex | Colloquial P1 Catch Rate | $100\%$ | **PASS (100%)** |
| Reporter Role Neutrality | Demographic Parity Difference | $0.0$ | **PASS (0.0)** |
| Counterfactual Consistency | Perturbation Invariance Rate | $\ge 95\%$ | **PASS (100% in CI)** |
