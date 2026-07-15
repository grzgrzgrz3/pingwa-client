"""`pingwa` command-line interface.

Commands: send, me, mcp. Reads PINGWA_KEY (and optional PINGWA_BASE_URL) from the
environment. CI-friendly: non-zero exit on failure, actionable message on stderr.
"""
import argparse
import json as jsonlib
import sys
from importlib.metadata import PackageNotFoundError, version

from pingwa.client import tools
from pingwa.client.http import MissingKeyError, PingwaClient, PingwaError

EXIT_OK = 0
EXIT_ERR = 1
EXIT_MISSING_KEY = 2
EXIT_QUOTA = 3


def _version() -> str:
    try:
        return version("pingwa")
    except PackageNotFoundError:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pingwa",
        description="WhatsApp notifications for AI agents & scripts. "
                    "Set PINGWA_KEY (a pw_... key from sending 'join' on WhatsApp).")
    p.add_argument("--version", action="version", version=f"pingwa {_version()}")
    p.add_argument("--base-url", default=None,
                   help="API base URL (default: $PINGWA_BASE_URL or the pingwa cloud)")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("send", help="send a WhatsApp notification to your own phone")
    s.add_argument("text", nargs="?", help="message text; omit or pass '-' to read stdin")
    s.add_argument("--image-url", dest="image_url", default=None, metavar="URL",
                   help="public https image URL to attach (shown with the text as caption; "
                        "delivered as an image only inside your open 24h window)")
    s.add_argument("--json", action="store_true", help="print the raw JSON response")

    a = sub.add_parser("ask", help="ask your phone a question and wait for the reply (free text or a button)")
    a.add_argument("text", nargs="?", help="the question; omit or pass '-' to read stdin")
    a.add_argument("--button", action="append", dest="buttons", metavar="TITLE",
                   help="add a tappable reply button (repeatable, up to 3); omit for a free-text answer")
    a.add_argument("--timeout", type=int, default=60, help="seconds to wait for the human (max 90)")
    a.add_argument("--json", action="store_true", help="print the raw JSON response")

    r = sub.add_parser("replies", help="pull inbound WhatsApp messages your phone sent (out-of-band instructions)")
    r.add_argument("--since", default=None, help="cursor from a previous call — only newer messages")
    r.add_argument("--wait", type=int, default=0, help="long-poll up to N seconds for a new message")
    r.add_argument("--json", action="store_true", help="print the raw JSON response")

    m = sub.add_parser("me", help="show plan, quota and reply-window status")
    m.add_argument("--json", action="store_true", help="print the raw JSON response")

    u = sub.add_parser("upgrade", help="get a Stripe link to upgrade to Pro (or manage an existing Pro sub)")
    u.add_argument("--json", action="store_true", help="print the raw JSON response")

    k = sub.add_parser("keys", help="list active API keys, or revoke one by name")
    k.add_argument("action", nargs="?", choices=["list", "revoke"], default="list")
    k.add_argument("name", nargs="?", help="key name (required for revoke)")
    k.add_argument("--json", action="store_true", help="print the raw JSON response")

    w = sub.add_parser("webhooks",
                       help="list webhooks, or add/remove one (pingwa PUSHes inbound messages to them)")
    w.add_argument("action", nargs="?", choices=["list", "add", "rm"], default="list")
    w.add_argument("target", nargs="?",
                   help="https URL (for add) or webhook id/url (for rm)")
    w.add_argument("--json", action="store_true", help="print the raw JSON response")

    sub.add_parser("mcp", help="run the pingwa MCP server over stdio (Claude Desktop/Code)")
    return p


def _client(args) -> PingwaClient:
    return PingwaClient.from_env(base_url=args.base_url)


def _cmd_send(args) -> int:
    text = args.text
    if text is None or text == "-":
        text = sys.stdin.read()
    client = _client(args)
    if args.json:
        print(jsonlib.dumps(client.notify(text.strip(), args.image_url)))
    else:
        print(tools.notify_tool(client, text, args.image_url))
    return EXIT_OK


