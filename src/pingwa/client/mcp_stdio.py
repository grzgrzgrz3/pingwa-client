"""pingwa MCP server over stdio — for Claude Desktop / Claude Code and any
stdio MCP client. Run via `pingwa mcp`. Authenticates with PINGWA_KEY from the
environment.

Tool contract (frozen — tools are added, never renamed/changed):
notify, check_status, upgrade, ask, check_replies.
"""
from mcp.server.fastmcp import FastMCP

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
    def notify(text: str, image_url: str | None = None) -> str:
        """Send a WhatsApp notification to the account owner's own phone.

        `text` is the message (1-1024 chars). `image_url` (optional) is a public https
        image link — a screenshot, chart or diff — delivered as an image with `text` as
        the caption when the user's 24h window is open (otherwise text only). Returns a
        confirmation with the queued message id; raises an actionable error on quota/auth.
        """
        return tools.notify_tool(get_client(), text, image_url)

    @mcp.tool(name="check_status")
    def check_status() -> str:
        """Show the pingwa account's plan, remaining monthly quota, and whether the
        free 24h WhatsApp reply window is currently open."""
        return tools.status_tool(get_client())

    @mcp.tool()
    def upgrade() -> str:
        """Get a link to upgrade the account to Pro (raises the monthly quota).

        Returns a Stripe Checkout URL for the human to open and pay — no pingwa
        password needed, the card is handled by Stripe. If the account is already
        Pro, returns a billing-portal URL to manage or cancel instead.
        """
        return tools.upgrade_tool(get_client())

    @mcp.tool()
    def ask(text: str, buttons: list[str] | None = None, timeout: int = 60) -> str:
        """Ask the human a question on WhatsApp and BLOCK until they reply (or timeout).

        `text` is the question. `buttons` (optional, up to 3) render as tappable reply
        buttons; omit them to invite a free-text answer the human types on their phone —
        use this to let the human steer you mid-task. `timeout` is seconds to wait
        (max 90). Returns the human's reply (free text and/or the chosen option). On
        timeout, returns a note — the question was delivered and the answer is still
        retrievable via `check_replies`.
        """
        return tools.ask_tool(get_client(), text, buttons, timeout)

    @mcp.tool(name="check_replies")
    def check_replies(since: str | None = None, wait: int = 0) -> str:
        """Pull inbound WhatsApp messages the human sent to pingwa (out-of-band
        instructions, or late answers to an `ask`). `since` is a cursor from a previous
        call (pass it back to get only newer messages); `wait` long-polls up to that many
        seconds for something to arrive. Returns the messages and a new cursor.
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
