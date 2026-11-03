"""Opt-in Substack step: create an unpublished draft from the issue's Markdown.

Uses the unofficial ``python-substack`` client (pinned). Only a *draft* is ever created:
``publish=False`` is passed explicitly, and nothing here schedules or sends a post.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from newsletter_machine.config import SubstackSettings

logger = logging.getLogger(__name__)

TITLE_LINE = re.compile(r"\A\s*# (?P<title>.+?)\s*(?:\n|\Z)")
UNTITLED = "Untitled draft"
SUBSTACK_TIMEOUT = 60.0  # seconds per request; the client's default is to wait forever


class SubstackClient(Protocol):
    def create_draft(self, title: str, markdown: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class SubstackResult:
    draft_id: str
    edit_url: str


def split_title(draft: str) -> tuple[str, str]:
    """``(title, body)``: the leading ``# Title`` goes to Substack's title field; the rest
    of the Markdown is passed on unchanged."""
    match = TITLE_LINE.match(draft)
    if match is None:
        return UNTITLED, draft
    return match.group("title"), draft[match.end() :].lstrip("\n")


def create_substack_draft(
    client: SubstackClient, draft: str, publication_url: str
) -> SubstackResult:
    title, body = split_title(draft)
    result = client.create_draft(title, body)
    draft_id = (result.get("draft") or {}).get("id")
    if draft_id in (None, ""):
        raise ValueError("Substack did not return a draft id.")
    logger.info("Created Substack draft %s", draft_id)
    return SubstackResult(str(draft_id), f"{publication_url}/publish/post/{draft_id}")


class _ApiClient:
    """Adapter over ``substack.Api``; signs in when built."""

    def __init__(self, api: Any) -> None:
        self._api = api

    def create_draft(self, title: str, markdown: str) -> Mapping[str, Any]:
        result: Mapping[str, Any] = self._api.create_draft_from_markdown(
            title=title, markdown=markdown, publish=False
        )
        return result


def make_substack_client(settings: SubstackSettings) -> SubstackClient:
    """Sign in with cookies (preferred: no captcha) or email and password."""
    from substack import Api  # lazy: the unofficial client is only needed when opted in

    if settings.cookies:
        api = Api(
            cookies_string=settings.cookies,
            publication_url=settings.publication_url,
            timeout=SUBSTACK_TIMEOUT,
        )
    else:
        api = Api(
            email=settings.email,
            password=settings.password,
            publication_url=settings.publication_url,
            timeout=SUBSTACK_TIMEOUT,
        )
    return _ApiClient(api)
