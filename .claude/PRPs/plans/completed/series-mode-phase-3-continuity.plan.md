# Plan: Series mode Phase 3 — Continuity

## Summary
Make later series parts read like a series. `series published <slug> <n> <url>` records a live URL. After a fully successful `issue --series` run, the final draft's italic "Next in this series" line is extracted by regex, and one cheap fast-model call writes a one-sentence summary. Both are stored on the part, with the same comment-preserving line edit as `drafted`. When drafting Part N>1, the series angle carries the previous part's title, URL, summary and teaser, one-line summaries of all earlier parts, and opening/closing instructions. Series-only checklist items (a new `src/newsletter_machine/series_checks.yaml`, validated by `checklist.load_checklist`) are appended to the run's checklist, so the writer targets them and the critic judges them through the existing machinery.

## User Story
As Varun, I want each new part to know what the previous part said, linked and promised, so that Part 2 opens with a one-clause link back to Part 1, delivers Part 1's teaser and points to Part 3, without me rebuilding that by hand.

## Problem → Solution
Every part is drafted as a standalone issue; `url`, `summary` and `teaser` exist in the schema but nothing writes or reads them → `series published` writes `url`; the draft run writes `summary` and `teaser`; the next run injects them and checks continuity.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `.claude/PRPs/prds/series-mode.prd.md`
- **PRD Phase**: Phase 3 — Continuity
- **Estimated Files**: ~20 (3 new src + 1 prompt + 1 YAML, ~8 src edits, 3 prompt edits, tests, README)

---

## UX Design

### Before
```
$ newsletter-machine issue --series evals --since 7d --out drafts/2026-11-11.md
(Part 2 drafted standalone: no link back, no recap, no teaser; Varun adds them by hand)
(no command records Part 1's URL)
```

### After
```
$ newsletter-machine series published evals 1 https://varunbhanot.substack.com/p/evals-part-1
Recorded Part 1 published at https://varunbhanot.substack.com/p/evals-part-1 in series/evals.yaml

$ newsletter-machine issue --series evals --since 7d --out drafts/2026-11-11.md
Drafting Series 'evals', Part 2 of 4: Golden sets (paid)
...
Summarised Part 2: <one sentence>
Teaser: Next in this series: ...
Marked Part 2 drafted in series/evals.yaml
```
Drafting Part N while Part N-1 has no URL prints a warning naming the `series published` command, and the writer leaves a `[VARUN: ...]` marker for the link.

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `series published <slug> <n> <url>` | n/a | sets part `status: published`, `url` | part must be drafted or published (re-record corrects a URL); exit 2 on bad URL/part |
| `issue --series` success | marks drafted + draft path | also writes `summary`, `teaser` | summary failure warns, still marks drafted, exit 0 |
| series angle | outline + brief | + earlier parts, previous part details, opening/closing instructions | |
| critic checklist (series runs) | voice checklist | + 1 to 3 series items | `voice/critic-checklist.yaml` untouched |
| `series show` | no summary/teaser | prints Summary / Teaser lines | |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/series_store.py` | 196-262 | `_part_block`, `_drafted_text`, `_parses_to`, `mark_drafted`: generalise these |
| P0 | `src/newsletter_machine/series_part.py` | all | `series_angle` to extend |
| P0 | `src/newsletter_machine/cli_issue_series.py` | all | `SeriesTarget`, `SeriesJob`, `finish_series` |
| P0 | `src/newsletter_machine/cli_issue.py` | 148-195 | `_build_agents`, `_prepare` (grounding seam) |
| P0 | `src/newsletter_machine/checklist.py` | all | `load_checklist(path, sections)` validation to reuse |
| P1 | `src/newsletter_machine/critic.py` | 70-80, 120-153 | critic prompt built from checklist; `merge_results` uses `inputs.checklist` |
| P1 | `src/newsletter_machine/cli_series.py` | all | subcommand registration and exit codes |
| P1 | `src/newsletter_machine/researcher.py` | 36-50 | `create_agent(..., middleware=[model_retry()])` pattern |
| P2 | `tests/test_cli_issue_series.py` | 1-120 | `_use_models`, `_series_file`, `_part` fixtures |
| P2 | `tests/test_series_store.py` | 300-345 | `mark_drafted` tests |

## External Documentation
No external research needed — feature uses established internal patterns.

---

## Patterns to Mirror

### COMMENT-PRESERVING EDIT + VERIFY + FALLBACK
```python
# SOURCE: src/newsletter_machine/series_store.py:247-258
def mark_drafted(path: Path, slug: str, number: int, draft: str) -> bool:
    text = _read(path)
    expected = _drafted_series(path, _parse_text(path, text), number, draft)
    edited = _drafted_text(text, number, draft)
    kept = _parses_to(path, edited, expected)
    if kept and edited is not None:
        write_atomic(path, edited)
    else:
        save_series(path, expected, slug)  # checks the rewrite loads before writing
