"""Render a critique as Markdown Varun can read next to the draft."""

from dataclasses import dataclass

from newsletter_machine.checks import CheckResult
from newsletter_machine.critic import Critique

SEVERITY_ORDER = {"must": 0, "should": 1}


@dataclass(frozen=True)
class ReportMeta:
    draft_name: str
    words: int
    writer_version: int
    critic_version: int
    checklist_version: int
    series: str = ""  # e.g. "Series 'evals', Part 1 of 4: <title> (free)"; blank for a plain issue


def _blockquote(text: str) -> str:
    """Quote every line, so a multi-line quote cannot spill into the report as headings."""
    return "\n".join(f"> {line}".rstrip() for line in text.splitlines()) + "\n"


def _failure(result: CheckResult) -> str:
    item = result.item
    lines = [
        f"### `{item.id}` ({item.section}, {item.severity}; checked by {result.checked_by})",
        "",
        f"**Rule:** {item.rule}",
        "",
    ]
    lines += [_blockquote(quote) for quote in result.quotes]
    if result.fix:
        lines += [f"**Fix:** {result.fix}", ""]
    return "\n".join(lines)


def _section(title: str, body: list[str], separator: str) -> list[str]:
    return [f"## {title}", "", separator.join(body), ""] if body else []


def render_critique(critique: Critique, meta: ReportMeta) -> str:
    by_status = {
        status: [r for r in critique.results if r.status == status]
        for status in ("pass", "fail", "not-checked")
    }
    failures = sorted(by_status["fail"], key=lambda r: SEVERITY_ORDER[r.item.severity])
    lines = [
        f"# Voice critique: {meta.draft_name}",
        "",
        *([meta.series, ""] if meta.series else []),  # plain: a title may hold * or _
        f"{meta.words} words. {critique.passed} passed, {critique.failed} failed, "
        f"{critique.not_checked} not checked.",
        "",
        f"*writer prompt v{meta.writer_version}, critic prompt v{meta.critic_version}, "
        f"checklist v{meta.checklist_version}*",
        "",
        *_section("Summary", [critique.summary or "(no summary)"], ""),
        *_section("Failed", [_failure(r) for r in failures], "\n"),
        *_section(
            "Not checked",
            [f"- `{r.item.id}`: {r.item.rule}" for r in by_status["not-checked"]],
            "\n",
        ),
        *_section(
            "Passed", [f"- `{r.item.id}` ({r.item.section})" for r in by_status["pass"]], "\n"
        ),
    ]
    return "\n".join(lines).rstrip() + "\n"
