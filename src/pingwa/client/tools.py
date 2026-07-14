"""Tool logic shared by the CLI and both MCP transports (stdio + remote).

Each function returns an agent/human-readable string; errors propagate as
PingwaError (message + actionable hint). Sync and async variants share the same
validation and formatting, so behaviour is identical across surfaces.
"""
from pingwa.client.http import PingwaError


def _validate_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise PingwaError(
            "Notification text is empty.",
            code="empty_text",
            action="Pass a non-empty message, e.g. notify(text='build finished').",
        )
    return text


def _fmt_notify(res: dict) -> str:
    return (f"Sent ✓ — WhatsApp notification queued "
            f"(id={res.get('id')}, billing={res.get('billing_class')}, "
            f"status={res.get('status')}).")


def _fmt_status(me: dict) -> str:
    usage = me.get("usage") or {}
    return (f"plan={me.get('plan')} active={me.get('active')} "
            f"window_open={me.get('window_open')} "
            f"quota_used={usage.get('paid_used')}/{usage.get('paid_quota')}")


def _fmt_upgrade(res: dict) -> str:
    url = res.get("url")
    if res.get("kind") == "portal":
        return f"Already on Pro. Manage or cancel your subscription here: {url}"
    return ("Upgrade to Pro — open this link to pay "
            f"(card handled by Stripe, never by pingwa): {url}")


def _fmt_reply(res: dict) -> str:
    reply = res.get("reply") or {}
    text = (reply.get("text") or "").strip()
    button = reply.get("button_id")
    line = f"Human replied: {text or '(empty)'}"
    if button:
        line += f"  [chosen option: {button}]"
    return line


def _fmt_timeout(err: PingwaError) -> str:
    """A 408 from /v1/ask is normal flow, not a failure: the question was delivered,
    the human just hasn't answered yet. Return the actionable note instead of raising
    so an agent tool call resolves cleanly."""
    return f"No reply yet — {err.message} {err.action or ''}".strip()


def _fmt_replies(res: dict) -> str:
    msgs = res.get("messages") or []
    cursor = res.get("cursor")
    if not msgs:
        return f"No new replies. (cursor={cursor})"
    lines = [f"- {m.get('body', '').strip()}"
             + (f"  [option: {m['button_id']}]" if m.get("button_id") else "")
             for m in msgs]
    return f"{len(msgs)} reply(ies):\n" + "\n".join(lines) + f"\n(cursor={cursor})"


def notify_tool(client, text: str, image_url: str | None = None) -> str:
    return _fmt_notify(client.notify(_validate_text(text), image_url))


def status_tool(client) -> str:
    return _fmt_status(client.me())


def upgrade_tool(client) -> str:
    return _fmt_upgrade(client.upgrade())


def ask_tool(client, text: str, buttons: list[str] | None = None, timeout: int = 60) -> str:
    try:
        return _fmt_reply(client.ask(_validate_text(text), buttons, timeout))
    except PingwaError as exc:
        if exc.status == 408:
            return _fmt_timeout(exc)
        raise


def check_replies_tool(client, since: str | None = None, wait: int = 0) -> str:
    return _fmt_replies(client.check_replies(since, wait))


async def notify_tool_async(client, text: str, image_url: str | None = None) -> str:
    return _fmt_notify(await client.notify(_validate_text(text), image_url))


async def status_tool_async(client) -> str:
    return _fmt_status(await client.me())


async def upgrade_tool_async(client) -> str:
    return _fmt_upgrade(await client.upgrade())


async def ask_tool_async(client, text: str, buttons: list[str] | None = None, timeout: int = 60) -> str:
    try:
        return _fmt_reply(await client.ask(_validate_text(text), buttons, timeout))
    except PingwaError as exc:
        if exc.status == 408:
            return _fmt_timeout(exc)
        raise


async def check_replies_tool_async(client, since: str | None = None, wait: int = 0) -> str:
    return _fmt_replies(await client.check_replies(since, wait))
