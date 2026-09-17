from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings
from app.monitoring.logging import sanitize_extra_data
from app.security.pii_redaction import redact_payload

logger = logging.getLogger("app.monitoring.langfuse")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class LangfuseTracer:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        enabled: bool | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
        sample_rate: float | None = None,
        debug: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if settings is not None:
            self.enabled = (
                (settings.langfuse_enabled if enabled is None else enabled)
                and bool(settings.langfuse_public_key if public_key is None else public_key)
                and bool(settings.langfuse_secret_key if secret_key is None else secret_key)
            )
            self.public_key = (
                settings.langfuse_public_key if public_key is None else public_key
            ) or ""
            self.secret_key = (
                settings.langfuse_secret_key if secret_key is None else secret_key
            ) or ""
            self.host = (settings.langfuse_host if host is None else host).rstrip("/")
            self.sample_rate = settings.langfuse_sample_rate if sample_rate is None else sample_rate
            self.debug = settings.langfuse_debug if debug is None else debug
            self.redact_pii = settings.redact_pii_in_llm_prompts
        else:
            self.enabled = bool(enabled and public_key and secret_key)
            self.public_key = public_key or ""
            self.secret_key = secret_key or ""
            self.host = (host or "https://cloud.langfuse.com").rstrip("/")
            self.sample_rate = 1.0 if sample_rate is None else sample_rate
            self.debug = bool(debug)
            self.redact_pii = True

        self.transport = transport
        self._auth = (self.public_key, self.secret_key) if self.enabled else None

    def _sanitize(self, data: Any) -> Any:
        if data is None:
            return None
        if isinstance(data, dict):
            cleaned = sanitize_extra_data(data)
            return redact_payload(cleaned) if self.redact_pii else cleaned
        if isinstance(data, str):
            if self.redact_pii:
                redacted = redact_payload({"text": data})
                return redacted.get("text", data)
            return data
        return data

    async def _send_batch(self, batch: list[dict[str, Any]]) -> bool:
        if not self.enabled or not batch:
            return True

        url = f"{self.host}/api/public/ingestion"
        headers = {"Content-Type": "application/json"}
        payload = {"batch": batch}

        try:
            async with httpx.AsyncClient(
                transport=self.transport,
                auth=self._auth,
                timeout=5.0,
            ) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    if self.debug:
                        logger.debug("Successfully ingested %d events to Langfuse", len(batch))
                    return True
                if resp.status_code == 207:
                    try:
                        data = resp.json()
                        if data.get("errors"):
                            logger.warning(
                                "Langfuse partial batch ingestion errors: %s", data.get("errors")
                            )
                        elif self.debug:
                            logger.debug("Successfully ingested %d events to Langfuse", len(batch))
                    except Exception:
                        pass
                    return True
                logger.warning(
                    "Failed to ingest events to Langfuse. Status: %s, Response: %s",
                    resp.status_code,
                    resp.text,
                )
                return False
        except Exception as exc:
            if self.debug:
                logger.warning("Exception sending events to Langfuse: %s", exc)
            else:
                logger.debug("Exception sending events to Langfuse: %s", exc)
            return False

    def start_trace(
        self,
        *,
        name: str = "facility-assistant",
        trace_id: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        input_data: Any = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> LangfuseTraceContext:
        trace_id = trace_id or f"tr-{uuid.uuid4().hex}"
        sanitized_input = self._sanitize(input_data)
        sanitized_metadata = self._sanitize(metadata or {})

        context = LangfuseTraceContext(
            tracer=self,
            trace_id=trace_id,
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=sanitized_metadata,
            tags=tags or [],
        )

        if self.enabled:
            context.enqueue_event(
                event_type="trace-create",
                body={
                    "id": trace_id,
                    "name": name,
                    "userId": user_id,
                    "sessionId": session_id,
                    "input": sanitized_input,
                    "metadata": sanitized_metadata,
                    "tags": tags or [],
                    "timestamp": _now_iso(),
                },
            )

        return context


class LangfuseTraceContext:
    def __init__(
        self,
        *,
        tracer: LangfuseTracer,
        trace_id: str,
        name: str,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self.tracer = tracer
        self.trace_id = trace_id
        self.name = name
        self.user_id = user_id
        self.session_id = session_id
        self.metadata = metadata or {}
        self.tags = tags or []
        self._events: list[dict[str, Any]] = []

    def enqueue_event(self, *, event_type: str, body: dict[str, Any]) -> None:
        if not self.tracer.enabled:
            return
        event = {
            "id": f"evt-{uuid.uuid4().hex}",
            "timestamp": _now_iso(),
            "type": event_type,
            "body": body,
        }
        self._events.append(event)

    def log_generation(
        self,
        *,
        name: str,
        model: str,
        input_data: Any,
        output_data: Any,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        model_parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        status_message: str | None = None,
        level: str = "DEFAULT",
    ) -> str:
        observation_id = f"gen-{uuid.uuid4().hex}"
        if not self.tracer.enabled:
            return observation_id

        st = (
            start_time.isoformat()
            if isinstance(start_time, datetime)
            else (start_time or _now_iso())
        )
        et = end_time.isoformat() if isinstance(end_time, datetime) else (end_time or _now_iso())

        usage: dict[str, int] = {}
        if prompt_tokens is not None:
            usage["promptTokens"] = prompt_tokens
        if completion_tokens is not None:
            usage["completionTokens"] = completion_tokens
        if total_tokens is not None:
            usage["totalTokens"] = total_tokens
        elif prompt_tokens is not None and completion_tokens is not None:
            usage["totalTokens"] = prompt_tokens + completion_tokens

        body = {
            "id": observation_id,
            "traceId": self.trace_id,
            "type": "GENERATION",
            "name": name,
            "startTime": st,
            "endTime": et,
            "model": model,
            "modelParameters": model_parameters or {},
            "input": self.tracer._sanitize(input_data),
            "output": self.tracer._sanitize(output_data),
            "usage": usage or None,
            "metadata": self.tracer._sanitize(metadata or {}),
            "level": level,
            "statusMessage": status_message,
        }
        self.enqueue_event(event_type="observation-create", body=body)
        return observation_id

    def log_span(
        self,
        *,
        name: str,
        input_data: Any = None,
        output_data: Any = None,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        metadata: dict[str, Any] | None = None,
        level: str = "DEFAULT",
        status_message: str | None = None,
    ) -> str:
        observation_id = f"span-{uuid.uuid4().hex}"
        if not self.tracer.enabled:
            return observation_id

        st = (
            start_time.isoformat()
            if isinstance(start_time, datetime)
            else (start_time or _now_iso())
        )
        et = end_time.isoformat() if isinstance(end_time, datetime) else (end_time or _now_iso())

        body = {
            "id": observation_id,
            "traceId": self.trace_id,
            "type": "SPAN",
            "name": name,
            "startTime": st,
            "endTime": et,
            "input": self.tracer._sanitize(input_data),
            "output": self.tracer._sanitize(output_data),
            "metadata": self.tracer._sanitize(metadata or {}),
            "level": level,
            "statusMessage": status_message,
        }
        self.enqueue_event(event_type="observation-create", body=body)
        return observation_id

    def end(
        self,
        *,
        output_data: Any = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        if not self.tracer.enabled:
            return

        body: dict[str, Any] = {
            "id": self.trace_id,
        }
        if output_data is not None:
            body["output"] = self.tracer._sanitize(output_data)
        if metadata:
            body["metadata"] = self.tracer._sanitize(metadata)
        if tags:
            body["tags"] = tags

        self.enqueue_event(event_type="trace-create", body=body)

    async def flush(self) -> bool:
        if not self.tracer.enabled or not self._events:
            return True
        batch_to_send = list(self._events)
        self._events.clear()
        return await self.tracer._send_batch(batch_to_send)
