from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from fakes import relevance_fake
from newsletter_machine.prompts import load_prompt
from newsletter_machine.relevance import (
    RELEVANCE_SOURCE_CHARS,
    SourceFit,
    SourceNote,
    build_relevance_classifier,
    classify_sources,
    relevance_system_prompt,
    relevance_task,
    render_parked,
    source_lines,
)
from newsletter_machine.sources import SourceDoc

CONTEXT = "Series topic: evals\nOutline:\n- Part 1: Why evals. Why? (this part)"


def _doc(slug: str, status: str = "ok", text: str = "") -> SourceDoc:
    return SourceDoc(
        url=f"https://example.com/{slug}",
        title=f"Title {slug}",
        kind="article",
        status=status,  # type: ignore[arg-type]
        text=text or ("" if status == "failed" else f"Body about {slug}."),
    )


def _classifier(off: tuple[str, ...] = (), fail: tuple[str, ...] = ()) -> object:
    return build_relevance_classifier(relevance_fake(off, fail), relevance_system_prompt())


def test_prompt_is_versioned_and_renders() -> None:
    assert load_prompt("relevance").version >= 1
    prompt = relevance_system_prompt()
    assert "on_topic" in prompt and "$" not in prompt


def test_task_holds_the_series_context_and_one_cut_source() -> None:
    task = relevance_task(CONTEXT, _doc("a", text="x" * (RELEVANCE_SOURCE_CHARS + 50)), 3)
    assert task.startswith(CONTEXT)
    assert '<source index="3"' in task and "[truncated: 50 more characters]" in task


def test_classify_keeps_on_topic_and_parks_off_topic_in_order() -> None:
    docs = (_doc("evals-a"), _doc("pricing"), _doc("evals-b"), _doc("gone", status="failed"))
    result = classify_sources(_classifier(off=("pricing",)), docs, CONTEXT)  # type: ignore[arg-type]
    assert [d.url for d in result.kept] == [
        "https://example.com/evals-a",
        "https://example.com/evals-b",
        "https://example.com/gone",  # failed sources stay, so the notes list them as skipped
    ]
    assert result.parked == (SourceNote(docs[1], "about pricing"),)
    assert result.unchecked == ()
    assert result.on_topic == 2


def test_classify_keeps_a_source_whose_check_failed() -> None:
    docs = (_doc("evals-a"), _doc("flaky"))
    result = classify_sources(_classifier(fail=("flaky",)), docs, CONTEXT)  # type: ignore[arg-type]
    assert [d.url for d in result.kept] == [d.url for d in docs]
    assert result.parked == ()
    assert [item.doc.url for item in result.unchecked] == ["https://example.com/flaky"]
    assert "classifier down" in result.unchecked[0].reason
    assert not result.all_unchecked


def test_classify_keeps_a_source_when_the_model_returns_no_verdict() -> None:
    classifier = RunnableLambda(lambda task: {"messages": [AIMessage(content="no verdict")]})
    result = classify_sources(classifier, (_doc("a"),), CONTEXT)
    assert len(result.kept) == 1 and "no verdict" in result.unchecked[0].reason
    assert result.all_unchecked


def test_classify_without_usable_sources_makes_no_call() -> None:
    model = relevance_fake()
    classifier = build_relevance_classifier(model, "p")
    result = classify_sources(classifier, (_doc("gone", status="failed"),), CONTEXT)
    assert model.calls == 0 and result.on_topic == 0 and len(result.kept) == 1


def test_source_lines_link_each_source_with_its_reason() -> None:
    parked = (SourceNote(_doc("p"), "  about pricing \n"),)
    assert source_lines(parked) == ("- [Title p](https://example.com/p): about pricing",)


def test_render_parked_names_the_part_and_where_the_text_stays(tmp_path: Path) -> None:
    text = render_parked(
        (SourceNote(_doc("p"), "about pricing"),), "Series 'evals', Part 1", tmp_path
    )
    assert text.startswith("# Parked sources\n\nSeries 'evals', Part 1.")
    assert "--sources" not in text
    assert str(tmp_path) in text
    assert "- [Title p](https://example.com/p): about pricing\n" in text


def test_render_parked_says_none_when_nothing_was_parked(tmp_path: Path) -> None:
    assert "Nothing parked: every usable source is on the series topic." in render_parked(
        (), "Series 'evals', Part 1", tmp_path
    )


@pytest.mark.parametrize("title", ["", "  "])
def test_source_lines_fall_back_to_the_url_without_a_title(title: str) -> None:
    doc = SourceDoc(url="https://e.com/x", title=title, kind="article", status="ok", text="t")
    assert source_lines((SourceNote(doc, "r"),)) == ("- [https://e.com/x](https://e.com/x): r",)


def test_source_lines_escape_link_text() -> None:
    doc = SourceDoc(
        url="https://e.com/x", title="Evals [part 2]", kind="article", status="ok", text="t"
    )
    assert source_lines((SourceNote(doc, "r"),)) == (r"- [Evals \[part 2\]](https://e.com/x): r",)


def test_unchecked_lines_stay_on_one_line() -> None:
    class _Boom(Exception):
        pass

    classifier = RunnableLambda(lambda task: (_ for _ in ()).throw(_Boom("line one\nline two")))
    result = classify_sources(classifier, (_doc("a"),), CONTEXT)
    assert source_lines(result.unchecked) == (
        "- [Title a](https://example.com/a): _Boom: line one line two",
    )


def test_classify_records_the_part_each_on_topic_source_best_supports() -> None:
    docs = (_doc("judges"), _doc("pricing"), _doc("golden"), _doc("flaky"))
    fake = relevance_fake(off=("pricing",), fail=("flaky",), parts={"judges": 3, "golden": 2})
    classifier = build_relevance_classifier(fake, relevance_system_prompt())
    result = classify_sources(classifier, docs, CONTEXT)
    assert result.fits == (SourceFit(docs[0], 3), SourceFit(docs[2], 2))


def test_a_verdict_without_a_part_records_none_not_a_new_topic() -> None:
    context = "Series topic: evals"  # no part marked: the fake leaves best_part out
    result = classify_sources(_classifier(), (_doc("a"),), context)  # type: ignore[arg-type]
    assert result.fits == (SourceFit(result.kept[0], None),)


def test_prompt_explains_best_part() -> None:
    assert load_prompt("relevance").version >= 2
    assert "best_part" in relevance_system_prompt()
