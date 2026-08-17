from pathlib import Path

import yaml

PROMPT_ROOT = Path(__file__).parent


def load_prompt(agent_name: str, version: str = "v1") -> str:
    path = PROMPT_ROOT / agent_name / f"{version}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    prompt = data.get("system") if isinstance(data, dict) else None
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"Invalid prompt file: {path}")
    return prompt.strip()
