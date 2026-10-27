"""Contact form: messages from the web app's Contact page go to the team's mailbox by SMTP.

This is the one part of the app that uses the internet, and only when someone sends a message. The mail account is the
owner's and never sits in the code: TG_SMTP_USER and TG_SMTP_PASSWORD (for Gmail an app password, made in the Google
account's security settings), optionally TG_SMTP_HOST (default smtp.gmail.com) and TG_SMTP_PORT (587 with STARTTLS;
465 means SSL), as environment variables or as KEY=value lines in smtp.local.env in the project folder, which git and
Docker ignore (smtp.example.env shows the lines). The recipient is fixed here, so the form cannot send mail anywhere
else; the visitor's address goes in Reply-To.
"""

import os
import smtplib
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

RECIPIENT = "majidrafiee1404@gmail.com"
SETTINGS_FILE = "smtp.local.env"
KEYS = ("TG_SMTP_USER", "TG_SMTP_PASSWORD", "TG_SMTP_HOST", "TG_SMTP_PORT")
GMAIL = "smtp.gmail.com"
TIMEOUT = 20


@dataclass(frozen=True)
class Settings:
    user: str
    password: str
    host: str = GMAIL
    port: int = 587


def settings(root: Path) -> Settings | None:
    """The mail account, from the environment first, then smtp.local.env; None when it is not set up."""
    values: dict[str, str] = {}
    file = root / SETTINGS_FILE
    if file.is_file():
        for line in file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() in KEYS:
                values[key.strip()] = value.strip().strip("\"'")
    values.update({key: os.environ[key] for key in KEYS if os.environ.get(key)})
    if not values.get("TG_SMTP_USER") or not values.get("TG_SMTP_PASSWORD"):
        return None
    host = values.get("TG_SMTP_HOST") or GMAIL
    try:
        port = int(values.get("TG_SMTP_PORT") or 587)
    except ValueError:
        return None
    password = values["TG_SMTP_PASSWORD"]
    # Google shows app passwords in groups of four ("abcd efgh ijkl mnop"); the spaces are not part of them.
    return Settings(values["TG_SMTP_USER"], password.replace(" ", "") if host == GMAIL else password, host, port)


def one_line(text: str) -> str:
    """Whitespace, line breaks included, folded to single spaces: a header can never be split into two."""
    return " ".join(text.split())


def compose(sender: str, name: str, email: str, subject: str, message: str, lang: str) -> EmailMessage:
    mail = EmailMessage()
    mail["From"] = formataddr(("Truth Guardian", sender))
    mail["To"] = RECIPIENT
    mail["Reply-To"] = formataddr((one_line(name), email))
    mail["Subject"] = f"[Truth Guardian] {one_line(subject)}"
    mail.set_content(f"From: {one_line(name)} <{email}>\nPage language: {lang}\n\n{message.strip()}\n")
    return mail


def send(config: Settings, mail: EmailMessage) -> None:
    """Hands the message to the mail server; raises OSError or smtplib.SMTPException when it cannot."""
    context = ssl.create_default_context()
    if config.port == 465:
        with smtplib.SMTP_SSL(config.host, config.port, timeout=TIMEOUT, context=context) as server:
            server.login(config.user, config.password)
            server.send_message(mail)
        return
    with smtplib.SMTP(config.host, config.port, timeout=TIMEOUT) as server:
        server.starttls(context=context)
        server.login(config.user, config.password)
        server.send_message(mail)


class RateLimit:
    """At most `per_client` messages from one address and `total` from everyone within `window` seconds."""

    def __init__(self, per_client: int = 5, total: int = 30, window: float = 3600.0):
        self.per_client, self.total, self.window = per_client, total, window
        self.times: deque[tuple[float, str]] = deque()
        self.lock = threading.Lock()

    def allow(self, client: str) -> bool:
        with self.lock:
            now = time.monotonic()
            while self.times and now - self.times[0][0] > self.window:
                self.times.popleft()
            if len(self.times) >= self.total or sum(who == client for _, who in self.times) >= self.per_client:
                return False
            self.times.append((now, client))
            return True
