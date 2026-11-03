import sys
import types
from collections.abc import Mapping
from typing import Any

import pytest

from newsletter_machine.config import SubstackSettings
from newsletter_machine.substack_draft import (
    SUBSTACK_TIMEOUT,
    SubstackResult,
    create_substack_draft,
    make_substack_client,
    split_title,
)

DRAFT = "# Evals are the moat\n\nFirst paragraph.\n\n## Sources\n\n- [A](https://a.example)\n"
PUB = "https://varunbhanot.substack.com"


class FakeSubstack:
    def __init__(self, result: Mapping[str, Any]) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def create_draft(self, title: str, markdown: str) -> Mapping[str, Any]:
        self.calls.append((title, markdown))
        return self.result


def test_split_title_moves_the_h1_into_the_title_and_keeps_the_body_as_is() -> None:
    title, body = split_title(DRAFT)
    assert title == "Evals are the moat"
    assert body == "First paragraph.\n\n## Sources\n\n- [A](https://a.example)\n"


def test_split_title_without_h1_uses_a_placeholder_and_keeps_everything() -> None:
    assert split_title("Just text.\n") == ("Untitled draft", "Just text.\n")


def test_create_substack_draft_returns_id_and_editor_link() -> None:
    client = FakeSubstack({"draft": {"id": 123}, "publish": None})
    result = create_substack_draft(client, DRAFT, PUB)
    assert result == SubstackResult(draft_id="123", edit_url=f"{PUB}/publish/post/123")
    assert client.calls == [split_title(DRAFT)]


def test_create_substack_draft_rejects_an_answer_without_an_id() -> None:
    with pytest.raises(ValueError, match="draft id"):
        create_substack_draft(FakeSubstack({"draft": {}}), DRAFT, PUB)


class _FakeApi:
    made: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        _FakeApi.made.append(kwargs)
        self.drafts: list[dict[str, Any]] = []

    def create_draft_from_markdown(self, **kwargs: Any) -> dict[str, Any]:
        self.drafts.append(kwargs)
        return {"draft": {"id": 7}}


@pytest.fixture
def fake_substack_module(monkeypatch: pytest.MonkeyPatch) -> type[_FakeApi]:
    module = types.ModuleType("substack")
    module.Api = _FakeApi  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "substack", module)
    _FakeApi.made = []
    return _FakeApi


def test_client_uses_cookies_and_never_publishes(fake_substack_module: type[_FakeApi]) -> None:
    client = make_substack_client(SubstackSettings(PUB, cookies="sid=1"))
    assert fake_substack_module.made == [
        {"cookies_string": "sid=1", "publication_url": PUB, "timeout": SUBSTACK_TIMEOUT}
    ]
    assert create_substack_draft(client, DRAFT, PUB).draft_id == "7"
    api = client._api  # type: ignore[attr-defined]
    assert api.drafts[0]["publish"] is False
    assert api.drafts[0]["title"] == "Evals are the moat"


def test_client_falls_back_to_email_and_password(fake_substack_module: type[_FakeApi]) -> None:
    make_substack_client(SubstackSettings(PUB, email="v@e.com", password="pw"))
    assert fake_substack_module.made == [
        {"email": "v@e.com", "password": "pw", "publication_url": PUB, "timeout": SUBSTACK_TIMEOUT}
    ]
