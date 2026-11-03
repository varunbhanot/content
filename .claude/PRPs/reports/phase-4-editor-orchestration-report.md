# Implementation Report: Phase 4 — Editor orchestration (MVP)

## Summary
`newsletter-machine issue --out drafts/<date>.md [--since 7d | --links-file F | --sources DIR] [--angle TEXT] [--overwrite]` produces a draft from one command. It ingests the week's links with the Phase 2 code (or reuses an `ingest` folder), then runs a lead **editor** deep agent (`create_deep_agent`) that plans with its todo tool and `/plan.md`, and delegates through `task` to a **researcher** (fast model, per-source sourced notes), the Phase 3 **writer** and the Phase 3 **voice critic**, with up to `NM_MAX_REVISIONS` critique → revise loops (default 1). Sub-agents read trusted inputs from Python and save versioned files (`/drafts/vN.md`, `/critiques/vN.md`, ...) into the agent's in-state filesystem; code enforces the limits. Code then writes `<date>.md` (with the `## Sources` list rebuilt from the ingested sources), `<date>.critique.md` for that exact version (it runs the critic itself if the editor skipped it) and `<date>.notes.md`. Everything is tested offline with fake models. No live run yet: there is no `ANTHROPIC_API_KEY` in this environment.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Large | Large |
| Confidence | High: the sub-agent state contract was checked with a probe before planning | Met; one addition (salvaging a failed run, below) |
| Files Changed | ~20 | 28 (8 new src modules, 2 prompt files, 8 new test files + helper, docs) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Config | Complete | `NM_EDITOR_MODEL` (blank = writer model), `NM_MAX_REVISIONS` 0 to 3 |
| 2 | Workspace | Complete | `workspace.py`: paths, seeding, versioning, safe file reads |
| 3 | Researcher | Complete | `researcher.py` + `prompts/researcher.md`; one failing source never aborts |
| 4 | Sub-agent wrappers | Complete | `editor_subagents.py`; caps in code; refusing `general-purpose` |
| 5 | Editor | Complete | `editor.py` + `prompts/editor.md`; write-deny on protected dirs; recursion limit |
| 6 | Output | Complete | `issue_output.py`: Sources normalisation, notes |
| 7 | CLI | Complete | `cli_issue.py`; shared helpers moved to `cli_common.py` |
| 8 | Docs | Complete | README, `.env.example`, PRD row |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | `ruff check .`, `ruff format --check .`, `mypy src` (strict): zero issues |
| Unit Tests | Pass | 452 passed offline, 7 live deselected |
| Coverage | Pass | 99% total; every new module 100% |
| Build | Pass | `uv build --wheel` ships `prompts/editor.md` and `prompts/researcher.md` |
| CLI smoke | Pass | Real CLI, dummy key: sources read, agents built (incl. the Anthropic serial-tool-call middleware), API reached, 401 → "Editor failed", exit 1 |
| Live test | **Not run** | `tests/test_issue_live.py` skips: no `ANTHROPIC_API_KEY` here |

## Files Changed
Created: `src/newsletter_machine/{workspace,researcher,editor_subagents,editor,issue_output,cli_common,cli_issue}.py`, `src/newsletter_machine/prompts/{editor,researcher}.md`, `tests/{fakes,test_workspace,test_researcher,test_editor_subagents,test_editor,test_issue_output,test_cli_issue,test_issue_live}.py`, the plan and this report.
Updated: `src/newsletter_machine/{config,cli,writer,drafting}.py`, `tests/{test_config,test_writer,test_cli_ingest}.py`, `README.md`, `.env.example`, the PRD row.

## Deviations from Plan
- **Run salvage (added)**: the editor gets an in-memory checkpointer. If the lead fails after sub-agents saved a draft (rate limit, recursion limit), `run_editor` returns the saved files with `error` set; the CLI writes the latest draft, critique and notes, then exits 1. Without this a late failure would throw away paid-for drafts.
- **`cli_common.py`**: logging setup, exit codes, the Gmail reader and summaries moved out of `cli.py` so `cli_issue.py` can share them without an import cycle. Three monkeypatch targets in `tests/test_cli_ingest.py` moved with them (assertions unchanged).
- **`writer.py` refactor (no prompt change)**: `format_source` and `angle_line` extracted for reuse; the tag neutraliser also covers the new `<brief>`, `<research_notes>` and `<critique>` wrappers.
- **From review**: `NM_EDITOR_MODEL`/`NM_MAX_REVISIONS` live in a separate `EditorSettings` (`load_editor_settings`) so a bad value never breaks `hello`/`draft`; drafts are stored with the Sources list already rebuilt (so the critique matches the delivered text) plus `/drafts/vN.json` listing dropped links; a `SerialToolCalls` middleware asks Anthropic models for one tool call per turn, and a run-wide ledger in the wrappers refuses stale parallel calls from any model; the researcher runs sources 4 at a time and may retry once; prompts are rendered before any link is fetched; failed sources are seeded as `/sources/failed-N-slug.md` so `/sources/NN-*` numbers match the `[n]` labels.
- **Plan not archived; PRD Phase 4 left `in-progress`**, as in Phases 1 to 3: the live run and the "≤30 min edit" check are still open.

## Review
Three `code-review high` rounds (10, 10, 10 findings), all 30 fixed, none skipped. Highlights: parallel `task` calls bypassing the writer cap and overwriting `vN` (ledger + serial-call middleware), HTML-escaped `&amp;` URLs dropping real sources, `/sources/NN` numbering out of step with `[n]`, critique describing a pre-normalisation draft, notes written before the fallback critique, salvage triggering on lead-only files, text after the Sources list being deleted, all-failed ingest reported as a config error, and several error-message and duplication fixes. No CRITICAL/HIGH issues open.

## Issues Encountered
- `create_deep_agent` silently adds a `general-purpose` sub-agent with full tools on the lead's model. Supplying a refusing one with that name stops it.
- No Anthropic key in the sandbox, so no live draft.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_workspace.py` | 6 | seeding, safe reads, versions |
| `tests/test_researcher.py` | 7 | prompt, task, per-source notes, failures |
| `tests/test_editor_subagents.py` | 21 (+params) | each wrapper, caps, failures, revision task |
| `tests/test_editor.py` | 14 | prompt, task, full fake loop, write deny, salvage, serial calls, middleware |
| `tests/test_issue_output.py` | 8 | Sources normalisation (escaping, tails), notes |
| `tests/test_cli_issue.py` | 25 (+params) | happy paths, ingest, exit codes, fallbacks, write failures |
| `tests/test_config.py`, `tests/test_writer.py` | +13, +4 | new settings, tag neutralising |
| `tests/test_issue_live.py` | 1 (live) | real end-to-end on the fixture sources |

## Next Steps
- [ ] Live: `uv run pytest -m live tests/test_issue_live.py`, then a real `issue` run on a week of Gmail links
- [ ] Varun: approve the draft/notes format and review `prompts/editor.md`, `prompts/researcher.md`
- [ ] PRD success signal: two consecutive real issues need ≤30 min of edits; then archive the plan and mark Phase 4 `complete`
