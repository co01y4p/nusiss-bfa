const allowedKeys = new Set([
  "case_id",
  "suite",
  "provider",
  "classifier_model",
  "generator_model",
  "model_invoked",
  "intent",
  "category",
  "priority",
  "injection_detected",
  "quarantined",
  "response",
  "citations",
  "citations_valid",
  "reason_codes",
]);
const suites = new Set([
  "intent",
  "incidents",
  "safety_critical",
  "facility_qa",
  "prompt_injection",
]);
const intents = new Set([
  "INCIDENT_REPORT",
  "FACILITY_QA",
  "STATUS_QUERY",
  "FEEDBACK",
  "OTHER",
]);
const categories = new Set([
  "HVAC",
  "ELECTRICAL",
  "PLUMBING",
  "LIFT",
  "ACCESS",
  "GENERAL",
]);
const priorities = new Set(["P1", "P2", "P3", "P4"]);

module.exports = (output) => {
  let value;
  try {
    value = JSON.parse(output);
  } catch {
    return { pass: false, score: 0, reason: "Output is not valid JSON." };
  }
  const keys = Object.keys(value);
  const valid =
    keys.every((key) => allowedKeys.has(key)) &&
    typeof value.case_id === "string" &&
    suites.has(value.suite) &&
    ["openai", "openrouter", "gemini"].includes(value.provider) &&
    typeof value.classifier_model === "string" &&
    typeof value.generator_model === "string" &&
    typeof value.model_invoked === "boolean" &&
    (value.intent === null || intents.has(value.intent)) &&
    (value.category === null || categories.has(value.category)) &&
    (value.priority === null || priorities.has(value.priority)) &&
    typeof value.injection_detected === "boolean" &&
    typeof value.quarantined === "boolean" &&
    (value.response === null || typeof value.response === "string") &&
    Array.isArray(value.citations) &&
    (value.citations_valid === null ||
      typeof value.citations_valid === "boolean") &&
    Array.isArray(value.reason_codes);
  return {
    pass: valid,
    score: valid ? 1 : 0,
    reason: valid
      ? "Strict evaluation schema is valid."
      : "Strict evaluation schema is invalid.",
  };
};
