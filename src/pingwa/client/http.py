"""Tiny synchronous pingwa REST client — the shared core of the CLI and both MCP
transports. Imports only httpx + stdlib so `uvx pingwa` stays ultralight and the
client works without any server dependency installed.

Every error is raised as a PingwaError carrying the server's self-describing
`action` string verbatim, so an agent reading the message knows what to do next.
"""
import os
from urllib.parse import urlencode

import httpx

DEFAULT_BASE_URL = "https://pingwa.dev"
ENV_KEY = "PINGWA_KEY"
ENV_BASE = "PINGWA_BASE_URL"


class PingwaError(Exception):
    def __init__(self, message: str, *, code: str | None = None,
                 action: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.action = action
        self.status = status

    def __str__(self) -> str:
        return f"{self.message}  → {self.action}" if self.action else self.message


class MissingKeyError(PingwaError):
    def __init__(self) -> None:
        super().__init__(
            "No pingwa API key. Set the PINGWA_KEY environment variable (a pw_... key).",
            code="missing_key",
            action=("AI agent? Register yourself — POST /v1/registrations with the human's "
                    "phone number (recipe: https://pingwa.dev/llms.txt); the human only taps "
                    "one WhatsApp link and you claim the key directly. Human? Send 'join' on "
                    "WhatsApp to the pingwa service number, then export PINGWA_KEY=pw_..."),
        )


class PingwaClient:
    def __init__(self, key: str, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 30.0):
        self.key = key
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    @classmethod
    def from_env(cls, base_url: str | None = None) -> "PingwaClient":
        key = os.environ.get(ENV_KEY, "").strip()
        if not key:
            raise MissingKeyError()
        base = base_url or os.environ.get(ENV_BASE) or DEFAULT_BASE_URL
        return cls(key, base)

    def _request(self, method: str, path: str, json: dict | None = None,
                 *, timeout: float | None = None) -> dict:
        url = self.base_url + path
        headers = {"Authorization": f"Bearer {self.key}"}
        try:
            r = httpx.request(method, url, json=json, headers=headers,
                              timeout=timeout or self._timeout)
        except httpx.HTTPError as exc:
            raise PingwaError(
                f"Cannot reach pingwa at {self.base_url}: {exc}",
                code="network_error",
                action="Check your network or PINGWA_BASE_URL, then retry.",
            ) from exc
        return _parse(r)

    def notify(self, text: str, image_url: str | None = None) -> dict:
        return self._request("POST", "/v1/notify", _notify_body(text, image_url))

    def me(self) -> dict:
        return self._request("GET", "/v1/me")

    def ask(self, text: str, buttons: list[str] | None = None, timeout: int = 60) -> dict:
        """Send a question and block until the human replies on WhatsApp (free text
        or a button tap) or `timeout` seconds pass. On timeout the server raises a
        408 (code 'ask_timeout') — the question was still delivered and the answer
        stays retrievable via check_replies. The HTTP read timeout is set above the
        server's long-poll so the wait completes client-side."""
        return self._request("POST", "/v1/ask", _ask_body(text, buttons, timeout),
                             timeout=timeout + 15)

    def check_replies(self, since: str | None = None, wait: int = 0) -> dict:
        """Inbound WhatsApp messages after the `since` cursor (long-poll up to `wait`
        seconds). Returns {messages, cursor}; pass the cursor back as `since` next time."""
        return self._request("GET", _inbox_path(since, wait),
                             timeout=(wait + 15) if wait else None)

    def upgrade(self) -> dict:
        """Return a billing link: a Stripe Checkout URL to start Pro, or — if the
        account is already Pro — a billing-portal URL to manage/cancel. The api_key
        alone authorizes this; the human only enters payment on Stripe's page."""
        try:
            res = self._request("POST", "/v1/billing/checkout")
            return {"url": res["url"], "kind": "checkout"}
        except PingwaError as exc:
            if exc.code == "already_pro":
                res = self._request("POST", "/v1/billing/portal")
                return {"url": res["url"], "kind": "portal"}
            raise

    def list_keys(self) -> dict:
        """Active API keys on the account: names + timestamps, never the secrets."""
        return self._request("GET", "/v1/keys")

    def revoke_key(self, key_id: str) -> dict:
        """Revoke one key by id (list_keys gives the ids). Revoking the key used
        for this very request is allowed — the phone re-mints via 'join'."""
        return self._request("DELETE", f"/v1/keys/{key_id}")

    def create_webhook(self, url: str) -> dict:
        """Register an HTTPS endpoint pingwa PUSHes inbound messages to. Returns
        {id, url, secret, active, created_at}; the `secret` (whsec_...) signs every
        delivery and is returned ONCE here — never again. Max 5 active per account."""
        return self._request("POST", "/v1/webhooks", {"url": url})

    def list_webhooks(self) -> dict:
        """The account's webhook subscriptions: {webhooks:[{id,url,active,created_at,
        last_delivery_at,failure_count}]}. The signing secret is never returned here."""
        return self._request("GET", "/v1/webhooks")

    def delete_webhook(self, webhook_id: str) -> dict:
        """Delete one webhook by id (list_webhooks gives the ids)."""
        return self._request("DELETE", f"/v1/webhooks/{webhook_id}")


class AsyncPingwaClient:
    """Async twin of PingwaClient, for callers already on an event loop (the remote
    MCP server, which calls the REST API over loopback — a sync client there would
    block the single event loop and deadlock the self-call)."""

    def __init__(self, key: str, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 30.0):
        self.key = key
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _request(self, method: str, path: str, json: dict | None = None,
                       *, timeout: float | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.key}"}
        try:
            async with httpx.AsyncClient(timeout=timeout or self._timeout) as client:
                r = await client.request(method, self.base_url + path, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise PingwaError(
                f"Cannot reach pingwa at {self.base_url}: {exc}",
                code="network_error",
                action="Check your network or PINGWA_BASE_URL, then retry.",
            ) from exc
        return _parse(r)

    async def notify(self, text: str, image_url: str | None = None) -> dict:
        return await self._request("POST", "/v1/notify", _notify_body(text, image_url))

    async def me(self) -> dict:
        return await self._request("GET", "/v1/me")

    async def ask(self, text: str, buttons: list[str] | None = None, timeout: int = 60) -> dict:
        """Async twin of PingwaClient.ask."""
        return await self._request("POST", "/v1/ask", _ask_body(text, buttons, timeout),
                                   timeout=timeout + 15)

    async def check_replies(self, since: str | None = None, wait: int = 0) -> dict:
        """Async twin of PingwaClient.check_replies."""
        return await self._request("GET", _inbox_path(since, wait),
                                   timeout=(wait + 15) if wait else None)

    async def upgrade(self) -> dict:
        """Async twin of PingwaClient.upgrade."""
        try:
            res = await self._request("POST", "/v1/billing/checkout")
            return {"url": res["url"], "kind": "checkout"}
        except PingwaError as exc:
            if exc.code == "already_pro":
                res = await self._request("POST", "/v1/billing/portal")
                return {"url": res["url"], "kind": "portal"}
            raise

    async def list_keys(self) -> dict:
        """Async twin of PingwaClient.list_keys."""
        return await self._request("GET", "/v1/keys")

    async def revoke_key(self, key_id: str) -> dict:
        """Async twin of PingwaClient.revoke_key."""
        return await self._request("DELETE", f"/v1/keys/{key_id}")

    async def create_webhook(self, url: str) -> dict:
        """Async twin of PingwaClient.create_webhook."""
        return await self._request("POST", "/v1/webhooks", {"url": url})

    async def list_webhooks(self) -> dict:
        """Async twin of PingwaClient.list_webhooks."""
        return await self._request("GET", "/v1/webhooks")

    async def delete_webhook(self, webhook_id: str) -> dict:
        """Async twin of PingwaClient.delete_webhook."""
        return await self._request("DELETE", f"/v1/webhooks/{webhook_id}")


def _notify_body(text: str, image_url: str | None) -> dict:
    body: dict = {"text": text}
    if image_url:
        body["image_url"] = image_url
    return body


def _ask_body(text: str, buttons: list[str] | None, timeout: int) -> dict:
    body: dict = {"text": text, "timeout": timeout}
    if buttons:
        body["buttons"] = buttons
    return body


def _inbox_path(since: str | None, wait: int) -> str:
    params = {}
    if since:
        params["since"] = since
    if wait:
        params["wait"] = wait
    return "/v1/inbox" + (("?" + urlencode(params)) if params else "")


def _parse(r: httpx.Response) -> dict:
    # 2xx only: redirects are not followed, so a 3xx here means a misconfigured
    # base URL — falling through reports it instead of faking an empty success.
    if r.is_success:
        try:
            return r.json()
        except ValueError:
            return {}
    detail: object = r.text
    try:
        body = r.json()
        detail = body.get("detail", body) if isinstance(body, dict) else body
    except ValueError:
        pass
    if isinstance(detail, dict):
        raise PingwaError(
            detail.get("message") or detail.get("error") or f"HTTP {r.status_code}",
            code=detail.get("error"), action=detail.get("action"), status=r.status_code)
    if isinstance(detail, list):  # FastAPI 422 validation errors
        msgs = "; ".join(str(e.get("msg", e)) for e in detail)
        raise PingwaError(f"Invalid request: {msgs}", code="validation_error", status=r.status_code)
    raise PingwaError(str(detail) or f"HTTP {r.status_code}", status=r.status_code)