```

### CLI EXIT CODES
```python
# SOURCE: src/newsletter_machine/cli_series.py:144-160
    try:
        approval = check_approval(args.series_dir, args.slug)
    except USAGE_ERRORS as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    ...
    except OSError as exc:
        print(f"Could not write the series: {exc}", file=sys.stderr)
        return EXIT_ERROR
```

### CHEAP MODEL CALL
```python
# SOURCE: src/newsletter_machine/researcher.py:36-49
    return create_agent(model, tools=[], system_prompt=system_prompt,
                        middleware=[model_retry()], name=RESEARCHER_NAME)
```

### TEST STRUCTURE
```python
# SOURCE: tests/test_cli_issue_series.py:77-95 — _use_models patches cli_issue.make_chat_model
# with a factory returning scripted fakes keyed by "fake:<role>" model names.
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/series_edit.py` | CREATE | generic comment-preserving part line edit (moved `_part_block`, generalised `_drafted_text`) |
| `src/newsletter_machine/series_store.py` | UPDATE | `mark_drafted(..., summary, teaser)`, `mark_published`, shared `_update_part` |
| `src/newsletter_machine/series_summary.py` | CREATE | `extract_teaser` (regex), summariser build/run |
| `src/newsletter_machine/prompts/summary.md` | CREATE | one-sentence core-claim prompt |
| `src/newsletter_machine/series_checks.py` | CREATE | load `series_checks.yaml` via `load_checklist`, pick and fill items per part |
| `src/newsletter_machine/series_checks.yaml` | CREATE | series-only checklist items (templates) |
| `src/newsletter_machine/series_part.py` | UPDATE | continuity lines in `series_angle`, `previous_part`/`following_part` |
| `src/newsletter_machine/series.py` | UPDATE | `format_outline` prints summary/teaser |
| `src/newsletter_machine/cli_issue_series.py` | UPDATE | summariser on job, `series_grounding`, summary/teaser in `finish_series`, URL warning |
| `src/newsletter_machine/cli_issue.py` | UPDATE | pass series checklist into `_build_agents`; build summariser |
| `src/newsletter_machine/cli_series.py` | UPDATE | `published` subcommand |
| `src/newsletter_machine/prompts/writer.md`, `editor.md`, `critic.md` | UPDATE | one additive sentence each, version bump |
| `tests/...` | CREATE/UPDATE | `test_series_edit.py`, `test_series_summary.py`, `test_series_checks.py`, additions to store/part/cli tests |
| `README.md` | UPDATE | `series published`, continuity |

## NOT Building
- Outline adjustment (Phase 4), weekly-run integration (Phase 5).
- Automatic URL discovery via RSS.
- Planner caching/retries.
- Re-extracting summary/teaser at `series published` (Varun edits them by hand in the YAML if he changed the published text).
- New mechanical check kinds in `checklist.py` (the series items are judgement items; the final-part "no teaser" item uses existing `patterns`).

---

## Step-by-Step Tasks

### Task 1: `series_edit.py`
- **ACTION**: Move `_part_block` from `series_store.py`; add `edit_part(text, number, *, statuses: tuple[str, ...], status: str, fields: Mapping[str, str]) -> str | None`.
- **IMPLEMENT**: Inside the part block, replace the `status:` line whose value is one of `statuses` (keeping a trailing comment) with `status: <status>`; for each field, replace its single line value with `json.dumps(value)` keeping a trailing comment, or insert the line after the status line when the key is missing. Return None when the status line is not found. Callers verify by parsing.
- **GOTCHA**: a multi-line (block scalar) value leaves continuation lines behind; the caller's parse-equality check then falls back to a full rewrite. Insert missing keys in the given order.
- **VALIDATE**: unit tests for replace, insert, comments kept, no status match → None.

### Task 2: `series_store` updates
- **ACTION**: `mark_drafted(path, slug, number, draft, *, summary="", teaser="")` and `mark_published(series_dir, slug, number, url) -> Publication` via a shared `_update_part`.
- **IMPLEMENT**: `check_publication` validates (`URL_PATTERN` fullmatch + `urlsplit` netloc; part exists; status `drafted` or `published`) and returns the new text or None when the URL is already recorded; `save_publication` writes it. Same verify-or-rewrite flow.
- **VALIDATE**: existing `mark_drafted` tests still pass; new tests for summary/teaser, publish happy path, re-record, same-URL no-op, planned part refused, bad URL refused, comments kept.

### Task 3: `series_summary.py` + `prompts/summary.md`
- **IMPLEMENT**: `extract_teaser(draft)`: last line matching `^\s*([*_])(Next in this series\b.+?)\1\s*$` (case-insensitive), inner text stripped. `build_summariser(model, prompt)`, `summarise_part(summariser, draft) -> str`: body without Sources, capped at `SUMMARY_DRAFT_CHARS`; output collapsed to one line, capped at `MAX_SUMMARY_CHARS`; empty → `AgentOutputError`.
- **VALIDATE**: teaser variants (`*…*`, `_…_`, none, two teasers picks last, bold `**` not matched); summary with fake model.

### Task 4: `series_checks.yaml` + `series_checks.py`
- **IMPLEMENT**: YAML in checklist schema with four ids: `series-link-back` (Openings), `series-teaser-delivered` (Openings), `series-next-teaser` (Closings), `series-final-no-teaser` (Closings, `patterns: ['next in this series']`). `$placeholders` in rule/check. `load_series_checks(sections)` loads via `load_checklist` and checks the id set exactly and that all placeholders fill. `series_checklist(base, series, part, checks) -> Checklist` appends applicable items: link-back when a previous part exists; teaser-delivered when the previous part has a teaser; next-teaser when a following part exists; final-no-teaser otherwise.
- **GOTCHA**: package data: hatchling wheel includes non-Python files under `src/newsletter_machine`; read with `importlib.resources.as_file`.
- **VALIDATE**: item selection per part position; values substituted; bad YAML/unknown placeholder raise `ValueError`.

### Task 5: `series_angle` continuity
- **IMPLEMENT**: For N>1 add "Earlier parts" (one line each, summary or "no summary recorded"), "Previous part" block (title, URL or "not published yet", summary, teaser), and instructions: open with a one-clause link back (Markdown link to the URL, or a `[VARUN: link to Part N-1 once it is published]` marker when none), deliver the teaser's promise, brief callbacks allowed. Closing: next part's title/question with the italic `*Next in this series: ...*` line before `## Sources`; final part: no such line.
- **VALIDATE**: unit tests for Part 1, middle part, final part, unpublished previous.

