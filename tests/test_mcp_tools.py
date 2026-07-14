import pytest
import respx

from pingwa.client.http import PingwaClient, PingwaError
from pingwa.client.tools import (
    ask_tool,
    check_replies_tool,
    notify_tool,
    status_tool,
    upgrade_tool,
)

BASE = "http://api.test"


def _client():
    return PingwaClient("pw_k", BASE)


@respx.mock
def test_notify_tool_returns_confirmation():
    respx.post(f"{BASE}/v1/notify").respond(
        202, json={"id": "m9", "billing_class": "window_free", "status": "queued"})
    out = notify_tool(_client(), "deploy done")
    assert "Sent" in out and "m9" in out and "window_free" in out


def test_notify_tool_empty_text_raises_actionable():
    with pytest.raises(PingwaError) as ei:
        notify_tool(_client(), "   ")
    assert ei.value.code == "empty_text" and ei.value.action


@respx.mock
def test_status_tool_summarises_me():
    respx.get(f"{BASE}/v1/me").respond(200, json={
        "plan": "pro", "active": True, "window_open": False,
        "usage": {"paid_used": 3, "paid_quota": 500}})
    out = status_tool(_client())
    assert "plan=pro" in out and "quota_used=3/500" in out and "window_open=False" in out


@respx.mock
def test_upgrade_tool_returns_checkout_link():
    respx.post(f"{BASE}/v1/billing/checkout").respond(
        200, json={"url": "https://checkout.stripe.com/c/1"})
    out = upgrade_tool(_client())
    assert "https://checkout.stripe.com/c/1" in out


@respx.mock
def test_ask_tool_formats_reply():
    respx.post(f"{BASE}/v1/ask").respond(200, json={
        "message_id": "q1", "answered": True,
        "reply": {"answer_id": "i1", "text": "go ahead", "button_id": "b0"}})
    out = ask_tool(_client(), "ready?", ["go ahead", "wait"])
    assert "go ahead" in out and "b0" in out


@respx.mock
def test_ask_tool_timeout_returns_note_not_raise():
    respx.post(f"{BASE}/v1/ask").respond(408, json={"detail": {
        "error": "ask_timeout", "message_id": "q1", "message": "no reply within 1s",
        "action": "poll GET /v1/messages/q1/reply"}})
    out = ask_tool(_client(), "ready?", timeout=1)
    assert "No reply yet" in out and "poll" in out.lower()


def test_ask_tool_empty_text_raises():
    with pytest.raises(PingwaError) as ei:
        ask_tool(_client(), "   ")
    assert ei.value.code == "empty_text"


@respx.mock
def test_check_replies_tool_lists_messages():
    respx.get(f"{BASE}/v1/inbox").respond(200, json={
        "messages": [{"body": "restart the worker", "button_id": None}], "cursor": "c1"})
    out = check_replies_tool(_client())
    assert "restart the worker" in out and "c1" in out


@respx.mock
def test_check_replies_tool_empty():
    respx.get(f"{BASE}/v1/inbox").respond(200, json={"messages": [], "cursor": None})
    assert "No new replies" in check_replies_tool(_client())


@respx.mock
def test_upgrade_tool_returns_portal_link_when_already_pro():
    respx.post(f"{BASE}/v1/billing/checkout").respond(409, json={"detail": {
        "error": "already_pro", "message": "already pro", "action": "portal"}})
    respx.post(f"{BASE}/v1/billing/portal").respond(
        200, json={"url": "https://billing.stripe.com/p/1"})
    out = upgrade_tool(_client())
    assert "https://billing.stripe.com/p/1" in out and "manage" in out.lower()
