import re
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.monitoring.logging import request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
# Accept a caller-supplied id only if it is short and plain, so it cannot inject log content.
VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdMiddleware:
    """Gives every HTTP request an id, exposes it in logs and in the response header.

    Written as a pure ASGI middleware (not BaseHTTPMiddleware) so the id is also visible to
    the code that writes uvicorn's access-log line, which runs outside Starlette's
    per-request task. The context variable is deliberately not reset afterwards: uvicorn
    handles each request in its own task, and keeping it lets the traceback of an unhandled
    exception (logged after this middleware has unwound) carry the id as well.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = ""
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                supplied = value.decode("latin-1")
                break
        request_id = supplied if VALID_REQUEST_ID.match(supplied) else uuid.uuid4().hex
        request_id_var.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)
