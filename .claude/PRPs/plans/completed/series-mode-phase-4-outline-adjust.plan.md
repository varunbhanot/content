# Plan: Series mode Phase 4 — Outline adjustment

## Summary
When this week's on-topic links do not support the next planned part, `issue --series` stops before drafting and proposes a revised remaining outline instead. The relevance call that already runs per source also names the outline part each source best supports (one new structured field, no extra call). A deterministic rule (`MIN_FIT_SOURCES = 2`) decides a mismatch. On mismatch the planner runs once in a "revise" mode over the frozen parts (drafted/published, never changed), the remaining planned parts and this week's on-topic sources; code numbers the parts, carries frozen parts through unchanged, computes the change list, writes the file back as `proposed` with a `revisions` history entry, keeps a `.bak` of the previous file, prints the diff and exits 0. Varun re-approves with `series approve`. `series revise <slug> [--since 7d]` triggers the same revision from saved sources. `issue --series --keep-outline` drafts the planned part anyway.

## User Story
As Varun, I want the series outline to follow what I actually read, so that a week whose links fit a different or new part gives me a revised outline to approve instead of a forced draft.

## Problem → Solution
`issue --series` always drafts the lowest planned part, however badly this week's links fit it → the fit is checked first; a poor fit produces a revised outline proposal (frozen parts untouched) and a recorded revision, and the run asks for re-approval.

## Metadata
- **Complexity**: Medium-Large
- **Source PRD**: `.claude/PRPs/prds/series-mode.prd.md`
- **PRD Phase**: Phase 4 — Outline adjustment
- **Estimated Files**: ~16 (2 new src, ~8 src edits, 2 prompt edits, tests, README)

---

## UX Design

### Before
```
$ newsletter-machine issue --series evals --since 7d --out drafts/2026-11-11.md
Drafting Series 'evals', Part 2 of 4: Golden sets (paid)
Relevance: 3 on-topic, 1 parked
(drafts Part 2 from links that are all about LLM judges)
```

### After
```
$ newsletter-machine issue --series evals --since 7d --out drafts/2026-11-11.md
Drafting Series 'evals', Part 2 of 4: Golden sets (paid)
Relevance: 3 on-topic, 1 parked
Fit: Part 2 has 0 of 3 on-topic sources; Part 3: 2, new topic: 1
This week's sources do not fit Part 2, so it was not drafted. Revising the outline ...
Revised series/evals.yaml (proposed, 4 parts). Rewritten in full; the previous file, with your comments, is at series/evals.yaml.bak
Reason: This week's reading is about LLM judges, which golden sets do not need first.
Changes:
  - Part 1 unchanged (drafted)
  - Part 2 is old Part 3 (moved up): LLM-as-judge
  - Part 3 is old Part 2 (moved down): Golden sets
  - Part 4 unchanged: Evals in CI
<outline>
Next: review series/evals.yaml, run: newsletter-machine series approve evals
then rerun: newsletter-machine issue --series evals ... (or pass --keep-outline to draft Part 2 anyway)
(exit 0)

$ newsletter-machine series revise evals --since 7d
Revising from 5 sources in 1 folder (2026-11-11.sources)
Revised series/evals.yaml ...  (same output)
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `issue --series` | always drafts next planned part | fit check after relevance; mismatch -> revise, no draft, exit 0 | parked list still written |
| `issue --series --keep-outline` | n/a | skip the fit check | usage error without `--series` |
| `series revise <slug> [--since 7d] [--drafts-dir]` | n/a | revise from saved sources | exit 2 usage, 1 model/write |
| series file | no history | optional top-level `revisions: [{date, reason, changes}]` | old files load unchanged |
| `series show` | outline | + one line per revision | |
| `series plan --overwrite` | replaced any proposed outline | refuses when the file has drafted/published parts or revisions | protects revised series |
| relevance verdict | `on_topic`, `reason` | + `best_part` (0 = fits no listed part) | prompt v2 |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/planner.py` | all | structured output, `_to_part`, `_coverage`, part-count rule |
| P0 | `src/newsletter_machine/relevance.py` | all | verdict schema, `classify_sources`, `Relevance` |
| P0 | `src/newsletter_machine/cli_issue.py` | 186-210, 375-400 | `_prepare`, `_draft_series` |
| P0 | `src/newsletter_machine/cli_issue_series.py` | all | `SeriesTarget`, `SeriesJob`, `filter_sources` |
| P0 | `src/newsletter_machine/series.py` | all | parse/serialise; add `revisions` |
| P0 | `src/newsletter_machine/series_store.py` | all | `save_series`, `check_can_plan`, `_read`, `_parse_text` |
| P1 | `src/newsletter_machine/cli_series.py` | all | subcommand pattern, `_run_plan` failure handling |
| P1 | `src/newsletter_machine/series_part.py` | 60-70, 160-170 | `_outline_lines`, `relevance_context` |
| P1 | `src/newsletter_machine/weekly.py` | 84-96 | `issue_args` Namespace must gain `keep_outline=False` |
| P2 | `tests/test_cli_issue_series.py` | 1-120 | `_use_models`, `_series_file`, `_series_issue` |
| P2 | `tests/test_planner.py` | 1-70 | `plan_reply`, `_planner` |
| P2 | `tests/fakes.py` | `RelevanceFake` | content-aware classifier fake to extend with `best_part` |

