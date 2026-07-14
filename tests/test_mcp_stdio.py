import respx

from pingwa.client.http import PingwaClient
from pingwa.client.mcp_stdio import build_server

BASE = "http://api.test"


def _factory():
    return PingwaClient("pw_k", BASE)


async def test_server_exposes_frozen_tool_set():
    mcp = build_server(client_factory=_factory)
    names = {t.name for t in await mcp.list_tools()}
    assert names == {"notify", "check_status", "upgrade", "ask", "check_replies"}


@respx.mock
async def test_ask_tool_call_returns_reply():
    respx.post(f"{BASE}/v1/ask").respond(200, json={
        "message_id": "q1", "answered": True,
        "reply": {"answer_id": "i1", "text": "ship it", "button_id": None}})
    mcp = build_server(client_factory=_factory)
    _, structured = await mcp.call_tool("ask", {"text": "ready?"})
    assert "ship it" in structured["result"]


@respx.mock
async def test_ask_tool_timeout_is_graceful():
    respx.post(f"{BASE}/v1/ask").respond(408, json={"detail": {
        "error": "ask_timeout", "message_id": "q1", "message": "no reply", "action": "poll later"}})
    mcp = build_server(client_factory=_factory)
    _, structured = await mcp.call_tool("ask", {"text": "ready?", "timeout": 1})
    assert "No reply yet" in structured["result"]


@respx.mock
async def test_check_replies_tool_call():
    respx.get(f"{BASE}/v1/inbox").respond(200, json={
        "messages": [{"body": "turn on the lights", "button_id": None}], "cursor": "c1"})
    mcp = build_server(client_factory=_factory)
    _, structured = await mcp.call_tool("check_replies", {})
    assert "turn on the lights" in structured["result"]


@respx.mock
async def test_upgrade_tool_call_returns_link():
    respx.post(f"{BASE}/v1/billing/checkout").respond(
        200, json={"url": "https://checkout.stripe.com/c/1"})
    mcp = build_server(client_factory=_factory)
    _, structured = await mcp.call_tool("upgrade", {})
    assert "https://checkout.stripe.com/c/1" in structured["result"]


@respx.mock
async def test_notify_tool_call_hits_api():
    respx.post(f"{BASE}/v1/notify").respond(
        202, json={"id": "mA", "billing_class": "template", "status": "queued"})
    mcp = build_server(client_factory=_factory)
    _, structured = await mcp.call_tool("notify", {"text": "hi"})
    assert "mA" in structured["result"]


@respx.mock
async def test_check_status_tool_call():
    respx.get(f"{BASE}/v1/me").respond(200, json={
        "plan": "pro", "active": True, "window_open": False,
        "usage": {"paid_used": 1, "paid_quota": 500}})
    mcp = build_server(client_factory=_factory)
    _, structured = await mcp.call_tool("check_status", {})
    assert "plan=pro" in structured["result"]


async def test_tools_have_descriptions():
    mcp = build_server(client_factory=_factory)
    for t in await mcp.list_tools():
        assert t.description  # agent-readable descriptions present
