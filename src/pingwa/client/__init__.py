"""pingwa client — the open-source (MIT) half of pingwa.

This package (`pingwa.client`) is the ONLY code shipped in the published `pingwa`
wheel's public surface: the CLI (`pingwa`), the HTTP client, the shared tool layer,
and the stdio MCP server. It depends on nothing but httpx + the MCP SDK and never
imports a server module, so `uvx pingwa` stays tiny and auditable.

Licensing boundary: everything under this package is MIT-licensed (see repo LICENSE).
The pingwa server (api, worker, billing, webhooks, registrations, …) that lives
elsewhere in the repo is proprietary and not published. Keep this package free of
server imports so the boundary — and the trust claim "the client is open source" —
stays true.
"""