## External Documentation
No external research needed — feature uses established internal patterns (`create_agent(response_format=...)`, `model_retry()`).

---

## Patterns to Mirror

### STRUCTURED OUTPUT AGENT
```python
# SOURCE: src/newsletter_machine/relevance.py:64-79
return create_agent(model, tools=[], system_prompt=system_prompt,
                    response_format=RelevanceVerdict, middleware=[model_retry()], name=RELEVANCE_NAME)
```

### CODE OWNS FACTS
```python
# SOURCE: src/newsletter_machine/planner.py:153-170 (_coverage / _to_part)
valid = dict.fromkeys(i for i in indexes if 1 <= i <= len(docs))
access = "free" if number == 1 else planned.access
thin=planned.thin or len(sources) < MIN_PART_SOURCES
```

### CLI EXIT CODES / KEEP PAID OUTPUT ON SCREEN
```python
# SOURCE: src/newsletter_machine/cli_series.py:120-140
except USAGE_ERRORS as exc:
    print(format_outline(series, job.slug))  # keep the paid-for outline on screen
    print(f"Could not write the series: {exc} (outline not written)", file=sys.stderr)
    return EXIT_ERROR
```

### VALIDATION ERRORS NAME FILE AND FIELD
```python
# SOURCE: src/newsletter_machine/series.py:138-150
raise ValueError(f"{where}: 'thin' must be true or false (got {value!r})")
```

