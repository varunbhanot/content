from newsletter_machine.checklist import ChecklistItem
from newsletter_machine.checks import CheckResult
from newsletter_machine.critic import Critique
from newsletter_machine.critique_report import ReportMeta, render_critique


def _item(item_id: str, severity: str = "must") -> ChecklistItem:
    return ChecklistItem(
        id=item_id,
        section="Avoid",
        rule=f"rule {item_id}",
        check="c",
        severity=severity,  # type: ignore[arg-type]
    )


META = ReportMeta(
    draft_name="issue.md", words=870, writer_version=1, critic_version=2, checklist_version=3
)


def _critique() -> Critique:
    return Critique(
        results=(
            CheckResult(item=_item("ok-one"), status="pass", checked_by="critic"),
            CheckResult(item=_item("soft", "should"), status="fail", fix="tweak"),
            CheckResult(
                item=_item("hard"),
                status="fail",
                quotes=("bad line",),
                fix="better line",
                checked_by="critic",
            ),
            CheckResult(item=_item("skipped"), status="not-checked", checked_by="critic"),
        ),
        summary="Mostly Varun.",
    )


def test_render_critique_header_counts_and_versions() -> None:
    text = render_critique(_critique(), META)
    assert text.startswith("# Voice critique: issue.md\n")
    assert "870 words. 1 passed, 2 failed, 1 not checked." in text
    assert "writer prompt v1, critic prompt v2, checklist v3" in text
    assert "## Summary\n\nMostly Varun." in text


def test_render_critique_lists_must_failures_before_should() -> None:
    text = render_critique(_critique(), META)
    assert text.index("`hard`") < text.index("`soft`")
    assert "> bad line" in text
    assert "**Fix:** better line" in text
    assert "(Avoid, should; checked by code)" in text


def test_render_critique_lists_not_checked_and_passed() -> None:
    text = render_critique(_critique(), META)
    assert "## Not checked\n\n- `skipped`: rule skipped" in text
    assert "## Passed\n\n- `ok-one` (Avoid)" in text


def test_render_critique_has_no_em_dashes() -> None:
    assert "—" not in render_critique(_critique(), META)


def test_render_critique_omits_empty_sections() -> None:
    critique = Critique(results=(CheckResult(item=_item("ok"), status="pass"),), summary="Good.")
    text = render_critique(critique, META)
    assert "## Failed" not in text
    assert "## Not checked" not in text


def test_render_critique_quotes_every_line_of_a_multiline_quote() -> None:
    result = CheckResult(item=_item("hard"), status="fail", quotes=("one\n\n## Two",))
    text = render_critique(Critique(results=(result,), summary="s"), META)
    assert "> one\n>\n> ## Two" in text
    assert "\n## Two" not in text
