# Plan: Series mode Phase 2 — Draft a series part

## Summary
Add `--series <slug>` to `newsletter-machine issue`. Before any model call the command loads `series/<slug>.yaml`, checks it is `approved` and picks the next part (lowest-numbered `planned`). After ingest, one cheap structured-output call per usable source (new `prompts/relevance.md`, `NM_RELEVANCE_MODEL`, default the fast model) keeps on-topic sources and parks the rest in `drafts/<date>.parked.md`. The series topic, outline and this part's brief go through the existing angle seam to the editor, researcher and writer. After a fully successful run the part is marked `drafted` with its draft path, editing only those two lines of the file so Varun's comments survive.

## User Story
As Varun, I want `issue --series evals` to draft the next planned part from this week's on-topic links, so that I get a coherent series part without rebuilding the outline and brief by hand.

## Problem → Solution
`issue` only takes a free-text `--angle`, and every ingested link reaches the writer → `issue --series evals` filters links to the series, injects the part brief and outline, and records the draft against the part.

## Metadata
- **Complexity**: Medium (new modules follow existing patterns; one new prompt; additive prompt edits)
- **Source PRD**: `.claude/PRPs/prds/series-mode.prd.md`
- **PRD Phase**: Phase 2 — Draft a series part
- **Estimated Files**: ~16 (3 new src modules + 1 prompt, 7 src edits, 2 prompt edits, 4 test files, README)

---

## UX Design

### Before
```
$ newsletter-machine issue --angle "evals part 1: why demos lie" --since 7d --out drafts/2026-11-04.md
(every link this week feeds the draft; outline and brief pasted by hand)
```

### After
```
$ newsletter-machine issue --series evals --since 7d --out drafts/2026-11-04.md
Series 'evals': drafting Part 1 of 4, Why your demo passed and production failed (free)
Wrote 6 files to drafts/2026-11-04.sources
Relevance: 4 on-topic, 2 parked -> drafts/2026-11-04.parked.md
  Parked: A post about pricing (https://...): about SaaS pricing, not evals
Using 4 of 4 sources
Wrote drafts/2026-11-04.md (912 words, final draft v2)
...
Series: marked Part 1 drafted in series/evals.yaml
```
Zero on-topic sources: prints the parked list and "No on-topic sources for Part 1; nothing to draft." and exits 0 (same as "No links found; nothing to draft.").

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| `issue` flags | `--angle` | `--series <slug>`, `--series-dir` | `--series` + `--angle` is an argparse usage error (exit 2) |
| outputs | draft, critique, notes, sources/ | + `<stem>.parked.md` in series mode | always written in series mode, "(none)" when nothing parked |
| `series/<slug>.yaml` | written by plan/approve | part `status: drafted`, `draft: <out>` | only after exit 0 |
| notes / critique | no series info | "Series 'evals', Part 1 of 4: <title>" line | |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/cli_issue.py` | all | `_prepare` (exit 2 before model calls), `_gather`, `run_issue`, `_finalise` |
| P0 | `src/newsletter_machine/series_store.py` | 115-164 | `_approved_text`: surgical edit + verify + fallback rewrite |
| P0 | `src/newsletter_machine/critic.py` | 87-103, 145-153 | structured output via `response_format`, `structured_response` check |
| P0 | `src/newsletter_machine/researcher.py` | 36-97 | `model_retry()`-only middleware, `batch(..., return_exceptions=True)` |
| P1 | `src/newsletter_machine/writer.py` | 81-92 | `angle_line`, `format_source` |
| P1 | `src/newsletter_machine/editor_subagents.py` | 72-84, 167-187 | `EditorInputs`, `critique_version` -> `ReportMeta` |
| P1 | `src/newsletter_machine/issue_output.py` | 108-182 | `NotesInput`, `render_notes` |
| P1 | `src/newsletter_machine/config.py` | 172-178 | `load_planner_model` (mirror for relevance) |
| P2 | `tests/test_cli_issue.py` | 1-70 | `_use_models` fake-model factory |
| P2 | `tests/fakes.py` | all | `FakeModel`, `critic_reply` tool-call shape |

## External Documentation
No external research needed — feature uses established internal patterns (`create_agent(response_format=...)` as in `critic.py`/`planner.py`).

---

## Patterns to Mirror

### NAMING / MODEL CONFIG
```python
# SOURCE: src/newsletter_machine/config.py:172-178
def load_planner_model(settings: Settings, env: Mapping[str, str] | None = None) -> str:
    env = _load_env(env)
    return _require_provider_prefix(
        "NM_PLANNER_MODEL", env.get("NM_PLANNER_MODEL", "").strip() or settings.writer_model
    )
