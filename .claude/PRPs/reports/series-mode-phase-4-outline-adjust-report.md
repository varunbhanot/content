# Implementation Report: Series mode Phase 4 — Outline adjustment

## Summary
`issue --series` now checks whether this week's on-topic sources fit the next planned part before drafting. The relevance verdict gained a `best_part` field (no extra call); `series_fit.check_fit` applies a deterministic rule (`MIN_FIT_SOURCES = 2`: mismatch when the next part has fewer than 2 supporting sources and another planned part or "no listed part" has more). On mismatch the planner runs once in revise mode (`series_revise.py`, same system prompt with a new "Revising an outline" section, `SeriesRevision` structured output); code keeps written parts, numbers new parts, maps sources, carries over sources of continued parts and writes the change list. The file goes back to `proposed` with a `revisions` entry, the previous file is kept as `<slug>.yaml.bak`, and the command exits 0. `series revise <slug> [--since 7d]` does the same from saved sources; `issue --series --keep-outline` drafts anyway. The planner agent now uses the shared retry middleware.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium-Large | Medium-Large |
| Files Changed | ~16 | 13 src/prompt/doc updates, 3 new src, 4 new test files |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | `revisions` schema | done | optional key, omitted when empty |
| 2 | relevance `best_part` | done | relevance prompt v2; outline marks written parts |
| 3 | fit rule | done | `series_fit.py` |
| 4 | planner retry + helpers | done | no caching (one call, small prompt) |
| 5 | revise mode | done | `series_revise.py`; `split_outline` in `series_part.py` |
| 6 | planner prompt | done | v2 |
| 7 | store | done | `check_revisable`, `save_revision`, `.bak`, `check_can_plan` guard |
| 8 | `series revise` | done | shared runner in new `cli_series_revise.py` (deviation: split out to keep `cli_series.py` small and share with `issue`) |
| 9 | issue fit check | done | `SeriesModels` groups the three series models |
| 10 | README + weekly Namespace | done | |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| ruff check / format | Pass | |
| mypy src | Pass | |
| pytest --cov | Pass | 928 passed, 99% coverage |
| Live | Not run | no API key |

## Deviations from Plan
- Frozen parts are not listed in the change list (only remaining parts, dropped parts and a teaser check line), keeping the record short.
- Shared revision runner lives in `cli_series_revise.py`.
- Relevance fake defaults `best_part` to the part marked "(this part)" so existing runs fit.

## Tests Written
`tests/test_series_fit.py`, `tests/test_series_revise.py`, `tests/test_cli_series_revise.py`, `tests/test_cli_issue_series_fit.py`, plus additions to `test_series.py`, `test_relevance.py`, `test_series_part.py`, `test_series_store.py`, `test_planner.py`.

## Code review (3 rounds, `code-review high`)
Round 1 (10 findings), all fixed except one noted: `best_part` now `None` when omitted (never a "new topic" vote); fit rule needs >= 2 sources elsewhere; backups never overwritten (`.bak`, `.2.bak`, ...); reviser not built with `--keep-outline`; issue-path revision sources deduped and capped at `MAX_PLANNER_SOURCES`; rerun hint shell-quoted; outline line helper shared; moved parts flagged "rewritten". Noted, not fixed: `series revise` reads all saved sources (parked ones included), relying on the planner's "ignore off-topic sources" rule.
Round 2 (10 findings): fixed duplicate-URL votes, `--series-dir` in rerun hint, no revision on partial verdicts (any failed relevance check), unrevisable series (written parts not first / already 6 written) warn and draft as planned instead of failing, Part 1 forced-free not reported as rewritten, `--keep-outline` hint on revision failure. Kept by decision: planner model built up front for series runs (config errors exit 2 before any paid call).
Round 3 (9 findings): fixed thin flag for parts carrying old sources, `from_parts` required in schema, a written part returned again is rejected, `--overwrite` kept in rerun hint, `check_revisable` moved out of `series_store` (no model imports in the store), `run_revision` uses `revise_task`. Kept by decision: exit 0 on revision (Phase 5 must treat "no draft" as a notice); the "Drafting Part N" line printed before the fit check; minor duplicate YAML render/parse in `save_revision`.

Final: ruff, ruff format, mypy clean; 947 passed, 99% coverage.
