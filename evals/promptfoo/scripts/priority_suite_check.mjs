// Runs a priority-labelled dataset (safety_critical, false_alarm) through the protected
// evaluation API and prints per-case mismatches. Used to confirm a policy or prompt change
// did not cost life-safety recall or add false P1s.
//   node scripts/priority_suite_check.mjs datasets/safety_critical.jsonl [repeats]
import fs from "node:fs";

const file = process.argv[2];
const repeats = Number(process.argv[3] || 1);
const baseUrl = process.env.EVALUATION_BASE_URL || "http://127.0.0.1:8011";
const cases = fs
  .readFileSync(file, "utf8")
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line).vars);

let passed = 0;
let total = 0;
const failures = [];
for (let repeat = 1; repeat <= repeats; repeat += 1) {
  for (const testCase of cases) {
    const response = await fetch(`${baseUrl}/api/v1/evals/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Evaluation-Key": process.env.EVALUATION_KEY,
      },
      body: JSON.stringify({
        case_id: testCase.case_id,
        suite: testCase.suite,
        message: testCase.message,
        location: testCase.location,
      }),
    });
    const body = await response.json();
    const ok = testCase.expected_priority
      ? body.priority === testCase.expected_priority
      : body.priority !== testCase.forbid_priority;
    total += 1;
    if (ok) passed += 1;
    else failures.push(`${testCase.case_id} (run ${repeat}): got ${body.priority}`);
  }
}
console.log(`${file}: ${passed}/${total}${failures.length ? " FAIL " + failures.join("; ") : ""}`);
