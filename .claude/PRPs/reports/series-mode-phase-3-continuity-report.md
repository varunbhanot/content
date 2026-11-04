# Implementation Report: Series mode Phase 3 — Continuity

## Summary
`series published <slug> <n> <url>` records a drafted part's live URL with a comment-preserving edit. After a fully successful `issue --series` run, the part is marked `drafted` with a one-line `summary` (one `NM_SUMMARY_MODEL` call, default the fast model) and its closing `teaser` (regex on the italic "Next in this series" line). From Part 2 on, the series angle carries earlier parts' summaries and the previous part's title, URL, summary and teaser, with opening/closing instructions. Series-only checks in `src/newsletter_machine/series_checks.yaml` load through `checklist.load_checklist` and join the run's checklist, so the writer targets them and the critic judges them through the existing machinery.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium | Medium |
| Files Changed | ~20 | 26 (5 new src incl. prompt + YAML, 7 src edits, 3 prompt edits, 4 new + 6 edited tests, README, .env.example) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | `series_edit.py` | done | `_part_block` moved; generic `edit_part` |
| 2 | store: summary/teaser, publication | done | `plan_publication`/`save_publication` mirror `check_approval`/`save_approval` |
| 3 | `series_summary.py` + `prompts/summary.md` | done | |
| 4 | `series_checks.yaml` + `series_checks.py` | done | |
| 5 | `series_angle` continuity | done | |
| 6 | CLI wiring | done | Deviation: `NM_SUMMARY_MODEL` (default fast model) instead of `NM_FAST_MODEL` directly, mirroring `NM_RELEVANCE_MODEL` |
| 7 | `series published`, `series show` | done | |
| 8 | prompts, README | done | writer v3, editor v3, critic v2 |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| ruff check / format | Pass | |
| mypy src | Pass | 45 files |
| pytest --cov | Pass | 833 passed, 10 live deselected; 99% coverage |
| Wheel contents | Pass | `series_checks.yaml`, `prompts/summary.md` packaged |

## Deviations from Plan
- `NM_SUMMARY_MODEL` added (blank = `NM_FAST_MODEL`), as for the planner and relevance models; it keeps the summary model separately configurable and testable.
- PRD row stays `in-progress` and the plan stays in `plans/` (caller's instruction; archived after merge).

## Tests Written
`test_series_edit.py` (5), `test_series_summary.py` (11), `test_series_checks.py` (7), `test_series_summary_live.py` (1 live), plus additions to `test_series_store.py`, `test_series_part.py`, `test_series.py`, `test_cli_series.py`, `test_cli_issue_series.py`, `test_config.py`.
