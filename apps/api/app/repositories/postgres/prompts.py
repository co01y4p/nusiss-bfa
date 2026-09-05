from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import AgentPromptModel
from app.prompts import AGENT_METADATA, load_prompt


def utc_now() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyPromptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_active_prompt(self, agent_name: str) -> str:
        """Get the active system prompt for an agent, falling back to default v1.yaml."""
        if agent_name not in AGENT_METADATA:
            raise ValueError(f"Unknown agent name: {agent_name}")
        row = self.session.scalar(
            select(AgentPromptModel).where(
                AgentPromptModel.agent_name == agent_name,
                AgentPromptModel.is_active.is_(True),
            )
        )
        if row and row.system_prompt and row.system_prompt.strip():
            return row.system_prompt.strip()
        return load_prompt(agent_name, version="v1")

    def get_prompt_record(self, agent_name: str) -> AgentPromptModel | None:
        return self.session.scalar(
            select(AgentPromptModel).where(
                AgentPromptModel.agent_name == agent_name,
                AgentPromptModel.is_active.is_(True),
            )
        )

    def get_all_prompts(self) -> list[dict[str, Any]]:
        """List all 8 agents with their metadata, active prompt, and default prompt."""
        records = {
            row.agent_name: row
            for row in self.session.scalars(
                select(AgentPromptModel).where(AgentPromptModel.is_active.is_(True))
            ).all()
        }

        results: list[dict[str, Any]] = []
        for name, meta in AGENT_METADATA.items():
            default_prompt = load_prompt(name, version="v1")
            custom_row = records.get(name)
            is_custom = custom_row is not None and bool(custom_row.system_prompt.strip())
            active_prompt = (
                custom_row.system_prompt.strip() if is_custom and custom_row else default_prompt
            )

            results.append(
                {
                    "name": name,
                    "title": meta["title"],
                    "role": meta["role"],
                    "description": meta["description"],
                    "default_model": meta["default_model"],
                    "output_schema_summary": meta["output_schema_summary"],
                    "sample_input": meta["sample_input"],
                    "system_prompt": active_prompt,
                    "default_prompt": default_prompt,
                    "is_customized": is_custom,
                    "version": custom_row.version if is_custom and custom_row else "v1 (built-in)",
                    "updated_at": custom_row.updated_at if is_custom and custom_row else None,
                    "change_summary": custom_row.change_summary
                    if is_custom and custom_row
                    else None,
                    "char_count": len(active_prompt),
                    "line_count": len(active_prompt.splitlines()),
                }
            )
        return results

    def save_prompt(
        self,
        agent_name: str,
        system_prompt: str,
        *,
        change_summary: str | None = None,
        version: str = "custom",
    ) -> AgentPromptModel:
        if agent_name not in AGENT_METADATA:
            raise ValueError(f"Unknown agent name: {agent_name}")
        clean_prompt = system_prompt.strip()
        if not clean_prompt:
            raise ValueError("System prompt cannot be empty")

        row = self.session.scalar(
            select(AgentPromptModel).where(AgentPromptModel.agent_name == agent_name)
        )
        now = utc_now()
        if row is None:
            row = AgentPromptModel(
                agent_name=agent_name,
                version=version,
                system_prompt=clean_prompt,
                is_active=True,
                change_summary=change_summary,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.system_prompt = clean_prompt
            row.version = version
            row.is_active = True
            row.change_summary = change_summary
            row.updated_at = now

        self.session.commit()
        self.session.refresh(row)
        return row

    def reset_to_default(self, agent_name: str) -> str:
        if agent_name not in AGENT_METADATA:
            raise ValueError(f"Unknown agent name: {agent_name}")
        row = self.session.scalar(
            select(AgentPromptModel).where(AgentPromptModel.agent_name == agent_name)
        )
        if row:
            row.is_active = False
            row.updated_at = utc_now()
            self.session.commit()
        return load_prompt(agent_name, version="v1")
