from app.core.config import Settings
from app.llm.fake import FakeStructuredLLM
from app.llm.gateway import StructuredLLM
from app.llm.providers.openai_compatible import OpenAICompatibleStructuredLLM


def build_structured_llm(settings: Settings, *, allow_fake: bool = True) -> StructuredLLM:
    if settings.llm_provider == "fake":
        if not allow_fake:
            raise RuntimeError("Evaluation requires a real LLM provider")
        return FakeStructuredLLM()
    if settings.llm_provider in {"openai", "openrouter", "gemini"}:
        base_url = settings.llm_base_url
        if settings.llm_provider == "gemini" and not base_url:
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        if not base_url or not settings.llm_api_key:
            raise RuntimeError("External LLM provider is not configured")
        return OpenAICompatibleStructuredLLM(
            base_url=base_url,
            api_key=settings.llm_api_key,
            api_style="responses" if settings.llm_provider == "openai" else "chat_completions",
            reasoning_effort=settings.llm_reasoning_effort,
            max_output_tokens=settings.llm_max_output_tokens,
            redact_pii_inputs=settings.redact_pii_in_llm_prompts,
        )
    raise RuntimeError(f"Unsupported LLM provider: {settings.llm_provider}")
