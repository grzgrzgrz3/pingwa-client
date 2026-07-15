# pingwa (client)

[![PyPI](https://img.shields.io/pypi/v/pingwa.svg)](https://pypi.org/project/pingwa/)
[![Python](https://img.shields.io/pypi/pyversions/pingwa.svg)](https://pypi.org/project/pingwa/)
[![License: MIT](https://img.shields.io/pypi/l/pingwa.svg)](https://github.com/grzgrzgrz3/pingwa-client/blob/main/LICENSE)

WhatsApp notifications + human-in-the-loop for AI agents and scripts — from your
terminal or an MCP client. `curl → WhatsApp in 60s`, no app, no dashboard.

This is the **open-source (MIT) pingwa client**: a CLI, a tiny HTTP client, and an
MCP server. It talks to a pingwa backend (the hosted service at
https://pingwa.dev, or your own). The backend is separate and private;
this client is not.

## Install & use

No install needed with [uv](https://docs.astral.sh/uv/):

```bash
export PINGWA_KEY=pw_your_key          # get one: send "join" on WhatsApp to the service number
uvx pingwa send "build finished ✅"     # notify your own phone
echo "deploy done" | uvx pingwa send -  # from stdin
uvx pingwa ask "Deploy to prod?" --button yes --button no   # wait for a reply from your phone
uvx pingwa replies                      # pull messages your phone sent back (out-of-band steering)
uvx pingwa me                           # plan / quota / reply-window
uvx pingwa keys                         # list active API keys (up to 10 named keys per number)
uvx pingwa keys revoke ci               # revoke one by name (or reply 'revoke ci' on WhatsApp)
uvx pingwa upgrade                      # get a Stripe link to go Pro (no password needed)
uvx pingwa send "x" --json              # raw JSON response
```

**AI agents:** don't ask your human to copy-paste a key — drive the registration
yourself (`POST /v1/registrations`; full recipe in
[llms.txt](https://pingwa.dev/llms.txt)). The human only taps one WhatsApp link;
the key is claimed by you and never travels through the chat. Works for existing
accounts too — it mints an additional named key.

Exit codes: `0` ok · `2` missing key · `3` quota exceeded · `1` other.
Override the backend with `PINGWA_BASE_URL` or `--base-url`.

## Webhooks

Prefer PUSH over polling `replies`? Register HTTPS endpoints and pingwa POSTs
every inbound WhatsApp message to them:

```bash
uvx pingwa webhooks                                   # list your webhooks
uvx pingwa webhooks add https://your-host/pingwa-hook # returns a signing SECRET, shown ONCE
uvx pingwa webhooks rm https://your-host/pingwa-hook  # by id, or by exact url
```

`add` prints a `whsec_...` secret **once** — store it now; it never appears
again. Each delivery carries an `X-Pingwa-Signature: sha256=<hex>` header (an
HMAC-SHA256 of the raw body under that secret) — verify it and reject anything
that fails. Full verification recipe and payload shape:
[llms.txt](https://pingwa.dev/llms.txt). Up to 5 active webhooks per account; to
rotate a secret, `rm` then `add` again.

## MCP server

Same tools on stdio and remote: `notify(text)`, `ask(text, buttons?, timeout?)`,
`check_replies(since?, wait?)`, `check_status()`, `upgrade()`.

Local (stdio) — for Claude Desktop / Claude Code:

```json
{
  "mcpServers": {
    "pingwa": {
      "command": "uvx",
      "args": ["pingwa", "mcp"],
      "env": { "PINGWA_KEY": "pw_your_key" }
    }
  }
}
```

Remote (Streamable HTTP, no install):

```json
{
  "mcpServers": {
    "pingwa": {
      "url": "https://pingwa.dev/mcp",
      "headers": { "Authorization": "Bearer pw_your_key" }
    }
  }
}
```

Every error carries an `action` hint, so an agent knows what to do next.

## What it sends

Only your message text and your key, to the pingwa backend you point it at — over
HTTPS. Nothing else. The recipient is always your own phone (there is no "to"
field). See the service's [/privacy](https://pingwa.dev/privacy).

## License

MIT — see the `LICENSE` in the repository root. Covers this client package only.
