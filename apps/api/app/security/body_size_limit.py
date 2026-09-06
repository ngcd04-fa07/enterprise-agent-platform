import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    """Enforces `max_bytes` on every request body, at the ASGI boundary —
    below FastAPI's routing and Pydantic validation, so an oversized body
    is rejected before any application code (or Starlette's own body
    buffering for JSON parsing) ever sees it. Closes the gap where only
    the upload route had a bound (Stage 20) — every other JSON route had
    none at all.

    Two independent checks, because a declared Content-Length can be
    absent or simply wrong (chunked transfer-encoding, or a client that
    lies):

    1. If Content-Length is present and already exceeds the limit, reject
       immediately with a 413 — the body is never read at all.
    2. Regardless of what Content-Length claimed, every chunk actually
       read off the ASGI receive stream is counted as it arrives; once
       the running total exceeds the limit, reading stops and a 413 is
       sent. The body is never buffered in full before this check runs —
       only the bytes received so far are ever held, and those are
       discarded (not passed to the app) the moment the limit is
       crossed.

    Applies uniformly to every route, including the upload endpoint —
    `Settings.max_request_body_bytes` is validated at startup to be >=
    `max_upload_size_bytes` (see app/core/config.py) specifically so this
    never rejects a legitimate upload before the upload route's own,
    more precise size check gets a chance to run.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared_length = _content_length(scope)
        if declared_length is not None and declared_length > self._max_bytes:
            await _send_413(send)
            return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_bytes:
                    raise BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracking_send)
        except BodyTooLargeError:
            # Only recoverable if the app hasn't already started its own
            # response — with this app's routes, the body is always fully
            # read (or this limit trips) before any route handler could
            # begin responding, so this guard is a safety net, not the
            # expected path.
            if not response_started:
                await _send_413(send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_413(send: Send) -> None:
    body = json.dumps({"detail": "Request body too large"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})