### Task 6: wiring in `cli_issue_series.py` / `cli_issue.py`
- **IMPLEMENT**: `SeriesTarget` gains `checks: Checklist` loaded in `series_target` (exit 2 on error). `series_grounding(grounding, target)` returns grounding with the combined checklist; `_build_agents(settings, target)` uses it. `SeriesJob` gains `summariser`. `finish_series` reads the draft, extracts teaser, summarises (failure → warning, empty summary), marks drafted with both. Warn at start when the previous part has no URL.
- **VALIDATE**: CLI tests: Part 2 run injects continuity into the writer task and critic prompt, records summary/teaser; summary failure still marks drafted.

### Task 7: `series published` CLI and `series show`
- **VALIDATE**: CLI tests for exit codes 0/1/2, output lines.

### Task 8: prompt edits (additive, version bumps) and README.

---

## Testing Strategy
Offline only; fakes from `tests/fakes.py`. TDD per task. Coverage stays ≥ 80% (currently ~99%).

### Edge Cases Checklist
- [ ] URL with spaces / ftp scheme / no host → exit 2
- [ ] Part number out of range / planned part → exit 2
- [ ] Same URL recorded twice → no write, exit 0
- [ ] Hand-edited series file with comments → comments kept
- [ ] Block-scalar summary in YAML → full rewrite fallback
- [ ] Draft without a teaser → empty teaser, warning when a next part exists
- [ ] Summary model failure → drafted, empty summary, warning, exit 0
- [ ] Final part → final-no-teaser item, no next-teaser instruction

---

## Validation Commands
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest --cov=newsletter_machine
```
EXPECT: all pass, coverage ≥ 80%.

### Manual Validation
- [ ] `series published evals 1 <url>` on the real evals file keeps comments
- [ ] Live Part 2 draft after Part 1 is published: opens with a one-clause link to Part 1, delivers its teaser, ends with a Part 3 teaser

---

## Acceptance Criteria
- [ ] All tasks completed; validation passes; no edits under `voice/`
- [ ] Prompt diffs and series checklist items listed verbatim in the PR

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Critic fails `no-invented-facts` on the recap (not in sources) | M | M | the link-back item quotes the previous summary; critic.md line says a recap matching it is not invented |
| Summary drifts from the published text | M | L | Varun can edit `summary` in the YAML; noted in README |
| Line edit corrupts YAML | L | H | parse-equality verification + full rewrite fallback (as Phase 2) |

## Notes
- Decision: summary + teaser at draft time only (from the final machine draft). Teaser by regex; summary by one fast-model call (`NM_FAST_MODEL`), because a deterministic first-sentence pick is usually the hook or the recap, not the claim.
- Decision: `series published` accepts a `drafted` or already `published` part (re-recording corrects a wrong URL); a `planned` part is refused.
- Decision: drafting Part N does not require Part N-1 to be published; it warns and the writer leaves a `[VARUN: ...]` marker.