def _cmd_ask(args) -> int:
    text = args.text
    if text is None or text == "-":
        text = sys.stdin.read()
    client = _client(args)
    if args.json:
        try:
            print(jsonlib.dumps(client.ask(text.strip(), args.buttons, args.timeout)))
        except PingwaError as exc:
            if exc.status == 408:  # timeout is normal flow: question delivered, no answer yet
                print(jsonlib.dumps({"answered": False, "error": exc.code, "message": exc.message}))
                return EXIT_OK
            raise
    else:
        print(tools.ask_tool(client, text, args.buttons, args.timeout))
    return EXIT_OK


def _cmd_replies(args) -> int:
    client = _client(args)
    if args.json:
        print(jsonlib.dumps(client.check_replies(args.since, args.wait)))
    else:
        print(tools.check_replies_tool(client, args.since, args.wait))
    return EXIT_OK


def _cmd_me(args) -> int:
    client = _client(args)
    if args.json:
        print(jsonlib.dumps(client.me()))
    else:
        print(tools.status_tool(client))
    return EXIT_OK


def _cmd_upgrade(args) -> int:
    client = _client(args)
    if args.json:
        print(jsonlib.dumps(client.upgrade()))
    else:
        print(tools.upgrade_tool(client))
    return EXIT_OK


def _cmd_keys(args) -> int:
    client = _client(args)
    if args.action == "revoke":
        if not args.name:
            print("error: 'pingwa keys revoke' needs a key name (run 'pingwa keys' to list)",
                  file=sys.stderr)
            return EXIT_ERR
        print(tools.revoke_key_tool(client, args.name))
        return EXIT_OK
    if args.json:
        print(jsonlib.dumps(client.list_keys()))
    else:
        print(tools.keys_tool(client))
    return EXIT_OK


def _cmd_webhooks(args) -> int:
    client = _client(args)
    if args.action == "add":
        if not args.target:
            print("error: 'pingwa webhooks add' needs an https URL", file=sys.stderr)
            return EXIT_ERR
        if args.json:
            print(jsonlib.dumps(client.create_webhook(args.target)))
        else:
            print(tools.add_webhook_tool(client, args.target))
        return EXIT_OK
    if args.action == "rm":
        if not args.target:
            print("error: 'pingwa webhooks rm' needs a webhook id (run 'pingwa webhooks' to list)",
                  file=sys.stderr)
            return EXIT_ERR
        print(tools.rm_webhook_tool(client, args.target))
        return EXIT_OK
    if args.json:
        print(jsonlib.dumps(client.list_webhooks()))
    else:
        print(tools.webhooks_tool(client))
    return EXIT_OK


def _cmd_mcp(args) -> int:
    from pingwa.client.mcp_stdio import main as mcp_main
    mcp_main()
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    # argparse before 3.12.8 fails to match a trailing optional positional when a
    # flag is interleaved between two nargs="?" positionals (e.g.
    # `webhooks add --json <url>`). --json is a version-independent boolean output
    # toggle, so lift it out of argv before parsing and reapply it after; honour
    # the `--` end-of-options marker so a literal "--json" argument survives.
    cleaned: list[str] = []
    want_json = False
    end_of_opts = False
    for tok in raw:
        if not end_of_opts and tok == "--":
            end_of_opts = True
            cleaned.append(tok)
        elif not end_of_opts and tok == "--json":
            want_json = True
        else:
            cleaned.append(tok)
    parser = _build_parser()
    args = parser.parse_args(cleaned)
    if want_json:
        args.json = True
    if not args.command:
        parser.print_help(sys.stderr)
        return EXIT_ERR
    handlers = {"send": _cmd_send, "ask": _cmd_ask, "replies": _cmd_replies,
                "me": _cmd_me, "upgrade": _cmd_upgrade, "keys": _cmd_keys,
                "webhooks": _cmd_webhooks, "mcp": _cmd_mcp}
    try:
        return handlers[args.command](args)
    except MissingKeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_MISSING_KEY
    except PingwaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_QUOTA if exc.status == 402 else EXIT_ERR


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
