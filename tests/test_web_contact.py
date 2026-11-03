import smtplib

import pytest
from fastapi.testclient import TestClient

from truth_guardian.web import contact
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT
from truth_guardian.web.examples import ExampleStore

from test_web_api import FakeEngine

ACCOUNT = contact.Settings("team@example.org", "secret")
MESSAGE = {"name": "Sara", "email": "sara@example.org", "subject": "A question", "message": "Hello team."}


@pytest.fixture
def sent(monkeypatch):
    """The app with a configured account and a mailer that records instead of sending."""
    monkeypatch.setattr(contact, "settings", lambda root: ACCOUNT)
    outbox = []
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False, mailer=lambda config, mail: outbox.append((config, mail)))) as client:
        client.outbox = outbox
        yield client


def test_without_an_account_the_page_is_told_and_nothing_is_sent(monkeypatch):
    monkeypatch.setattr(contact, "settings", lambda root: None)
    outbox = []
    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False, mailer=lambda *a: outbox.append(a))) as client:
        assert client.get("/api/contact").json() == {"configured": False}
        assert client.post("/api/contact", json=MESSAGE).status_code == 503
    assert outbox == []


def test_a_message_goes_to_the_fixed_mailbox_with_the_visitor_as_reply_to(sent):
    assert sent.get("/api/contact").json() == {"configured": True}
    response = sent.post("/api/contact", json={**MESSAGE, "subject": "A question\r\nBcc: someone@example.org", "lang": "fa"})
    assert response.json() == {"sent": True}
    config, mail = sent.outbox[0]
    assert config == ACCOUNT
    assert mail["To"] == contact.RECIPIENT
    assert mail["Reply-To"] == "Sara <sara@example.org>"
    assert mail["Subject"] == "[Truth Guardian] A question Bcc: someone@example.org"
    assert mail["Bcc"] is None
    assert "Hello team." in mail.get_content() and "Page language: fa" in mail.get_content()


@pytest.mark.parametrize("change", [{"email": "not an address"}, {"email": "a@b"}, {"email": "سلام@example.org"}, {"email": "a@مثال.org"}, {"name": "   "}, {"message": ""}, {"to": "other@example.org"}])
def test_bad_messages_are_refused(sent, change):
    assert sent.post("/api/contact", json={**MESSAGE, **change}).status_code == 422
    assert sent.outbox == []


def test_one_visitor_may_send_only_a_few_messages_an_hour(sent):
    codes = [sent.post("/api/contact", json=MESSAGE).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


@pytest.mark.parametrize("error", [OSError("no network"), smtplib.SMTPAuthenticationError(535, b"bad")])
def test_mail_server_failures_are_reported(monkeypatch, error):
    monkeypatch.setattr(contact, "settings", lambda root: ACCOUNT)

    def fail(config, mail):
        raise error

    with TestClient(create_app(FakeEngine(), ExampleStore(ROOT), load=False, mailer=fail)) as client:
        response = client.post("/api/contact", json=MESSAGE)
    assert response.status_code == 502
    assert "secret" not in response.text


def test_settings_come_from_the_environment_before_the_local_file(tmp_path, monkeypatch):
    for key in contact.KEYS:
        monkeypatch.delenv(key, raising=False)
    assert contact.settings(tmp_path) is None
    (tmp_path / contact.SETTINGS_FILE).write_text('# comment\nTG_SMTP_USER=file@example.org\nTG_SMTP_PASSWORD="abcd efgh ijkl mnop"\n', encoding="utf-8")
    assert contact.settings(tmp_path) == contact.Settings("file@example.org", "abcdefghijklmnop")
    monkeypatch.setenv("TG_SMTP_USER", "env@example.org")
    monkeypatch.setenv("TG_SMTP_HOST", "mail.example.org")
    monkeypatch.setenv("TG_SMTP_PORT", "465")
    assert contact.settings(tmp_path) == contact.Settings("env@example.org", "abcd efgh ijkl mnop", "mail.example.org", 465)
    monkeypatch.setenv("TG_SMTP_PORT", "not a port")
    assert contact.settings(tmp_path) is None


def test_rate_limit_counts_every_client_and_all_of_them():
    limit = contact.RateLimit(per_client=2, total=3, window=60)
    assert [limit.allow("a"), limit.allow("a"), limit.allow("a")] == [True, True, False]
    assert [limit.allow("b"), limit.allow("c")] == [True, False]
