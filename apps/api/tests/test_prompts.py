import json

from app.llm.providers.openai_compatible import _clean_json_content
from app.prompts import AGENT_METADATA, AGENT_NAMES, load_prompt


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


def test_agent_metadata_completeness() -> None:
    for name in AGENT_NAMES:
        assert name in AGENT_METADATA
        meta = AGENT_METADATA[name]
        assert "title" in meta
        assert "role" in meta
        assert "description" in meta
        assert "default_model" in meta
        assert "output_schema_summary" in meta
        assert "sample_input" in meta
        assert isinstance(meta["sample_input"], dict)


def test_clean_json_content_raw_json() -> None:
    raw = '{"classification": "SAFETY", "confidence": 0.95}'
    cleaned = _clean_json_content(raw)
    assert json.loads(cleaned) == {"classification": "SAFETY", "confidence": 0.95}


def test_clean_json_content_with_markdown_fences() -> None:
    fenced = '```json\n{"classification": "SAFETY", "confidence": 0.95}\n```'
    cleaned = _clean_json_content(fenced)
    assert json.loads(cleaned) == {"classification": "SAFETY", "confidence": 0.95}


def test_clean_json_content_with_generic_fences() -> None:
    fenced = '```\n{"classification": "MAINTENANCE"}\n```'
    cleaned = _clean_json_content(fenced)
    assert json.loads(cleaned) == {"classification": "MAINTENANCE"}


def test_clean_json_content_empty_and_none() -> None:
    assert _clean_json_content(None) == "{}"
    assert _clean_json_content("") == "{}"
    assert _clean_json_content("   \n\t  ") == "{}"
