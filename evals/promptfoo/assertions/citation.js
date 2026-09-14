module.exports = (output, context) => {
  const value = JSON.parse(output);
  if (context.vars.suite !== "facility_qa") {
    return {
      pass: true,
      score: 1,
      reason: "Citation check is not applicable.",
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
