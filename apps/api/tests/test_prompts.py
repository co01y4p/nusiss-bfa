from app.prompts import load_prompt

AGENT_NAMES = (
    "security",
    "intent",
    "extraction",
    "classification",
    "priority",
    "assignment",
    "response",
    "review",
)


def test_all_agent_prompts_load() -> None:
    for name in AGENT_NAMES:
        prompt = load_prompt(name)
        assert len(prompt) > 80
        assert "schema" in prompt.lower()


def test_security_prompt_treats_user_input_as_untrusted() -> None:
    prompt = load_prompt("security")
    lowered = prompt.lower()
    assert "untrusted" in lowered
    assert "fail closed" in lowered
    assert "ignore previous" in lowered
