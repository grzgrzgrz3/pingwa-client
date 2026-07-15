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


def _fmt_keys(res: dict) -> str:
    keys = res.get("keys") or []
    if not keys:
        return "No active API keys. Send 'join' on WhatsApp to mint one."
    lines = [f"- {k.get('name')}  (created {(k.get('created_at') or '')[:10]}, "
             + (f"last used {(k['last_used_at'] or '')[:10]}" if k.get("last_used_at") else "never used")
             + ")"
             for k in keys]
    return f"{len(keys)} active key(s):\n" + "\n".join(lines)


def _key_id_by_name(res: dict, name: str) -> str:
    for k in res.get("keys") or []:
        if (k.get("name") or "").lower() == name.lower():
            return k["id"]
    names = ", ".join(k.get("name", "?") for k in res.get("keys") or []) or "(none)"
    raise PingwaError(
        f"No active key named '{name}'.",
        code="key_not_found",
        action=f"Active keys: {names}. Run 'pingwa keys' to list them.",
    )


def _fmt_webhooks(res: dict) -> str:
    hooks = res.get("webhooks") or []
    if not hooks:
        return "No webhooks. Add one: pingwa webhooks add https://your-host/hook"
    lines = []
    for w in hooks:
        state = "active" if w.get("active") else "inactive"
        fails = w.get("failure_count") or 0
        last = (w.get("last_delivery_at") or "")[:10] or "never"
        lines.append(
            f"- {w.get('id')}  {w.get('url')}  ({state}, last delivery {last}"
            + (f", {fails} failure(s)" if fails else "")
            + ")"
        )
    return f"{len(hooks)} webhook(s):\n" + "\n".join(lines)


def _fmt_webhook_created(res: dict) -> str:
    return (f"Webhook created ✓ (id={res.get('id')}, url={res.get('url')}).\n"
            f"Signing secret (shown ONCE — store it now, it signs every delivery):\n"
            f"  {res.get('secret')}\n"
            "Verify the X-Pingwa-Signature header with it — recipe: "
            "https://pingwa.dev/llms.txt")


def _webhook_id_by_arg(res: dict, arg: str) -> str:
    """Resolve a `pingwa webhooks rm` argument to a webhook id. An exact id match
    wins; otherwise try to match a listed webhook's exact url. Two subscriptions
    sharing one url is ambiguous → error listing the candidate ids."""
    hooks = res.get("webhooks") or []
    for w in hooks:
        if w.get("id") == arg:
            return arg
    by_url = [w for w in hooks if w.get("url") == arg]
    if len(by_url) == 1:
        return by_url[0]["id"]
    if len(by_url) > 1:
        ids = ", ".join(w.get("id", "?") for w in by_url)
        raise PingwaError(
            f"Multiple webhooks share the url '{arg}'.",
            code="ambiguous_webhook",
            action=f"Delete by id instead — candidates: {ids} (run 'pingwa webhooks').",
        )
    ids = ", ".join(w.get("id", "?") for w in hooks) or "(none)"
    raise PingwaError(
        f"No webhook with id or url '{arg}'.",
        code="webhook_not_found",
        action=f"Known ids: {ids}. Run 'pingwa webhooks' to list them.",
    )


def notify_tool(client, text: str, image_url: str | None = None) -> str:
    return _fmt_notify(client.notify(_validate_text(text), image_url))


def keys_tool(client) -> str:
    return _fmt_keys(client.list_keys())


def revoke_key_tool(client, name: str) -> str:
    key_id = _key_id_by_name(client.list_keys(), name)
    res = client.revoke_key(key_id)
    return f"Key '{res.get('revoked', name)}' revoked."


def webhooks_tool(client) -> str:
    return _fmt_webhooks(client.list_webhooks())


def add_webhook_tool(client, url: str) -> str:
    return _fmt_webhook_created(client.create_webhook(url))


def rm_webhook_tool(client, arg: str) -> str:
    webhook_id = _webhook_id_by_arg(client.list_webhooks(), arg)
    client.delete_webhook(webhook_id)
    return f"Webhook {webhook_id} deleted."


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