### TEST STRUCTURE
`tests/test_cli_issue_series.py::_use_models` patches `cli_issue.make_chat_model` with a factory keyed by `fake:<role>`; add `"fake:planner"` (env `NM_PLANNER_MODEL=fake:planner`).

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/series.py` | UPDATE | `Revision` dataclass, optional `revisions`, round-trip, `format_outline` lines |
| `src/newsletter_machine/relevance.py` | UPDATE | `best_part` field; `SourceFit`; `Relevance.fits` |
| `src/newsletter_machine/prompts/relevance.md` | UPDATE | describe `best_part`; v2 |
| `src/newsletter_machine/series_part.py` | UPDATE | relevance outline marks frozen parts (so `best_part` aims at planned ones) |
| `src/newsletter_machine/series_fit.py` | CREATE | `MIN_FIT_SOURCES`, `FitCheck`, `check_fit`, `fit_line` |
| `src/newsletter_machine/planner.py` | UPDATE | retry middleware; public `source_ref`/`coverage`/`to_part` helpers |
| `src/newsletter_machine/series_revise.py` | CREATE | revise schema, task, `run_revision`, change list |
| `src/newsletter_machine/prompts/planner.md` | UPDATE | "Revising an outline" section; v2 |
| `src/newsletter_machine/series_store.py` | UPDATE | `save_revision` (re-check, `.bak`, rewrite), `check_revisable`, guard in `check_can_plan` |
| `src/newsletter_machine/cli_series.py` | UPDATE | `series revise`, shared revision printing |
| `src/newsletter_machine/cli_issue_series.py` | UPDATE | `--keep-outline`, reviser in `SeriesJob`, `adjust_outline` |
| `src/newsletter_machine/cli_issue.py` | UPDATE | build reviser in `_prepare`; fit check in `_draft_series` |
| `src/newsletter_machine/weekly.py` | UPDATE | `keep_outline=False` in `issue_args` |
| `tests/...` | UPDATE/CREATE | `test_series_fit.py`, `test_series_revise.py`, extend series/store/relevance/cli tests |
| `README.md` | UPDATE | mismatch behaviour, `series revise`, `--keep-outline`, revisions |

## NOT Building
- Weekly-run integration (Phase 5): only `keep_outline=False` added to the Namespace so `weekly` keeps working.
- RSS URL discovery; series-worthiness check; multi-series.
- Proposing to end a series when it would grow past 6 parts (PRD open question): a revision over `MAX_PARTS` is rejected like a plan.
- A comment-preserving revision: the revised outline is a full rewrite with a `.bak` copy (see Notes).

---

## Step-by-Step Tasks

### Task 1: `revisions` in the series schema
- **ACTION**: `series.py`: `@dataclass(frozen=True) class Revision: date: str; reason: str; changes: tuple[str, ...]`; `Series.revisions: tuple[Revision, ...] = ()`. `SERIES_FIELDS` gains `"revisions"` (optional). `_revisions(data, path)`: absent/None -> `()`; must be a list of mappings with exactly `date`, `reason`, `changes`; `date` an ISO date (str, or `datetime.date` as YAML loads an unquoted one -> `isoformat()`); `reason` non-empty text; `changes` a list of non-empty strings. Errors name `revision #i`. `series_to_mapping` emits `revisions` only when non-empty (old files round-trip identically). `format_outline` appends `Revised <date>: <reason>` per revision.
- **GOTCHA**: `yaml.safe_dump` quotes `'2026-11-04'`; loading an unquoted date yields `datetime.date` (not `datetime`; reject datetimes).
- **VALIDATE**: round-trip tests; old files without the key load; bad entries raise with path.

### Task 2: relevance reports the best-supported part
- **ACTION**: `RelevanceVerdict.best_part: int = Field(default=0, description=...)`. `@dataclass(frozen=True) class SourceFit: doc; part: int`. `Relevance.fits: tuple[SourceFit, ...] = ()` for on-topic sources only. `relevance_context` marks drafted/published parts `(drafted)`/`(published)` so the model knows which are frozen. Prompt v2 explains `best_part`.
- **VALIDATE**: `RelevanceFake` gains `parts: Mapping[str, int]` (word -> part); tests for fits.

### Task 3: deterministic fit rule
- **ACTION**: `series_fit.py`: `MIN_FIT_SOURCES = 2`; `NEW_TOPIC = 0`. `FitCheck(part: int, counts: Mapping[int, int], total: int)` with `mismatch` property: `counts[part] < MIN_FIT_SOURCES and max(other planned or NEW_TOPIC counts) > counts[part]`. `check_fit(series, part, fits)`: counts only planned parts and NEW_TOPIC; frozen-part and unknown numbers are counted as neither (logged). `fit_line(check)`.
- **VALIDATE**: table tests (good fit; 0 vs 1 elsewhere; 1 vs 1 tie drafts; sources supporting a published part never trigger).

### Task 4: planner retry + shared helpers
- **ACTION**: `build_planner` adds `middleware=[model_retry()]` (no caching: one call per run, prompt below the cacheable minimum). Rename `_source_ref`->`source_ref`, `_coverage`->`coverage`; split `_to_part(planned, number, docs)` into `to_part(planned, number, sources)`.
- **VALIDATE**: existing planner tests pass; retry test with `flaky`.