```

### STRUCTURED OUTPUT
```python
# SOURCE: src/newsletter_machine/planner.py:139-143, 174-177
return create_agent(model, tools=[], system_prompt=system_prompt, response_format=SeriesPlan, name=PLANNER_NAME)
output = result.get("structured_response")
if not isinstance(output, SeriesPlan):
    raise AgentOutputError("The planner did not return a structured outline.")
```

### BATCH PER SOURCE
```python
# SOURCE: src/newsletter_machine/researcher.py:84-86
results = researcher.batch(tasks, config={"max_concurrency": RESEARCH_CONCURRENCY}, return_exceptions=True)
```

### SURGICAL YAML EDIT WITH VERIFIED FALLBACK
```python
# SOURCE: src/newsletter_machine/series_store.py:115-122
new_text, count = STATUS_LINE.subn(r"status: approved\2", text, count=1)
if count and _parse_text(path, new_text) == approved:
    return new_text
return render_series_yaml(approved, slug)
```

### ERROR HANDLING (CLI)
```python
# SOURCE: src/newsletter_machine/cli_issue.py:331-342
except (ConfigError, ValueError, KeyError, OSError, ImportError) as exc:
    print(f"Config error: {exc}", file=sys.stderr)
    return EXIT_CONFIG
```

### TEST STRUCTURE
```python
# SOURCE: tests/test_cli_issue.py:34-57 — monkeypatch cli_issue.make_chat_model with a dict of scripted replies per model id
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/series_part.py` | CREATE | `next_part`, `check_draftable`, `outline_lines`, `series_angle`, `series_label` (pure) |
| `src/newsletter_machine/relevance.py` | CREATE | `RelevanceVerdict`, prompt, classifier build, `classify_sources` -> `Relevance` |
| `src/newsletter_machine/cli_issue_series.py` | CREATE | series-mode glue for `issue`: prepare, filter + parked file, mark drafted |
| `src/newsletter_machine/prompts/relevance.md` | CREATE | classifier prompt, `version: 1` |
| `src/newsletter_machine/series_store.py` | UPDATE | `mark_drafted` (surgical edit, verified, fallback rewrite) |
| `src/newsletter_machine/config.py` | UPDATE | `load_relevance_model` (`NM_RELEVANCE_MODEL`, blank = fast model) |
| `src/newsletter_machine/cli_issue.py` | UPDATE | `--series`/`--series-dir`, mutually exclusive with `--angle`; call series glue |
| `src/newsletter_machine/editor_subagents.py` | UPDATE | `EditorInputs.series_label` -> `ReportMeta.series` |
| `src/newsletter_machine/critique_report.py` | UPDATE | `ReportMeta.series` line |
| `src/newsletter_machine/issue_output.py` | UPDATE | `NotesInput.series` + parked lines in notes |
| `src/newsletter_machine/prompts/writer.md`, `editor.md` | UPDATE | one additive sentence each (version 1 -> 2) |
| `tests/test_series_part.py`, `tests/test_relevance.py`, `tests/test_cli_issue_series.py`, `tests/test_series_store.py`, `tests/test_config.py`, `tests/test_critique_report.py`, `tests/test_issue_output.py` | CREATE/UPDATE | TDD |
| `README.md` | UPDATE | `issue --series evals` usage |
| `.env.example` (if present) | UPDATE | `NM_RELEVANCE_MODEL` |

## NOT Building
- Continuity: previous-part summaries/URLs, teasers, `series published` (Phase 3)
- Outline adjustment when links don't fit (Phase 4)
- Weekly-run integration (Phase 5)
- Critic continuity checks; caching/retries for the planner
- Researcher prompt edits (its existing angle bullet already covers "how this source supports the angle")

---

## Step-by-Step Tasks

### Task 1: `series_part.py` (pure)
- **IMPLEMENT**: `next_part(series) -> SeriesPart | None` (lowest-numbered `planned`); `check_draftable(series, path) -> SeriesPart` raises `ValueError` naming the file when status != `approved` (hint `series approve <slug>`) or no planned part left; `outline_lines(series, current)`; `series_angle(series, part) -> str` (topic, outline titles + questions, this part's number/title/question/brief/arc/access, basic→advanced instruction); `series_label(slug, series, part) -> str` = `Series 'evals', Part 1 of 4: <title> (free)`.
- **GOTCHA**: `angle_line` prefixes "Varun's angle: " and strips; the text must read naturally after it.
- **VALIDATE**: `tests/test_series_part.py`.

### Task 2: `config.load_relevance_model`
- **IMPLEMENT**: mirror `load_planner_model`; blank = `settings.fast_model`.

### Task 3: `relevance.py` + `prompts/relevance.md`
- **IMPLEMENT**: `RelevanceVerdict(on_topic: bool, reason: str)`; `relevance_system_prompt()`; `build_relevance_classifier(model, prompt)` = `create_agent(..., response_format=RelevanceVerdict, middleware=[model_retry()])`; `relevance_task(context, doc, index)` with `format_source(doc, index, RELEVANCE_SOURCE_CHARS=4000)`; `classify_sources(classifier, docs, context) -> Relevance(kept, parked)` batching usable docs (concurrency 4). A failed call or missing structured output KEEPS the source (never drop on error) and is recorded in `Relevance.unchecked`. Failed (unusable) docs stay in `kept` so notes still list them as skipped.
- **GOTCHA**: batch order is preserved by `Runnable.batch`; fakes must be content-aware, not order-scripted, since concurrency reorders model calls.

### Task 4: `series_store.mark_drafted(path, slug, number, draft) -> bool`
- **IMPLEMENT**: re-read + validate; part must still be `planned` (else `ValueError`); edit that part's `status:` and `draft:` lines inside its block; verify parse equals `replace(series, parts=...)`; else full `render_series_yaml` rewrite; `write_atomic`. Returns True when comments were kept.

### Task 5: report + notes
- **IMPLEMENT**: `ReportMeta.series: str = ""` rendered as `*<series>*` under the title; `EditorInputs.series_label: str = ""` passed through `critique_version`; `NotesInput.series: str = ""`, `NotesInput.parked: tuple[str, ...] = ()` rendered as a "Series" section.

### Task 6: `cli_issue_series.py` + `cli_issue.py`
- **IMPLEMENT**: `SeriesJob(slug, path, series, part, angle, label, classifier, parked_path)` built in `_prepare` (exit 2 on any problem, before fetching); after `_gather`: classify, print relevance line + parked list, write parked file (`write_reported`, exit 1 on failure); zero on-topic → exit 0, no editor; editor gets the series angle; after `_finalise` returns 0 → `mark_drafted`, exit 1 with "draft kept" on failure; non-zero → "Part N stays planned".
- **GOTCHA**: argparse mutually-exclusive group for `--angle`/`--series` (argparse exits 2). Relevance model only built in series mode, so existing tests' `seen` sets stay unchanged.

### Task 7: prompts
- writer.md item 1 and editor.md step 4 get one additive sentence each; bump `version: 2`.

---

## Testing Strategy

| Test | Input | Expected |
|---|---|---|
| next part | parts planned/drafted mix | lowest planned |
| not approved / none planned / missing / invalid file | — | exit 2, no model built |
| `--series` + `--angle` | — | exit 2 |
| happy path | 3 sources, 1 off-topic | parked file lists 1; draft written; part drafted; comment kept; notes + critique mention series |
| zero on-topic | all off | exit 0, parked written, no draft, series untouched |
| classifier error | exception for one source | source kept, noted |
| run fails | editor no reply | exit 1, series untouched |
| mark_drafted fallback | status written oddly | full rewrite, returns False |
| relevance model config | blank / set / bad | fast / value / ConfigError |

## Validation Commands
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest --cov=newsletter_machine
```
EXPECT: clean; coverage >= 80% (currently ~99%).

### Manual Validation
- [ ] With ANTHROPIC_API_KEY: `series plan evals --since 28d`, `series approve evals`, `issue --series evals --since 7d --out drafts/<date>.md`; check parked list, draft follows the part arc, `series/evals.yaml` Part 1 `drafted`.

## Acceptance Criteria
- [ ] All tasks completed; validation passes; prompt diffs listed in the PR for Varun's approval

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Classifier drops a useful link | M | M | parked list printed + file; errors keep the source; `--sources` rerun |
| Surgical YAML edit misses an odd layout | L | L | verified against the parsed result; fallback full rewrite, reported |
| Series file edited during the run | L | M | `mark_drafted` re-reads and re-validates; part must still be planned |

## Notes
- Decisions: `--series` + `--angle` = usage error; zero on-topic = exit 0 (as "nothing to draft"); part marked drafted only on exit 0 (a salvaged/critique-less run leaves it `planned`, said on stderr); classifier errors keep the source; parked file always written in series mode; draft path stored as given to `--out`.
