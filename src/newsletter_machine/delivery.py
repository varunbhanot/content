"""Delivery: put the weekly result in Varun's own Gmail inbox, without sending anything.

The message is inserted (``users.messages.insert``, like IMAP APPEND) with only ``INBOX`` and
``UNREAD``: never the ingest label, or next week's ``ingest`` would read the draft's links.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate
from typing import Protocol

logger = logging.getLogger(__name__)

DELIVERY_LABELS = ("INBOX", "UNREAD")
DELIVERY_HEADER = "X-Newsletter-Machine"


class Mailbox(Protocol):
    def profile_address(self) -> str: ...

    def insert_message(self, raw: bytes, label_ids: Sequence[str]) -> str: ...


@dataclass(frozen=True)
class Delivery:
    subject: str
    body: str
    attachments: tuple[tuple[str, str], ...]  # (file name, Markdown text)


def build_message(delivery: Delivery, address: str) -> EmailMessage:
    """A plain-text message to and from ``address``, Markdown files attached as-is."""
    message = EmailMessage()
    message["From"] = address
    message["To"] = address
    message["Subject"] = delivery.subject
    message["Date"] = formatdate(localtime=True)
    message[DELIVERY_HEADER] = "weekly"
    message.set_content(delivery.body, charset="utf-8")
    for name, text in delivery.attachments:
        message.add_attachment(
            text.encode("utf-8"), maintype="text", subtype="markdown", filename=name
        )
    return message


def deliver(mailbox: Mailbox, delivery: Delivery) -> str:
    """Insert the message into the mailbox; returns the Gmail message id."""
    message = build_message(delivery, mailbox.profile_address())
    message_id = mailbox.insert_message(message.as_bytes(), DELIVERY_LABELS)
    logger.info("Delivered %r to the inbox as message %s", delivery.subject, message_id)
    return message_id
