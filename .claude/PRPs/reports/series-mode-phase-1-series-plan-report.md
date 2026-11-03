# Implementation Report: Series mode Phase 1 — Series plan & approve

## Summary
Added `newsletter-machine series plan | approve | show`. `plan` reads the dated source folders earlier `issue` runs saved (`drafts/<YYYY-MM-DD>.sources/`) within `--since` (default `28d`), runs a planner model (`NM_PLANNER_MODEL`, default the writer model) with the new `prompts/planner.md` (the PRD's 7 rules), and writes `series/<slug>.yaml` with status `proposed`. `approve` locks it (one approved series at a time); `show` prints it. Every load validates the file into frozen dataclasses; an invalid file exits 2 naming the file, part and field.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium-Large | Medium |
| Files Changed | ~14 | 16 (5 new src modules + prompt, 3 edited src, 5 new tests, 1 edited test, README, PRD) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Series schema (`series.py`) | Complete | |
| 2 | Store (`series_store.py`) | Complete | Deviated: approval split into `check_approval` + `save_approval` |
| 3 | Planner, prompt, `format_source(max_chars)`, `load_planner_model` | Complete | |
| 4 | CLI (`cli_series.py`, `cli.py`) | Complete | |
| 5 | Docs | Complete | |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | `ruff check`, `ruff format --check`, `mypy src` (strict) clean |
| Unit + CLI Tests | Pass | 682 passed, 8 live deselected |
| Coverage | Pass | 99% total; new modules 100% |
| Build | N/A | `uv run newsletter-machine series --help` loads |
| Edge Cases | Pass | smoke run with a fake model: plan, refuse re-plan, approve, refuse re-plan of approved |

## Deviations from Plan
- `approve_series` was split into `check_approval` (validation, exit 2) and `save_approval` (write, exit 1), because a missing file (`FileNotFoundError`) and a write failure are both `OSError` and need different exit codes.
- `check_can_plan` also rejects a `--series-dir` that is a file, so that case fails before the model call.
- The plan was not archived to `completed/`: the PRD row links it and the phase stays `in-progress` until the PR merges (as in earlier phases).

## Code review (2 rounds, `/code-review high`)
- Round 1 (8 findings, all fixed): comment on the status line broke approve; uppercase-scheme URLs made the file unloadable (save now re-validates); `--overwrite` could not replace a broken proposed file; a stray `.md` in a sources folder aborted planning; temp or non-slug YAML files blocked approval; non-Latin topics became slug `source`; an unused `approve_series` wrapper; a duplicated `.sources` suffix (now `ingest.SOURCES_SUFFIX`).
- Round 2 (10 findings): fixed the one HIGH (an approved file with broken YAML could be overwritten: status is now read leniently and only `proposed` is replaced), blank source titles (URL fallback; outline printed if the write fails), lenient active-series scan, fallback copies no longer replace full text, an 80-source cap, `Sequence` typing, shared `validation.non_empty_text`. Not changed: fail-fast on a malformed saved source (repo convention), CRLF (not reproducible: `read_text` normalises newlines), double folder scan (negligible).

## Issues Encountered
- A prose reply makes LangChain's structured-output agent retry, which an empty fake model cannot serve; the "no structured output" test uses a stub runnable instead, as `test_critic.py` already does.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_series.py` | 40 | schema, validation errors, round trip, outline |
| `tests/test_series_store.py` | 23 | load/save, plan guard, approve, one active series |
| `tests/test_planner.py` | 14 | source window, dedupe, task, prompt rules, output checks |
| `tests/test_cli_series.py` | 26 | exit codes, no model call on usage errors, write races |
| `tests/test_config.py` | +3 | `NM_PLANNER_MODEL` |
| `tests/test_series_live.py` | 1 (live) | real planner on fixtures |

## Next Steps
- [ ] Live run: `uv run newsletter-machine series plan evals --since 28d` with `ANTHROPIC_API_KEY`
- [ ] Phase 2: `issue --series`