### Task 5: revise mode
- **ACTION**: `series_revise.py`: `RevisedPart(PlannedPart)` + `from_parts: list[int]`; `SeriesRevision(BaseModel)`: `reason: str`, `parts: list[RevisedPart]`. `build_reviser(model, system_prompt)` (same planner prompt, `response_format=SeriesRevision`, retry). `frozen_parts(series, path)` — drafted/published parts must be a prefix, else `ValueError`; a planned part must remain. `revise_task(series, docs)` — "Revise the outline ..." + frozen parts (number, title, question, status, summary, last teaser) + planned parts (number, title, question, brief, arc, access, source titles) + numbered source excerpts (`format_source`, `PLANNER_SOURCE_CHARS`). `run_revision(reviser, series, docs, today) -> Revised(series, revision)`: checks reason, part count (`>=1` remaining, total in `MIN_PARTS..MAX_PARTS`), numbers from `len(frozen)+1`, sources = carried old sources of `from_parts` (valid planned numbers only) + `coverage(source_indexes)`, deduped by URL; status `proposed`; appends `Revision(today, reason, changes)`. `outline_changes(old, new_parts, from_parts)`: per new part "Part N unchanged" / "Part N is old Part M (moved up|down)" / "Part N merges old Parts A, B" / "Part N is split from old Part M" / "Part N is new"; then "Old Part M dropped" for unreferenced planned parts; frozen parts "Part N unchanged (drafted)". If the result equals the old outline apart from status, still write (Varun asked) but changes say "no changes".
- **VALIDATE**: unit tests with scripted `SeriesRevision` tool calls.

### Task 6: prompt revise section
- **ACTION**: append `# Revising an outline` to `prompts/planner.md`, bump `version: 2`.

### Task 7: store
- **ACTION**: `check_revisable(path) -> Series` (load; not `complete`; frozen prefix; a planned part left). `save_revision(path, slug, before: Series, revised: Series) -> Path`: re-read text; must parse equal to `before` (else `ValueError` "changed during the run"); write `.bak` (`path.with_name(path.name + ".bak")`) atomically, then `save_series`. `check_can_plan`: when the file parses and has frozen parts or revisions, refuse even with `--overwrite`.
- **VALIDATE**: store tests.

### Task 8: `series revise`
- **ACTION**: parser `revise slug --since (7d) --drafts-dir --series-dir`. `_prepare_revise` (exit 2): settings, `check_revisable`, `collect_sources`, reviser built with planner model. Run (exit 1 on failure), `save_revision` (exit 1, outline kept on screen), `print_revision`.
- **VALIDATE**: CLI tests.

### Task 9: `issue --series` fit check
- **ACTION**: `--keep-outline` flag (ValueError without `--series`). `SeriesJob.reviser`. `_draft_series`: after the empty check, unless `keep_outline`, `check_fit`; print `fit_line`; on mismatch `adjust_outline(job, docs)` → run revision, save, print, return 0/1. Planner model built in `_prepare` for series runs.
- **VALIDATE**: CLI tests: mismatch writes revised file + `.bak`, no draft, exit 0; good fit drafts; `--keep-outline` drafts; reviser failure exit 1 with file untouched.

### Task 10: README + weekly Namespace.

---

## Testing Strategy
Unit: schema (revisions), fit rule table, revise task/outputs/changes, store save/guards, relevance fits. CLI: `series revise` success/usage/model failure/write failure; `issue --series` mismatch/keep-outline/good fit. Edge cases: no planned part left, frozen not prefix, model cites unknown parts/sources, part count over 6, file edited mid-run, `complete` series.

## Validation Commands
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest --cov=newsletter_machine
```
EXPECT: all pass, coverage >= 80% (currently ~99%).

### Manual Validation
- [ ] Live: a week whose links fit Part 3 produces a sensible revised outline (`@pytest.mark.live` not added: needs Varun's sources and a key).

## Acceptance Criteria
- [ ] Mismatch week -> revised proposal, no draft, exit 0
- [ ] Frozen parts byte-identical in meaning; revision recorded; `.bak` written
- [ ] `series approve` re-approves; `issue --series` then drafts
- [ ] All validation passes

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Relevance model's `best_part` noisy -> spurious revisions | M | M | threshold + strict "more elsewhere" rule; `--keep-outline`; revision is only a proposal |
| Full rewrite loses comments | H | L | `.bak` copy, CLI says so |
| Stale teaser in the last frozen part | M | M | task shows the teaser; prompt asks next part to honour it; diff output prints it |

## Notes
- Exit 0 on a revision: a clean, expected outcome like "nothing to draft"; the message says what to do. Phase 5 must treat "no draft written" from a revision as a notice, not a delivery.
- Series goes back to `proposed`, so no series is active until Varun approves; `series approve` stays the single approval step.
- Planner caching skipped: one call per run, prompt ~900 tokens.
