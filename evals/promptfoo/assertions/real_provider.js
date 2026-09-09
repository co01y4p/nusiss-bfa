module.exports = (output) => {
  const value = JSON.parse(output);
  const validProvider = ["openai", "openrouter", "gemini"].includes(
    value.provider,
  );
  return {
    pass: validProvider,
    score: validProvider ? 1 : 0,
    reason: validProvider
      ? "A real LLM provider is configured for evaluation."
      : "A fake provider was used.",
  };
};
