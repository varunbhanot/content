# Plan: Series mode Phase 1 — Series plan & approve

## Summary
Add a `series` command group to `newsletter-machine`: `series plan <topic>` reads the source folders past `issue` runs saved (`drafts/<YYYY-MM-DD>.sources/`) inside a lookback window (default 28 days), asks a planner model (new `prompts/planner.md`, encoding the PRD's 7 planning rules) for a 3–6 part outline as structured output, and writes `series/<slug>.yaml` (status `proposed`) atomically. `series approve <slug>` moves it to `approved` (one approved series at a time); `series show <slug>` prints the outline. The YAML is validated on every load into frozen dataclasses; an invalid file exits 2 with a message naming the file and field.

## User Story
As Varun, I want the machine to turn the last few weeks of links I read into a proposed series outline that I can edit and approve, so that I stop holding the series plan in my head.

## Problem → Solution
No series state exists; the outline lives in Varun's head → `series plan evals --since 28d` writes `series/evals.yaml` (parts with question, brief, basic→advanced arc, free/paid, source coverage, thin flag) and `series approve evals` locks it.

## Metadata
- **Complexity**: Medium-Large (new module family following existing patterns, one new prompt)
- **Source PRD**: `.claude/PRPs/prds/series-mode.prd.md`
- **PRD Phase**: Phase 1 — Series plan & approve
- **Estimated Files**: ~14 (5 src modules + 1 prompt + config/cli/writer edits, 5 test files, README)

---

## UX Design

### Before
```
(no series support; Varun keeps the outline in his head and passes --angle by hand)
```

### After
```
$ uv run newsletter-machine series plan evals --since 28d
Planning from 14 sources in 4 folders (drafts/2026-10-09.sources ... drafts/2026-10-30.sources)
Wrote series/evals.yaml (proposed, 4 parts)

Series 'evals' (proposed): evals
Part 1 [free, planned] Why your demo passed and production failed
  Question: Why do agent demos that look great fail in production?
  Arc: demo vs production -> what an eval is -> where evals sit in the lifecycle
  Brief: ...
  Sources (3): Why agent demos fail (https://...), ...
Part 2 [paid, planned] Building a golden set   THIN: needs more reading on labelling cost
  ...
Next: edit series/evals.yaml if you want, then run: newsletter-machine series approve evals

$ uv run newsletter-machine series approve evals
Approved series/evals.yaml (4 parts). It is now the active series.

$ uv run newsletter-machine series show evals
(the outline above)
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| CLI | no `series` | `series plan/approve/show` | mirrors `issue`/`weekly` registration |
| Repo | no `series/` | `series/<slug>.yaml` committed | not git-ignored (PRD decision) |
| Env | — | `NM_PLANNER_MODEL` (default: writer model) | models only via config |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/checklist.py` | all | YAML validation pattern (`_text`, unknown-field rejection, `one_of`, path-prefixed ValueError) |
| P0 | `src/newsletter_machine/critic.py` | 32-45, 85-100, 141-151 | pydantic schema + `create_agent(response_format=...)` + `structured_response` |
| P0 | `src/newsletter_machine/cli_issue.py` | 1-5, 89-100, 150-170 | parser registration, `_prepare` (exit 2 before model) |
| P0 | `src/newsletter_machine/cli.py` | 205-230 | `main` dispatch, exit-code mapping in `_run_draft` |
| P1 | `src/newsletter_machine/config.py` | 147-158 | `load_editor_settings` (model default = writer model) |
| P1 | `src/newsletter_machine/ingest.py` | 59-63, 158-173 | `slugify`, `read_sources` |
| P1 | `src/newsletter_machine/writer.py` | 40-80 | `usable_sources`, `neutralise_tags`, `format_source` |
| P1 | `src/newsletter_machine/drafting.py` | 63-72 | `write_atomic` |
| P1 | `src/newsletter_machine/sources.py` | 120-136, 83-96 | `parse_since`, `normalize_url` |
| P2 | `tests/fakes.py`, `tests/test_cli_issue.py:1-60` | all | fake models, env fixture, monkeypatching `make_chat_model` |

## External Documentation
No external research needed — feature uses established internal patterns (LangChain `create_agent` structured output already used by the critic; PyYAML already a dependency with `types-PyYAML`).

---

## Patterns to Mirror

### NAMING_CONVENTION
// SOURCE: src/newsletter_machine/critic.py:22-29
```python
CRITIC_NAME = "voice-critic"
CRITIC_PROMPT = "critic"
```
Module-level UPPER constants, `snake_case` functions, private helpers `_x`, frozen dataclasses.

### ERROR_HANDLING
// SOURCE: src/newsletter_machine/checklist.py:46-50, 95-100
```python
def _text(raw: Mapping[str, Any], name: str, where: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: '{name}' must be non-empty text")
    return value.strip()
...
    unknown = set(raw) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)
    if unknown:
        raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}")
```
CLI mapping (src/newsletter_machine/cli.py `_run_draft`): `(ConfigError, ValueError, KeyError, OSError, ImportError)` → `Config error: ...` + `EXIT_CONFIG`; model run `Exception` → `logger.debug(..., exc_info=True)` + message + `EXIT_ERROR`.

### LOGGING_PATTERN
// SOURCE: src/newsletter_machine/critic.py:146
```python
logger = logging.getLogger(__name__)
logger.info("Critic checking a %d-character draft", len(draft))
```

### STRUCTURED_OUTPUT
// SOURCE: src/newsletter_machine/critic.py:92-100, 146-150
```python
runnable = create_agent(model, tools=[], system_prompt=system_prompt,
                        response_format=CriticOutput, name=CRITIC_NAME)
...
output = result.get("structured_response")
if not isinstance(output, CriticOutput):
    raise AgentOutputError("The critic did not return structured feedback.")
```

### ATOMIC_WRITE
// SOURCE: src/newsletter_machine/drafting.py:63-72 — `write_atomic(path, text)`.

### TEST_STRUCTURE
// SOURCE: tests/test_cli_issue.py:21-55, tests/fakes.py:29-47
```python
@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
...
monkeypatch.setattr(cli_issue, "make_chat_model", _make)
...
AIMessage(content="", tool_calls=[{"name": "CriticOutput", "args": args, "id": "c"}])
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/series.py` | CREATE | Schema (frozen dataclasses), parse/validate from mapping, `to_mapping`, outline formatting |
| `src/newsletter_machine/series_store.py` | CREATE | Paths, load/save (atomic), plan-overwrite guard, approve (comment-preserving), active-series lookup |
| `src/newsletter_machine/planner.py` | CREATE | Saved-source collection by date window, planner agent, structured output → `Series` |
| `src/newsletter_machine/cli_series.py` | CREATE | `series plan/approve/show` parser + runners, exit codes |
| `src/newsletter_machine/prompts/planner.md` | CREATE | Planner system prompt with the 7 rules (`$min_parts`, `$max_parts`) |
| `src/newsletter_machine/config.py` | UPDATE | `load_planner_model` (`NM_PLANNER_MODEL`, default writer model) |
| `src/newsletter_machine/writer.py` | UPDATE | `format_source(..., max_chars=MAX_SOURCE_CHARS)` so the planner reuses it with a smaller excerpt |
| `src/newsletter_machine/cli.py` | UPDATE | Register `series`, dispatch |
| `tests/test_series.py`, `tests/test_series_store.py`, `tests/test_planner.py`, `tests/test_cli_series.py`, `tests/test_series_live.py` | CREATE | Unit, CLI integration, live (marked) |
| `tests/test_config.py`, `tests/test_prompts.py` | UPDATE | Planner model + prompt |
| `README.md` | UPDATE | "Plan a series" section + `NM_PLANNER_MODEL` row |

## NOT Building
- `issue --series`, relevance filter, parked list (Phase 2); `series published`, summaries/teasers (Phase 3); re-planning an approved outline (Phase 4); weekly integration (Phase 5).
- Planning from undated folders (`ingest --out sources/x`): only `drafts/<YYYY-MM-DD>.sources/`.
- Cross-field rules for later phases (e.g. `drafted` requires `draft`): those phases add them.
- A `complete` transition command.

---

## Step-by-Step Tasks

### Task 1: Series schema (`series.py`)
- **ACTION**: Frozen dataclasses + validation from a parsed YAML mapping.
- **IMPLEMENT**:
  - `SeriesStatus = Literal["proposed","approved","complete"]`, `Access = Literal["free","paid"]`, `PartStatus = Literal["planned","drafted","published"]`.
  - `SourceRef(title, url)`; `SeriesPart(number, title, question, brief, arc: tuple[str,...], access, status, sources: tuple[SourceRef,...], thin: bool, needs: str = "", draft: str|None=None, url: str|None=None, summary: str="", teaser: str="")`; `Series(topic, status, parts)`.
  - `parse_series(data: object, where: str) -> Series`: mapping check; unknown top-level/part fields rejected; required text non-empty; `arc` list of ≥2 non-empty strings; `access`/`status` via `one_of`; `thin` must be bool; `sources` list of `{title, url}` with http(s) URL; `number` must equal position (1..n); ≥1 part; optional `draft`/`url` null or text (url http(s)).
  - `series_to_mapping(series) -> dict` (inverse; round-trips).
  - `format_outline(series, slug) -> str` for printing.
  - `SLUG_PATTERN` kebab-case.
- **MIRROR**: ERROR_HANDLING (checklist.py).
- **IMPORTS**: `validation.is_int, one_of`.
- **GOTCHA**: YAML `true` is bool and `is_int` excludes it; YAML may parse a bare date-like or number title as non-str → reject with clear error.
- **VALIDATE**: `tests/test_series.py` parametrized invalid cases; round-trip test.

### Task 2: Store (`series_store.py`)
- **ACTION**: File I/O and state transitions.
- **IMPLEMENT**: `DEFAULT_SERIES_DIR = Path("series")`; `series_path(dir, slug)` (validates slug); `load_series(path)` (missing → `FileNotFoundError` with hint to run `series plan`; YAML error → ValueError naming path); `render_series_yaml(series, slug)` (header comment + `yaml.safe_dump(sort_keys=False, allow_unicode=True, width=1000)`); `save_series(path, series, slug)` (mkdir parent, `write_atomic`); `check_can_plan(path, overwrite)` (approved/complete → refuse always; proposed exists without overwrite → `FileExistsError`); `approve_series(dir, slug) -> tuple[Series, bool]` (proposed→approved; already approved → no-op flag; complete → ValueError; another approved series in dir → ValueError naming it); approve rewrites only the top-level `status:` line via regex so Varun's comments/edits survive, re-parses the result, falls back to a full re-dump if the line is not found; `approved_series(dir) -> tuple[str,...]` slugs.
- **MIRROR**: ATOMIC_WRITE.
- **GOTCHA**: scanning the dir must validate every `*.yaml`; an invalid other file is a config error (fail fast) — message names it.
- **VALIDATE**: `tests/test_series_store.py`.

### Task 3: Planner (`planner.py`, `prompts/planner.md`, `writer.py`, `config.py`)
- **ACTION**: Collect saved sources; run planner; convert.
- **IMPLEMENT**:
  - `SOURCES_DIR_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})\.sources")`; `saved_source_dirs(drafts_dir, since: date) -> tuple[Path,...]` (dated ≥ since, sorted, invalid dates ignored); `collect_sources(drafts_dir, since) -> PlanningInput(dirs, docs)`: `read_sources` each (empty folder skipped with warning), `usable_sources`, dedupe by `normalize_url` keeping the newest; none → ValueError "No saved sources in <dir> since <date>: run `issue` first ...". Missing drafts dir → ValueError.
  - `planner_task(topic, docs)`: topic line + sources via `format_source(doc, i, max_chars=PLANNER_SOURCE_CHARS=4000)`.
  - pydantic `PlannedPart(title, question, brief, arc: list[str], access: Literal, source_indexes: list[int], thin: bool, needs: str)` and `SeriesPlan(parts: list[PlannedPart])`.
  - `planner_system_prompt(prompt=None)` renders `min_parts=3, max_parts=6`. `build_planner(model, system_prompt)` like `build_critic`.
  - `run_planner(planner, topic, docs) -> Series`: `structured_response` check; enforce 3–6 parts, non-empty text, ≥2 arc steps (else `AgentOutputError`); map indexes→`SourceRef` (unknown dropped with warning, duplicates removed); part 1 forced `free` (rule 5, logged if changed); `thin` = model flag OR fewer than `MIN_PART_SOURCES=2`; status `proposed`, parts `planned`.
  - `config.load_planner_model(settings, env=None) -> str` (`NM_PLANNER_MODEL` blank → writer model, provider prefix required).
  - `writer.format_source` gains `max_chars` parameter (default unchanged).
- **MIRROR**: STRUCTURED_OUTPUT; config `load_editor_settings`.
- **GOTCHA**: Untrusted source text — prompt says it is data; `neutralise_tags` via `format_source`. Model URLs never trusted: coverage comes from indexes mapped in code.
- **VALIDATE**: `tests/test_planner.py`, `tests/test_config.py`, `tests/test_prompts.py`.

### Task 4: CLI (`cli_series.py`, `cli.py`)
- **ACTION**: `add_series_parser(sub)` with nested subparsers `plan` (`topic`, `--since` default `28d`, `--drafts-dir` default `drafts`, `--series-dir` default `series`, `--overwrite`), `approve <slug>`, `show <slug>` (both `--series-dir`). `run_series(args)` dispatches.
- **IMPLEMENT**: `_prepare_plan` (settings, logging, slug from `slugify(topic)` with a letters/digits check, `check_can_plan`, since via `parse_since(value, now in issue_timezone())`, `collect_sources`, planner model + prompt) → any `(ConfigError, ValueError, KeyError, OSError, ImportError)` = exit 2; model run `Exception` = exit 1; re-check `check_can_plan` before writing (approval may have happened during the model call); write failure = exit 1; print outline + next-step line. approve/show need no API key.
- **MIRROR**: `cli.py:_run_draft`, `cli_issue.add_issue_parser`.
- **VALIDATE**: `tests/test_cli_series.py` (monkeypatch `cli_series.make_chat_model`).

### Task 5: Docs
- README "Plan a series" section and `NM_PLANNER_MODEL` row; PRD row links the plan.

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| parse valid | full mapping | `Series` equal to expected | no |
| round trip | series → yaml → parse | equal | no |
| invalid fields | missing topic, bad status, bad access, arc of 1, number gap, unknown field, `thin: "yes"`, bad url, non-mapping | ValueError naming field | yes |
| approve | proposed file with comments | status approved, comments kept | yes |
| approve with other active | two files | ValueError naming other | yes |
| approve complete | complete | ValueError | yes |
| plan guard | approved exists + overwrite | refused | yes |
| collect window | folders 2026-10-01, 10-20, junk name | only ≥ since, junk ignored | yes |
| dedupe | same url in two weeks | one doc | yes |
| no sources | empty drafts | ValueError | yes |
| run_planner | fake SeriesPlan | parts numbered, part 1 free, thin forced, unknown index dropped | yes |
| part count | 2 or 7 parts | AgentOutputError | yes |
| CLI plan | fake model | yaml written, exit 0, outline printed | no |
| CLI no sources | — | exit 2, model never built | yes |
| CLI model fails | raising model | exit 1, no file | yes |

### Edge Cases Checklist
- [x] Empty input (no sources, empty topic)
- [x] Invalid types (YAML bools/ints in text fields)
- [x] Concurrent access (approval during a model call: re-check before write)
- [x] Network failure (model exception → exit 1)
- [ ] Maximum size input (per-source excerpt cap 4,000 chars; no total cap — noted)

---

## Validation Commands

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest
uv run pytest --cov=newsletter_machine --cov-report=term-missing
```
EXPECT: zero lint/type errors, all tests pass, coverage ≥ 80%.

### Manual Validation
- [ ] `ANTHROPIC_API_KEY` set; `uv run newsletter-machine series plan evals --since 28d` → `series/evals.yaml`, 3–6 parts.
- [ ] `uv run newsletter-machine series approve evals`, then `series show evals`.
- [ ] `uv run pytest -m live tests/test_series_live.py`.

---

## Acceptance Criteria
- [ ] All tasks completed; validation commands pass; no type or lint errors
- [ ] Invalid series file → exit 2 with file + field named
- [ ] No model call when there are no sources / file exists / series approved

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Fake model + `create_agent(response_format=...)` picks a strategy the fake cannot satisfy | L | M | same approach already works for the critic tests (tool call named after the schema) |
| Planner input too large over many weeks | M | M | 4,000-char excerpt per source; dedupe across weeks |
| Re-dumping YAML loses Varun's comments | M | L | approve edits only the status line |

## Notes
- `--series-dir` added (default `series`) so tests and other checkouts need no `chdir`; PRD only names `--since`.
- Approving an already-approved series is a no-op with exit 0 (idempotent).
- Part count 3–6 is enforced on the planner's output; a hand-edited file only needs ≥1 consecutively numbered parts, so later phases (adjustment) are not blocked.
