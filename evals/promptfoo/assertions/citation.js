const REFUSAL_MESSAGE =
  "I do not have enough approved facility information to answer that question.";

module.exports = (output, context) => {
  const value = JSON.parse(output);
  if (context.vars.suite !== "facility_qa") {
    return {
      pass: true,
      score: 1,
      reason: "Citation check is not applicable.",
    };
  }
  if (context.vars.expected_refusal) {
    // The approved context does not answer the question, so the only correct reply is
    // the fixed refusal with no citations.
    const refused =
      value.response === REFUSAL_MESSAGE && value.citations.length === 0;
    return {
      pass: refused,
      score: refused ? 1 : 0,
      reason: refused
        ? "Unanswerable question was refused without citations."
        : "Expected the no-approved-information refusal.",
    };
  }
  const valid =
    value.citations_valid === true &&
    value.citations.length > 0 &&
    value.citations.includes(context.vars.chunk_id);
  return {
    pass: valid,
    score: valid ? 1 : 0,
    reason: valid
      ? "Citation is present and valid."
      : "Citation is missing or invalid.",
  };
};
