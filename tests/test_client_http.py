import httpx
import pytest
import respx

from pingwa.client.http import MissingKeyError, PingwaClient, PingwaError

BASE = "http://api.test"


def _client() -> PingwaClient:
    return PingwaClient("pw_testkey", BASE)


@respx.mock
def test_notify_success_returns_dict():
    respx.post(f"{BASE}/v1/notify").respond(
        202, json={"id": "m1", "billing_class": "template", "status": "queued"})
    out = _client().notify("hello")
    assert out["id"] == "m1" and out["status"] == "queued"
    sent = respx.calls.last.request
    assert sent.headers["Authorization"] == "Bearer pw_testkey"


@respx.mock
def test_notify_sends_image_url_when_given():
    route = respx.post(f"{BASE}/v1/notify").respond(
        202, json={"id": "m1", "billing_class": "window_free", "status": "queued"})
    _client().notify("caption", "https://ex.com/s.png")
    import json as _json
    sent = _json.loads(route.calls.last.request.content)
    assert sent == {"text": "caption", "image_url": "https://ex.com/s.png"}


@respx.mock
def test_notify_omits_image_url_when_none():
    route = respx.post(f"{BASE}/v1/notify").respond(202, json={"id": "m1", "status": "queued"})
    _client().notify("hi")
    import json as _json
    assert "image_url" not in _json.loads(route.calls.last.request.content)


@respx.mock
def test_me_success():
    respx.get(f"{BASE}/v1/me").respond(200, json={"plan": "free", "window_open": True})
    assert _client().me()["plan"] == "free"


@respx.mock
def test_ask_sends_buttons_and_timeout_returns_reply():
    route = respx.post(f"{BASE}/v1/ask").respond(200, json={
        "message_id": "q1", "answered": True,
        "reply": {"answer_id": "i1", "text": "Yes", "button_id": "b0"}})
    out = _client().ask("ship?", ["Yes", "No"], timeout=30)
    assert out["reply"]["button_id"] == "b0"
    body = respx.calls.last.request
    import json as _json
    sent = _json.loads(body.content)
    assert sent == {"text": "ship?", "timeout": 30, "buttons": ["Yes", "No"]}
    assert route.called


@respx.mock
def test_ask_timeout_408_raises_pingwa_error():
    respx.post(f"{BASE}/v1/ask").respond(408, json={"detail": {
        "error": "ask_timeout", "message_id": "q1", "message": "no reply", "action": "poll later"}})
    with pytest.raises(PingwaError) as ei:
        _client().ask("ready?", timeout=1)
    assert ei.value.status == 408 and ei.value.code == "ask_timeout"


@respx.mock
def test_check_replies_builds_cursor_query():
    route = respx.get(f"{BASE}/v1/inbox").respond(200, json={"messages": [], "cursor": "c2"})
    out = _client().check_replies(since="2026-07-13T00:00:00Z", wait=5)
    assert out["cursor"] == "c2"
    assert "since=2026-07-13T00%3A00%3A00Z" in str(route.calls.last.request.url)
    assert "wait=5" in str(route.calls.last.request.url)


@respx.mock
def test_402_maps_to_pingwa_error_with_action():
    respx.post(f"{BASE}/v1/notify").respond(402, json={"detail": {
        "error": "quota_exceeded", "message": "quota used",
        "action": "Upgrade: POST /v1/billing/checkout"}})
    with pytest.raises(PingwaError) as ei:
        _client().notify("x")
    err = ei.value
    assert err.code == "quota_exceeded" and err.status == 402
    assert "checkout" in err.action
    assert "→" in str(err)  # action rendered for the agent


@respx.mock
def test_upgrade_returns_checkout_url_for_free_user():
    respx.post(f"{BASE}/v1/billing/checkout").respond(
        200, json={"url": "https://checkout.stripe.com/c/1"})
    assert _client().upgrade() == {"url": "https://checkout.stripe.com/c/1", "kind": "checkout"}


