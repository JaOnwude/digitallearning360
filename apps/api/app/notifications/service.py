"""Outbound messages. Email via Resend when configured; console output otherwise.

SMS (Termii) arrives in Phase 2 as another backend behind the same functions.
"""

import asyncio
import json

import resend
import structlog

from app.core.config import get_settings

log = structlog.get_logger(__name__)

# Tests read this to fetch one-time codes without a real inbox.
sent_messages: list[dict[str, str]] = []


def _append_line(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def send_email(*, to: str, subject: str, text: str) -> None:
    settings = get_settings()
    message = {"to": to, "subject": subject, "text": text}
    if settings.resend_api_key is None:
        if settings.is_deployed:
            # Never print message bodies (they may hold login codes) outside local/test.
            log.error("email.not_configured", to=to, subject=subject)
            return
        sent_messages.append(message)
        if settings.email_outbox_file:
            await asyncio.to_thread(_append_line, settings.email_outbox_file, json.dumps(message))
        # Local development: the message (including any code) is printed to the API console.
        log.info("email.console", **message)
        return
    resend.api_key = settings.resend_api_key.get_secret_value()
    params: resend.Emails.SendParams = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "text": text,
    }
    await asyncio.to_thread(resend.Emails.send, params)
    log.info("email.sent", to=to, subject=subject)
