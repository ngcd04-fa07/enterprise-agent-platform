"""Direct ASGI-level tests for BodySizeLimitMiddleware — driving
scope/receive/send by hand rather than through a real HTTP client, so
each of the middleware's two independent checks (declared Content-Length
vs. actual bytes read off the stream) can be exercised precisely and
deterministically, including the "no Content-Length at all" case a real
httpx client won't reliably produce.
"""

from collections.abc import Callable

from app.security.body_size_limit import BodySizeLimitMiddleware


class _SendRecorder:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for message in self.messages:
            if message["type"] == "http.response.start":
                status: int = message["status"]
                return status
        return None

    @property
    def body(self) -> bytes:
        return b"".join(
            message["body"] for message in self.messages if message["type"] == "http.response.body"
        )


def _http_scope(*, content_length: int | None) -> dict:
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    return {"type": "http", "method": "POST", "path": "/", "headers": headers}


def _receive_sequence(chunks: list[bytes]) -> Callable:
    remaining = list(chunks)

    async def receive() -> dict:
        if not remaining:
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = remaining.pop(0)
        return {"type": "http.request", "body": chunk, "more_body": bool(remaining)}

    return receive


async def _echo_app(scope: dict, receive: Callable, send: Callable) -> None:
    del scope
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(len(body)).encode()})


async def test_declared_content_length_over_limit_is_rejected_without_reading_body() -> None:
    read_attempted = False

    async def receive() -> dict:
        nonlocal read_attempted
        read_attempted = True
        return {"type": "http.request", "body": b"x" * 1000, "more_body": False}

    send = _SendRecorder()
    middleware = BodySizeLimitMiddleware(_echo_app, max_bytes=100)

    await middleware(_http_scope(content_length=1000), receive, send)

    assert send.status == 413
    assert read_attempted is False


async def test_streaming_body_without_content_length_is_rejected_once_limit_crossed() -> None:
    # No Content-Length declared at all — the only signal is what's
    # actually read off the stream, chunk by chunk.
    receive = _receive_sequence([b"a" * 60, b"b" * 60])
    send = _SendRecorder()
    middleware = BodySizeLimitMiddleware(_echo_app, max_bytes=100)

    await middleware(_http_scope(content_length=None), receive, send)

    assert send.status == 413


async def test_body_within_limit_reaches_the_app() -> None:
    receive = _receive_sequence([b"a" * 40, b"b" * 40])
    send = _SendRecorder()
    middleware = BodySizeLimitMiddleware(_echo_app, max_bytes=100)

    await middleware(_http_scope(content_length=None), receive, send)

    assert send.status == 200
    assert send.body == b"80"


async def test_non_http_scope_passes_through_untouched() -> None:
    called = False

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        del scope, receive, send
        nonlocal called
        called = True

    async def receive() -> dict:
        return {"type": "lifespan.startup"}

    async def send(message: dict) -> None:
        del message

    middleware = BodySizeLimitMiddleware(app, max_bytes=100)
    await middleware({"type": "lifespan"}, receive, send)

    assert called is True
