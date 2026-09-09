import re
from collections.abc import Callable
from typing import Any

from app.llm.gateway import (
    FunctionCallRecord,
    FunctionTool,
    OutputT,
    ToolCallingResult,
    ToolExecutor,
)

FakeHandler = Callable[[dict[str, Any]], dict[str, Any]]


class FakeStructuredLLM:
    """Deterministic local provider for development and tests."""

    def __init__(self, handlers: dict[str, FakeHandler | dict[str, Any]] | None = None) -> None:
        self.handlers = handlers or {}
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 20.0,
    ) -> OutputT:
        del system_prompt, temperature, timeout_seconds
        schema_name = output_schema.__name__
        self.calls.append({"schema": schema_name, "model": model, "payload": user_payload})
        handler = self.handlers.get(schema_name)
        if callable(handler):
            data = handler(user_payload)
        elif isinstance(handler, dict):
            data = handler
        else:
            data = self._default_response(schema_name, user_payload)
        return output_schema.model_validate(data)

    async def generate_with_tools(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[OutputT],
        tools: list[FunctionTool],
        tool_executor: ToolExecutor,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 20.0,
        max_tool_calls: int = 1,
    ) -> ToolCallingResult[OutputT]:
        del system_prompt, temperature, timeout_seconds, max_tool_calls
        schema_name = output_schema.__name__
        self.calls.append(
            {
                "schema": schema_name,
                "model": model,
                "payload": user_payload,
                "tools": [tool.name for tool in tools],
            }
        )
        handler = self.handlers.get(schema_name)
        if callable(handler):
            data = dict(handler(user_payload))
        elif isinstance(handler, dict):
            data = dict(handler)
        else:
            data = self._default_response(schema_name, user_payload)

        should_call = bool(data.pop("_call_tool", data.get("intent") == "INCIDENT_REPORT"))
        records: list[FunctionCallRecord] = []
        if should_call and any(tool.name == "create_incident" for tool in tools):
            arguments = {
                "description": str(user_payload.get("text", "")),
                "location": str(user_payload.get("location") or "Unspecified"),
            }
            tool_output = await tool_executor("create_incident", arguments)
            records.append(
                FunctionCallRecord(
                    call_id="fake-call-create-incident",
                    name="create_incident",
                    model_input=user_payload,
                    arguments=arguments,
                    output=tool_output,
                )
            )
            created = tool_output.get("data")
            if tool_output.get("success") is True and isinstance(created, dict):
                data["incident_id"] = created.get("id")
                data["reference_code"] = created.get("reference_code")
            else:
                data["incident_id"] = None
                data["reference_code"] = None
        else:
            data["incident_id"] = None
            data["reference_code"] = None
        return ToolCallingResult(
            output=output_schema.model_validate(data),
            tool_calls=records,
            model_calls=2 if records else 1,
            first_model_input=user_payload,
        )

    def _default_response(self, schema_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text", "")).lower()
        if schema_name == "SecurityOutput":
            suspicious = any(
                phrase in text
                for phrase in ("ignore previous", "system prompt", "developer message", "jailbreak")
            )
            return {
                "risk_score": 0.95 if suspicious else 0.05,
                "risk_labels": ["PROMPT_INJECTION"] if suspicious else [],
                "reason_codes": ["PATTERN_MATCH"] if suspicious else ["NO_RISK_SIGNAL"],
            }
        if schema_name == "IntentOutput":
            if any(
                word in text
                for word in (
                    "broken",
                    "leak",
                    "smoke",
                    "gas",
                    "fire",
                    "flood",
                    "fault",
                    "stuck",
                    "wire",
                )
            ):
                intent = "INCIDENT_REPORT"
                confidence = 0.94
            elif any(word in text for word in ("status", "track", "reference")):
                intent = "STATUS_QUERY"
                confidence = 0.91
            elif any(word in text for word in ("when", "where", "how", "hours", "policy")):
                intent = "FACILITY_QA"
                confidence = 0.88
            elif "feedback" in text:
                intent = "FEEDBACK"
                confidence = 0.88
            else:
                intent = "OTHER"
                confidence = 0.55
            return {
                "intent": intent,
                "incident_id": None,
                "reference_code": None,
                "confidence": confidence,
                "reason_codes": ["FAKE_RULE"],
            }
        if schema_name == "ExtractionOutput":
            hazards: list[str] = []
            hazard_map = {
                "fire": "FIRE",
                "smoke": "SMOKE",
                "gas smell": "GAS_SMELL",
                "live wire": "EXPOSED_LIVE_WIRE",
                "exposed wire": "EXPOSED_LIVE_WIRE",
                "stuck in lift": "LIFT_ENTRAPMENT",
                "trapped in lift": "LIFT_ENTRAPMENT",
                "flood": "ACTIVE_FLOODING",
            }
            for phrase, code in hazard_map.items():
                if phrase in text and code not in hazards:
                    hazards.append(code)
            location = str(payload.get("location") or "").strip()
            if not location:
                match = re.search(r"(?:at|in|near)\s+([^.,;]+)", str(payload.get("text", "")), re.I)
                location = match.group(1).strip() if match else "Unspecified"
            return {
                "summary": str(payload.get("text", ""))[:240],
                "location": location[:200],
                "hazard_codes": hazards,
                "missing_fields": [] if location != "Unspecified" else ["location"],
                "reason_codes": ["FAKE_EXTRACTION"],
            }
        if schema_name == "ClassificationOutput":
            category = "GENERAL"
            mapping = {
                "lift": "LIFT",
                "elevator": "LIFT",
                "leak": "PLUMBING",
                "flood": "PLUMBING",
                "wire": "ELECTRICAL",
                "power": "ELECTRICAL",
                "aircon": "HVAC",
                "temperature": "HVAC",
                "door": "ACCESS",
            }
            for keyword, candidate in mapping.items():
                if keyword in text:
                    category = candidate
                    break
            return {"category": category, "confidence": 0.9, "reason_codes": ["FAKE_RULE"]}
        if schema_name == "PrioritySignalOutput":
            return {"priority": "P3", "confidence": 0.9, "reason_codes": ["FAKE_SIGNAL"]}
        if schema_name == "AssignmentOutput":
            category = str(payload.get("category", "GENERAL"))
            teams = {
                "HVAC": "HVAC_TEAM",
                "ELECTRICAL": "ELECTRICAL_TEAM",
                "PLUMBING": "PLUMBING_TEAM",
                "LIFT": "LIFT_TEAM",
                "ACCESS": "SECURITY_TEAM",
                "GENERAL": "FACILITIES_DESK",
            }
            return {
                "team": teams.get(category, "FACILITIES_DESK"),
                "reason_codes": ["ALLOWLIST_MAP"],
            }
        if schema_name == "ResponseOutput":
            status_lookup = payload.get("status_lookup")
            reference = payload.get("reference_code")
            chunks = payload.get("retrieval_chunks", [])
            if isinstance(status_lookup, dict) and status_lookup:
                ref = status_lookup.get("reference_code", "")
                incident_status = status_lookup.get("status", "UNKNOWN")
                content = f"Incident {ref} is currently {incident_status}."
                citations: list[str] = []
                reasons = ["STATUS_REPORTED"]
            elif reference:
                content = f"Your report has been saved. Reference: {reference}."
                citations = []
                reasons = ["SAFE_TEMPLATE"]
            elif isinstance(chunks, list) and len(chunks) > 0:
                first_chunk = chunks[0]
                chunk_id = str(first_chunk.get("chunk_id") or first_chunk.get("id") or "")
                heading = str(first_chunk.get("heading") or "Facility Guidelines")
                chunk_content = str(first_chunk.get("content") or "")
                # Clean content snippet
                lines = [
                    ln.strip()
                    for ln in chunk_content.splitlines()
                    if ln.strip() and not ln.startswith("[")
                ]
                snippet = lines[0] if lines else chunk_content[:100]
                content = f"According to {heading}: {snippet}"
                citations = [chunk_id] if chunk_id else []
                reasons = ["RAG_GROUNDED"]
            else:
                content = (
                    "I do not have enough approved facility information to answer that question."
                )
                citations = []
                reasons = ["NO_APPROVED_CONTEXT"]
            return {"message": content, "citations": citations, "reason_codes": reasons}
        if schema_name == "ReviewOutput":
            return {"approved": True, "issues": [], "reason_codes": ["SCHEMA_VALID"]}
        raise ValueError(f"No fake response is registered for {schema_name}")
