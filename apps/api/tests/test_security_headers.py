"""Direct ASGI-level tests for SecurityHeadersMiddleware — confirms the
always-on headers are present, and that HSTS only appears when
`enable_hsts=True` (wired from `environment != "development"` in
app/main.py) — never unconditionally, since emitting it in local dev
would make a browser refuse plain HTTP to the API afterward.
"""

from collections.abc import Callable

from app.security.headers import SecurityHeadersMiddleware


async def _minimal_app(scope: dict, receive: Callable, send: Callable) -> None:
    del scope, receive
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _header_names(messages: list[dict]) -> set[bytes]:
    for message in messages:
        if message["type"] == "http.response.start":
            headers: list[tuple[bytes, bytes]] = message["headers"]
            return {name for name, _value in headers}
    return set()


async def test_always_on_headers_present_when_hsts_disabled() -> None:
    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    middleware = SecurityHeadersMiddleware(_minimal_app, enable_hsts=False)
    await middleware({"type": "http"}, _no_receive, send)

    names = _header_names(messages)
    assert b"x-content-type-options" in names
    assert b"referrer-policy" in names
    assert b"strict-transport-security" not in names


async def test_hsts_present_only_when_enabled() -> None:
    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    middleware = SecurityHeadersMiddleware(_minimal_app, enable_hsts=True)
    await middleware({"type": "http"}, _no_receive, send)

    names = _header_names(messages)
    assert b"strict-transport-security" in names


async def test_non_http_scope_passes_through_untouched() -> None:
    called = False

    async def app(scope: dict, receive: Callable, send: Callable) -> None:
        del scope, receive, send
        nonlocal called
        called = True

    middleware = SecurityHeadersMiddleware(app, enable_hsts=True)
    await middleware({"type": "lifespan"}, _no_receive, _no_send)

    assert called is True


async def _no_receive() -> dict:
    return {"type": "lifespan.startup"}


async def _no_send(message: dict) -> None:
    del message
