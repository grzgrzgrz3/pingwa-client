import io
import json

import respx

from pingwa.client.cli import (
    EXIT_ERR,
    EXIT_MISSING_KEY,
    EXIT_QUOTA,
    EXIT_OK,
    main,
)

BASE = "http://api.test"


def _env(monkeypatch, key="pw_k"):
    monkeypatch.setenv("PINGWA_KEY", key)
    monkeypatch.setenv("PINGWA_BASE_URL", BASE)


@respx.mock
def test_send_success_prints_confirmation(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/notify").respond(
        202, json={"id": "m1", "billing_class": "template", "status": "queued"})
    rc = main(["send", "hello world"])
    assert rc == EXIT_OK
    assert "Sent" in capsys.readouterr().out


@respx.mock
def test_send_json_flag_prints_raw(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/notify").respond(202, json={"id": "m2", "status": "queued"})
    rc = main(["send", "--json", "hi"])
    assert rc == EXIT_OK
    assert json.loads(capsys.readouterr().out)["id"] == "m2"


@respx.mock
def test_send_reads_stdin_when_dash(monkeypatch, capsys):
    _env(monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO("from stdin"))
    route = respx.post(f"{BASE}/v1/notify").respond(202, json={"id": "m3", "status": "queued"})
    assert main(["send", "-"]) == EXIT_OK
    assert json.loads(route.calls.last.request.content)["text"] == "from stdin"


@respx.mock
def test_me_success(monkeypatch, capsys):
    _env(monkeypatch)
    respx.get(f"{BASE}/v1/me").respond(200, json={
        "plan": "free", "active": True, "window_open": True,
        "usage": {"paid_used": 0, "paid_quota": 5}})
    assert main(["me"]) == EXIT_OK
    assert "plan=free" in capsys.readouterr().out


def test_missing_key_exit_2(monkeypatch, capsys):
    monkeypatch.delenv("PINGWA_KEY", raising=False)
    rc = main(["send", "x"])
    assert rc == EXIT_MISSING_KEY
    assert "PINGWA_KEY" in capsys.readouterr().err


@respx.mock
def test_quota_exceeded_exit_3(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/notify").respond(402, json={"detail": {
        "error": "quota_exceeded", "message": "used up",
        "action": "Upgrade: POST /v1/billing/checkout"}})
    rc = main(["send", "x"])
    assert rc == EXIT_QUOTA
    assert "checkout" in capsys.readouterr().err


@respx.mock
def test_other_error_exit_1(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/notify").respond(403, json={"detail": {
        "error": "notifications_stopped", "message": "stopped", "action": "send join"}})
    assert main(["send", "x"]) == EXIT_ERR


@respx.mock
def test_upgrade_prints_link(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/billing/checkout").respond(
        200, json={"url": "https://checkout.stripe.com/c/1"})
    assert main(["upgrade"]) == EXIT_OK
    assert "checkout.stripe.com" in capsys.readouterr().out


@respx.mock
def test_ask_success_prints_reply(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/ask").respond(200, json={
        "message_id": "q1", "answered": True,
        "reply": {"answer_id": "i1", "text": "ship it", "button_id": None}})
    assert main(["ask", "ready?"]) == EXIT_OK
    assert "ship it" in capsys.readouterr().out


@respx.mock
def test_ask_sends_buttons(monkeypatch, capsys):
    _env(monkeypatch)
    route = respx.post(f"{BASE}/v1/ask").respond(200, json={
        "message_id": "q1", "answered": True, "reply": {"text": "Yes", "button_id": "b0"}})
    assert main(["ask", "ship?", "--button", "Yes", "--button", "No", "--timeout", "20"]) == EXIT_OK
    sent = json.loads(route.calls.last.request.content)
    assert sent["buttons"] == ["Yes", "No"] and sent["timeout"] == 20


@respx.mock
def test_ask_timeout_json_exit_ok(monkeypatch, capsys):
    _env(monkeypatch)
    respx.post(f"{BASE}/v1/ask").respond(408, json={"detail": {
        "error": "ask_timeout", "message_id": "q1", "message": "no reply", "action": "poll"}})
    assert main(["ask", "--json", "ready?"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["answered"] is False


@respx.mock
def test_replies_prints_messages(monkeypatch, capsys):
    _env(monkeypatch)
    respx.get(f"{BASE}/v1/inbox").respond(200, json={
        "messages": [{"body": "deploy now", "button_id": None}], "cursor": "c1"})
    assert main(["replies"]) == EXIT_OK
    assert "deploy now" in capsys.readouterr().out


def test_no_command_prints_help_exit_1(capsys):
    assert main([]) == EXIT_ERR
    assert "usage" in capsys.readouterr().err.lower()


_KEYS_JSON = {"keys": [
    {"id": "k1", "name": "laptop", "created_at": "2026-07-14T10:00:00+00:00",
     "last_used_at": "2026-07-14T12:00:00+00:00"},
    {"id": "k2", "name": "ci", "created_at": "2026-07-13T10:00:00+00:00",
     "last_used_at": None},
]}


@respx.mock
def test_keys_lists_names(monkeypatch, capsys):
    _env(monkeypatch)
    respx.get(f"{BASE}/v1/keys").respond(200, json=_KEYS_JSON)
    assert main(["keys"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "laptop" in out and "ci" in out


@respx.mock
def test_keys_revoke_by_name(monkeypatch, capsys):
    _env(monkeypatch)
    respx.get(f"{BASE}/v1/keys").respond(200, json=_KEYS_JSON)
    route = respx.delete(f"{BASE}/v1/keys/k2").respond(200, json={"revoked": "ci"})
    assert main(["keys", "revoke", "ci"]) == EXIT_OK
    assert route.called
    assert "ci" in capsys.readouterr().out


@respx.mock
def test_keys_revoke_unknown_name_exit_1(monkeypatch, capsys):
    _env(monkeypatch)
    respx.get(f"{BASE}/v1/keys").respond(200, json=_KEYS_JSON)
    assert main(["keys", "revoke", "nope"]) == EXIT_ERR
    assert "nope" in capsys.readouterr().err
