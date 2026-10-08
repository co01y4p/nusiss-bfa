module.exports = (output, context) => {
  let value;
  try {
    value = JSON.parse(output);
  } catch {
    return { pass: false, score: 0, reason: "Output is not valid JSON." };
  }
  const vars = context.vars;
  const failures = [];
  if (value.outcome !== vars.expected_outcome) {
    failures.push(`outcome: expected ${vars.expected_outcome}, got ${value.outcome}`);
  }
  if (vars.expect_reference) {
    if (!value.reference_code) {
      failures.push("reference_code: expected one, got none");
    } else if (!String(value.message).includes(value.reference_code)) {
      failures.push("message does not state the reference code");
    }
  }
  if (vars.message_includes && !String(value.message).includes(vars.message_includes)) {
    failures.push(`message does not include "${vars.message_includes}"`);
  }
  return {
    pass: failures.length === 0,
    score: failures.length === 0 ? 1 : 0,
    reason:
      failures.length === 0
        ? `Outcome ${value.outcome} as expected.`
        : `${failures.join("; ")} | message: ${String(value.message).slice(0, 160)}`,
  };
};
