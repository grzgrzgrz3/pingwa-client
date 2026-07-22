"""pingwa MCP server over stdio — for Claude Desktop / Claude Code and any
stdio MCP client. Run via `pingwa mcp`. Authenticates with PINGWA_KEY from the
environment.

Tool contract (frozen — tools are added, never renamed/changed):
notify, check_status, upgrade, ask, check_replies.
"""
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from pingwa.client import tools
from pingwa.client.http import PingwaClient

INSTRUCTIONS = (
    "pingwa is a two-way WhatsApp bridge to the account owner's own phone — a human in "
    "the loop for AI agents. There is no recipient field; messages always go to the key "
    "owner. Use `notify` to tell the human something happened (build done, task finished). "
    "Use `ask` to ask a question and BLOCK until the human answers on WhatsApp — they can "
    "reply with free text (steer you: 'use the other API', 'ship it') or tap one of up to "
    "3 buttons; the reply comes back to you. Use `check_replies` to pull any inbound "
    "WhatsApp messages the human sent (poll for out-of-band instructions). Use "
    "`check_status` to see plan and remaining quota, and `upgrade` when quota runs out to "
    "get a Stripe link for the human to open (no password needed). "
    "Set PINGWA_KEY (a pw_... key) in the environment; without it, tools return an "
    "actionable error explaining how to get one."
)


def register_tools(mcp: FastMCP, get_client) -> FastMCP:
    """Attach the frozen pingwa tool set to `mcp`. `get_client()` is called per
    invocation to obtain a PingwaClient — from the env (stdio) or the request's
    Authorization header (remote). Shared by both transports so the tool contract
    is defined exactly once."""

    @mcp.tool()
    def notify(
        text: Annotated[
            str,
            Field(description="The message to send (1-1024 characters). Goes to the "
                  "key owner's own phone; there is no recipient field."),
        ],
        image_url: Annotated[
            str | None,
            Field(description="Optional public https image link (screenshot, chart, "
                  "diff). Delivered as an image with `text` as the caption when the "
                  "24h reply window is open; text-only otherwise."),
        ] = None,
    ) -> str:
        """Send a one-way WhatsApp notification to the account owner's own phone.

        `text` is the message (1-1024 chars). `image_url` (optional) is a public https
        image link — a screenshot, chart or diff — delivered as an image with `text` as
        the caption when the user's 24h window is open (otherwise text only).

        Behavior: queues one WhatsApp message and returns a confirmation with the queued
        message id. Counts against the monthly quota. Does not block or return a reply.
        Raises an actionable error (with a fix hint) on quota exhaustion or bad/missing key.

        When to use: to tell the human something happened when you do NOT need an answer —
        a build finished, a job failed, a long task is done, a deploy shipped. When you
        need the human to answer or decide, use `ask` instead.
        """
        return tools.notify_tool(get_client(), text, image_url)

    @mcp.tool(name="check_status")
    def check_status() -> str:
        """Show the pingwa account's plan, remaining monthly quota, and whether the
        free 24h WhatsApp reply window is currently open.

        Behavior: read-only. Sends no WhatsApp message, changes nothing, and uses no
        quota — safe to call at any time. Returns a short human-readable summary: plan
        tier (Free/Pro), messages left this month, when the quota resets, and whether
        the reply window is open.

        When to use: before a batch of `notify`/`ask` calls to confirm quota remains;
        after any tool raises a quota error, to see how much is left and when it resets;
        or to decide whether to call `upgrade`. Takes no parameters. This is the only
        tool that reports account state — it never sends anything.
        """
        return tools.status_tool(get_client())

    @mcp.tool()
    def upgrade() -> str:
        """Get a link to raise the account's monthly quota by upgrading to Pro.

        Behavior: creates no charge itself and sends no WhatsApp message. Returns a
        Stripe Checkout URL for the human to open and pay — no pingwa password needed,
        the card is handled by Stripe. If the account is already Pro, returns a Stripe
        billing-portal URL to manage or cancel the subscription instead.

        When to use: when `notify`/`ask` fail with a quota-exhausted error, or when
        `check_status` shows the monthly quota is low or spent. Hand the returned URL to
        the human to open — you cannot complete the payment yourself. Takes no parameters.
        """
        return tools.upgrade_tool(get_client())

    @mcp.tool()
    def ask(
        text: Annotated[
            str,
            Field(description="The question to ask the human on WhatsApp."),
        ],
        buttons: Annotated[
            list[str] | None,
            Field(description="Optional list of up to 3 tappable reply buttons. Omit "
                  "to invite a free-text answer the human types on their phone (use "
                  "this to let them steer you mid-task)."),
        ] = None,
        timeout: Annotated[
            int,
            Field(description="Seconds to block waiting for the reply (max 90). On "
                  "timeout the question was still delivered; the answer stays "
                  "retrievable via `check_replies`."),
        ] = 60,
    ) -> str:
        """Ask the human a question on WhatsApp and BLOCK until they reply (or timeout).

        `text` is the question. `buttons` (optional, up to 3) render as tappable reply
        buttons; omit them to invite a free-text answer the human types on their phone.
        `timeout` is seconds to wait (max 90).

        Behavior: sends one WhatsApp message and waits synchronously for the human's
        answer, up to `timeout` seconds. Counts against the monthly quota. Returns the
        human's reply — free text and/or the chosen button. On timeout, returns a note:
        the question was still delivered and the answer stays retrievable later via
        `check_replies`.

        When to use: whenever you need a human decision before continuing — approval to
        proceed, a choice between options (use `buttons`), or free-text steering mid-task
        ('use the other API', 'ship it'). For a one-way heads-up that needs no answer,
        use `notify` instead; to fetch a late answer after a timeout, use `check_replies`.
        """
        return tools.ask_tool(get_client(), text, buttons, timeout)

    @mcp.tool(name="check_replies")
    def check_replies(
        since: Annotated[
            str | None,
            Field(description="Cursor from a previous call; pass it back to get only "
                  "messages newer than that point. Omit on the first call."),
        ] = None,
        wait: Annotated[
            int,
            Field(description="Seconds to long-poll for a message to arrive before "
                  "returning (0 = return immediately with whatever is buffered)."),
        ] = 0,
    ) -> str:
        """Pull inbound WhatsApp messages the human sent to pingwa — out-of-band
        instructions, or a late answer to an `ask` that timed out.

        `since` is a cursor from a previous call (pass it back to get only newer
        messages). `wait` long-polls up to that many seconds for a message to arrive
        (0 = return immediately with whatever is buffered).

        Behavior: read-only. Sends no WhatsApp message and uses no quota. Returns any
        inbound messages plus a new cursor.

        When to use: to poll for messages the human sent on their own initiative
        (steering you between tasks), or to collect the answer to an earlier `ask` that
        returned on timeout. Store the returned cursor and pass it back as `since` so you
        only see new messages. Unlike `ask`, this never sends a question — it only reads.
        """
        return tools.check_replies_tool(get_client(), since, wait)

    return mcp


def build_server(client_factory=PingwaClient.from_env) -> FastMCP:
    """FastMCP instance with the pingwa tools. `client_factory` is called per tool
    invocation to build the REST client (default: read PINGWA_KEY from the env);
    tests inject a factory returning a mocked client."""
    return register_tools(FastMCP("pingwa", instructions=INSTRUCTIONS), client_factory)


def main() -> None:
    build_server().run()  # stdio transport (default)


if __name__ == "__main__":  # pragma: no cover
    main()
