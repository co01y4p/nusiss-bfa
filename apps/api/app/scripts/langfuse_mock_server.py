from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("langfuse_local")

app = FastAPI(title="Langfuse Local Inspector")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store traces in-memory keyed by traceId
TRACES: dict[str, dict[str, Any]] = {}
HTML_FILE = Path(__file__).parent / "langfuse_ui.html"


@app.post("/api/public/ingestion")
async def ingest(request: Request) -> JSONResponse:
    body = await request.json()
    batch = body.get("batch", [])

    for event in batch:
        event_type = event.get("type")
        event_body = event.get("body", {})

        if event_type == "trace-create":
            trace_id = event_body.get("id")
            if not trace_id:
                continue
            if trace_id not in TRACES:
                TRACES[trace_id] = {
                    "id": trace_id,
                    "name": event_body.get("name", "trace"),
                    "userId": event_body.get("userId"),
                    "sessionId": event_body.get("sessionId"),
                    "input": event_body.get("input"),
                    "output": event_body.get("output"),
                    "metadata": event_body.get("metadata", {}),
                    "tags": event_body.get("tags", []),
                    "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
                    "generations": [],
                    "spans": [],
                }
            else:
                for k, v in event_body.items():
                    if v is not None:
                        TRACES[trace_id][k] = v

            logger.info(
                "🟢 [Langfuse Local] Trace: %s (ID: %s)",
                TRACES[trace_id].get("name"),
                trace_id,
            )

        elif event_type == "observation-create":
            trace_id = event_body.get("traceId")
            obs_type = event_body.get("type", "SPAN")
            if not trace_id:
                continue
            if trace_id not in TRACES:
                TRACES[trace_id] = {
                    "id": trace_id,
                    "name": "unknown",
                    "input": None,
                    "output": None,
                    "metadata": {},
                    "tags": [],
                    "timestamp": event.get("timestamp", datetime.now(UTC).isoformat()),
                    "generations": [],
                    "spans": [],
                }

            if obs_type == "GENERATION":
                TRACES[trace_id]["generations"].append(event_body)
                logger.info(
                    "🤖 [Langfuse Local] Generation: %s | Model: %s | Usage: %s",
                    event_body.get("name"),
                    event_body.get("model"),
                    event_body.get("usage"),
                )
            else:
                TRACES[trace_id]["spans"].append(event_body)
                logger.info("🔧 [Langfuse Local] Span: %s", event_body.get("name"))

    return JSONResponse(content={"status": 200, "successes": len(batch)}, status_code=200)


@app.get("/api/traces")
def get_traces() -> JSONResponse:
    traces_list = sorted(
        TRACES.values(),
        key=lambda t: str(t.get("timestamp", "")),
        reverse=True,
    )
    return JSONResponse(content={"traces": traces_list})


@app.delete("/api/traces")
def clear_traces() -> JSONResponse:
    TRACES.clear()
    return JSONResponse(content={"cleared": True})


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    if HTML_FILE.exists():
        return HTML_FILE.read_text(encoding="utf-8")
    return "<h1>Langfuse Local Inspector</h1><p>UI file missing.</p>"


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3002)
