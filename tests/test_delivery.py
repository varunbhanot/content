import email
from collections.abc import Sequence
from email.message import Message

from newsletter_machine.delivery import (
    DELIVERY_HEADER,
    DELIVERY_LABELS,
    Delivery,
    build_message,
    deliver,
)

DELIVERY = Delivery(
    subject="Newsletter draft: Evals are the moat (2026-11-06)",
    body="Your weekly draft is ready.\n\n# Evals are the moat — ünïcode\n",
    attachments=(("2026-11-06.md", "# Evals\n"), ("2026-11-06.notes.md", "notes")),
)


class FakeMailbox:
    def __init__(self) -> None:
        self.inserted: list[tuple[bytes, tuple[str, ...]]] = []

    def profile_address(self) -> str:
        return "varun@example.com"

    def insert_message(self, raw: bytes, label_ids: Sequence[str]) -> str:
        self.inserted.append((raw, tuple(label_ids)))
        return "m-1"


def _parts(message: Message) -> list[Message]:
    return [part for part in message.walk() if not part.is_multipart()]


def test_build_message_addresses_varun_and_marks_the_source() -> None:
    message = build_message(DELIVERY, "varun@example.com")
    assert message["From"] == message["To"] == "varun@example.com"
    assert message["Subject"] == DELIVERY.subject
    assert message[DELIVERY_HEADER] == "weekly"
    assert message["Date"]


def test_build_message_body_and_markdown_attachments() -> None:
    parts = _parts(build_message(DELIVERY, "varun@example.com"))
    assert parts[0].get_content_type() == "text/plain"
    assert "ünïcode" in parts[0].get_payload(decode=True).decode("utf-8")
    attached = {p.get_filename(): p for p in parts[1:]}
    assert set(attached) == {"2026-11-06.md", "2026-11-06.notes.md"}
    assert attached["2026-11-06.md"].get_content_type() == "text/markdown"
    assert attached["2026-11-06.md"].get_payload(decode=True) == b"# Evals\n"


def test_deliver_inserts_into_inbox_unread_and_never_the_ingest_label() -> None:
    mailbox = FakeMailbox()
    assert deliver(mailbox, DELIVERY) == "m-1"
    raw, labels = mailbox.inserted[0]
    assert labels == DELIVERY_LABELS == ("INBOX", "UNREAD")
    assert email.message_from_bytes(raw)["To"] == "varun@example.com"


def test_message_without_attachments_is_plain_text() -> None:
    message = build_message(Delivery("s", "b", ()), "v@example.com")
    assert not message.is_multipart()
