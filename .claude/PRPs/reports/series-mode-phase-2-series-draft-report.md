# Implementation Report: Series mode Phase 2 — Draft a series part

## Summary
`newsletter-machine issue --series <slug>` drafts the next `planned` part of an approved series. Before any model call it validates the series file and picks the part. After ingest it runs one fast structured-output relevance call per usable source and parks off-topic sources in `<stem>.parked.md`. It injects the topic, the outline and the part brief through the angle seam. After a fully successful run it marks the part `drafted` with the draft path, editing two lines so comments survive.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium | Medium |
| Files Changed | ~16 | 25 (5 new src incl. prompt, 8 src edits, 5 new + 6 edited tests, README, .env.example) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | `series_part.py` | done | |
| 2 | `load_relevance_model` | done | |
| 3 | `relevance.py` + `prompts/relevance.md` | done | Matches verdicts by index, so duplicate URLs stay separate |
| 4 | `series_store.mark_drafted` | done | |
| 5 | report + notes series lines | done | Also lists the sources kept because their check failed ("unchecked") |
| 6 | `cli_issue_series.py` + `cli_issue.py` | done | |
| 7 | prompt edits | done | writer.md, editor.md v1 -> v2 |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| ruff check / format | Pass | |
| mypy src | Pass | 42 files |
| pytest --cov | Pass | 773 passed, 9 live deselected; 99% coverage |

## Deviations from Plan
- `weekly.issue_args` now sets `series=None` and `series_dir`. Without them the scheduled run would have raised `AttributeError`. A new test pins `issue_args` to the parser defaults.
- Added `tests/test_relevance_live.py` (`@pytest.mark.live`).
- The PRD row stays `in-progress` and the plan stays in `plans/`. The caller asked for this; both are archived after merge.

## Tests Written
`test_series_part.py` (10), `test_relevance.py` (11), `test_cli_issue_series.py` (13), `test_relevance_live.py` (1 live), plus additions to `test_series_store.py`, `test_config.py`, `test_critique_report.py`, `test_issue_output.py` and `test_weekly.py`.

## Review fixes (3 rounds, `/code-review high`)
- A rerun on an `--out` already recorded as a part's draft is refused (exit 2). Without this it drafted the next part over that draft.
- `mark_drafted` handles a column-0 comment inside a part, a missing `draft:` key, the `Null`/`NULL`/`~` spellings and a failed parse. Its fallback rewrite goes through `save_series`, which checks the file loads. It refuses a series that is no longer approved.
- Draft paths are recorded relative to the folder that holds `series/`, so they read the same from any working directory.
- If the relevance check fails for every source, the run exits 1 without drafting, so a wrong `NM_RELEVANCE_MODEL` cannot draft from unfiltered sources.
- A failed run's parked list no longer blocks the rerun. Parked and unchecked bullets use the same escaped one-line format. The series text is tag-neutralised. The critique label is plain text.
