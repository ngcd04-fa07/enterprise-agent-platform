from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """API-appropriate response headers only (Stage 20) — this service
    serves JSON, never HTML, so browser-document policies (CSP,
    frame-ancestors/X-Frame-Options) belong on whichever component
    actually renders HTML for a browser to display, which in this
    project's topology is the Next.js frontend (see apps/web/
    next.config.ts), not here. Adding frame/CSP headers to a JSON API
    would protect nothing real while inviting exactly the kind of
    "middleware for a threat that doesn't apply to this response type"
    padding this stage is explicitly trying to avoid.

    - `X-Content-Type-Options: nosniff` — always on; prevents a browser
      from second-guessing this API's declared `Content-Type` (e.g.
      treating a JSON error body as executable content), which is a
      real, cheap protection regardless of response type.
    - `Referrer-Policy: no-referrer` — always on; this API has no reason
      to leak its own URLs (which can contain resource ids) via the
      Referer header on any outbound navigation a client might trigger.
    - `Strict-Transport-Security` — only when `enable_hsts=True` (wired
      from `environment != "development"`, mirroring the existing
      Secure-cookie pattern in app/api/routes/auth.py). HSTS tells a
      browser to *refuse plain HTTP to this host from now on* — emitting
      it in local dev, which only runs over plain HTTP, would be a real
      trap (the browser would then refuse to reach localhost:8000 over
      HTTP at all until the HSTS policy expires or is manually cleared).
      It's also only meaningful once something in the deployment actually
      terminates TLS, which this project doesn't do yet (Stage 21).
    """

    def __init__(self, app: ASGIApp, *, enable_hsts: bool) -> None:
        self._app = app
        self._enable_hsts = enable_hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"referrer-policy", b"no-referrer"))
                if self._enable_hsts:
                    headers.append(
                        (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self._app(scope, receive, add_headers)