@respx.mock
def test_upgrade_falls_back_to_portal_when_already_pro():
    respx.post(f"{BASE}/v1/billing/checkout").respond(409, json={"detail": {
        "error": "already_pro", "message": "already pro", "action": "use portal"}})
    respx.post(f"{BASE}/v1/billing/portal").respond(
        200, json={"url": "https://billing.stripe.com/p/1"})
    assert _client().upgrade() == {"url": "https://billing.stripe.com/p/1", "kind": "portal"}


@respx.mock
def test_upgrade_propagates_billing_not_configured():
    respx.post(f"{BASE}/v1/billing/checkout").respond(503, json={"detail": {
        "error": "billing_not_configured", "message": "no stripe", "action": "contact operator"}})
    with pytest.raises(PingwaError) as ei:
        _client().upgrade()
    assert ei.value.code == "billing_not_configured"


@respx.mock
def test_422_validation_list_summarised():
    respx.post(f"{BASE}/v1/notify").respond(422, json={"detail": [
        {"loc": ["body", "text"], "msg": "String should have at most 1024 characters"}]})
    with pytest.raises(PingwaError) as ei:
        _client().notify("x" * 2000)
    assert ei.value.code == "validation_error"
    assert "1024" in ei.value.message


@respx.mock
def test_network_error_wrapped():
    respx.post(f"{BASE}/v1/notify").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(PingwaError) as ei:
        _client().notify("x")
    assert ei.value.code == "network_error"


@respx.mock
def test_create_webhook_posts_url_returns_secret():
    route = respx.post(f"{BASE}/v1/webhooks").respond(201, json={
        "id": "wh1", "url": "https://ex.com/hook", "secret": "whsec_abc",
        "active": True, "created_at": "2026-07-15T00:00:00+00:00"})
    out = _client().create_webhook("https://ex.com/hook")
    assert out["secret"] == "whsec_abc" and out["id"] == "wh1"
    import json as _json
    assert _json.loads(route.calls.last.request.content) == {"url": "https://ex.com/hook"}


@respx.mock
def test_create_webhook_409_limit_surfaces_action():
    respx.post(f"{BASE}/v1/webhooks").respond(409, json={"detail": {
        "error": "webhook_limit_reached", "message": "5 active max",
        "action": "DELETE /v1/webhooks/{id} to free a slot, then create again."}})
    with pytest.raises(PingwaError) as ei:
        _client().create_webhook("https://ex.com/hook")
    assert ei.value.code == "webhook_limit_reached" and ei.value.status == 409
    assert "free a slot" in ei.value.action


@respx.mock
def test_list_webhooks_returns_rows():
    respx.get(f"{BASE}/v1/webhooks").respond(200, json={"webhooks": [
        {"id": "wh1", "url": "https://ex.com/h", "active": True,
         "created_at": "2026-07-15T00:00:00+00:00", "last_delivery_at": None,
         "failure_count": 0}]})
    out = _client().list_webhooks()
    assert out["webhooks"][0]["id"] == "wh1"


@respx.mock
def test_delete_webhook_hits_id_path():
    route = respx.delete(f"{BASE}/v1/webhooks/wh1").respond(200, json={"deleted": True})
    assert _client().delete_webhook("wh1")["deleted"] is True
    assert route.called


@respx.mock
def test_delete_webhook_404_raises():
    respx.delete(f"{BASE}/v1/webhooks/nope").respond(404, json={"detail": {
        "error": "webhook_not_found", "message": "no such webhook",
        "action": "GET /v1/webhooks to list your webhooks and their ids."}})
    with pytest.raises(PingwaError) as ei:
        _client().delete_webhook("nope")
    assert ei.value.code == "webhook_not_found" and ei.value.status == 404


def test_from_env_missing_key_raises(monkeypatch):
    monkeypatch.delenv("PINGWA_KEY", raising=False)
    with pytest.raises(MissingKeyError):
        PingwaClient.from_env()


def test_from_env_reads_key_and_base(monkeypatch):
    monkeypatch.setenv("PINGWA_KEY", "pw_abc")
    monkeypatch.setenv("PINGWA_BASE_URL", "http://localhost:8000")
    c = PingwaClient.from_env()
    assert c.key == "pw_abc" and c.base_url == "http://localhost:8000"
