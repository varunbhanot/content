# Implementation Report: Phase 3 — Voice writer & critic

## Summary
`newsletter-machine draft --sources DIR [--angle TEXT] --out issue.md` reads the Markdown files `ingest` wrote, runs a **writer** sub-agent grounded in the approved style guide and all 13 hand-written posts, saves the draft, then runs a **voice critic** sub-agent once and writes `issue.critique.md` with pass/fail per checklist item, verbatim quotes and suggested fixes. The checklist is an editable data file (`voice/critic-checklist.yaml`); every item cites the style-guide section it comes from, and the loader refuses items whose section does not exist. Exact rules (em dashes, banned words, word range, paragraph length) are checked in code; judgement rules go to the model with structured output. Prompts live in versioned files under `src/newsletter_machine/prompts/`. Both sub-agents are `CompiledSubAgent`s, so Phase 4's lead agent can pass them to `create_deep_agent(subagents=[...])` unchanged (covered by a test). Everything runs offline with fake chat models. The live run has not happened yet: no `ANTHROPIC_API_KEY` in this environment.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Large | Large |
| Confidence | High: verified the sub-agent API with a probe first | Met. The design held; the three review rounds hardened the Markdown checks and the CLI file handling |
| Files Changed | ~20 | 38 (11 new src modules/prompt files, 11 new test files + fixtures, checklist, docs) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | `frontmatter.py` + style-guide loaders | Complete | `split_front_matter` moved out of `voice.py`; `load_style_guide`, `style_guide_sections` |
| 2 | Checklist data file + loader | Complete | 19 items over all 7 style-guide sections; 7 mechanical |
| 3 | Prompt files + loader | Complete | `writer.md`, `critic.md` (front-matter `version: 1`), `string.Template` fails fast on a missing value |
| 4 | `ingest.read_sources` | Complete | Inverse of `render_source`; numeric order |
| 5 | Writer | Complete | Sources in `<source>` tags, wrapper tags in source text neutralised, 24k-char cap per source, failed sources skipped |
| 6 | Mechanical checks (`checks.py`) | Complete | Measures reader-visible text: link targets, URLs and `[VARUN: ...]` markers excluded |
| 7 | Critic | Complete | `ToolStrategy(CriticOutput)`; merges code + model results in checklist order; missing items are `not-checked` |
| 8 | Report + drafting | Complete | `critique_report.py`, `drafting.py` (`build_subagents`, output paths, atomic writes) |
| 9 | Config + CLI | Complete | `NM_CRITIC_MODEL` (blank = writer model); exit 0/1/2 |
| 10 | Docs | Complete | README "Draft in Varun's voice", `.env.example`, PRD row |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | `ruff check .`, `ruff format --check .`, `mypy src` (strict): zero issues |
| Unit Tests | Pass | 346 passed offline, 6 live deselected |
| Coverage | Pass | 99% total; every new module 100% |
| Build | Pass | `uv build --wheel` includes `prompts/writer.md` and `prompts/critic.md` |
| CLI smoke | Pass | Real CLI with a dummy key: sources read, prompts built, API reached, 401 → "Writer failed", exit 1 |
| Live test | **Not run** | `tests/test_draft_live.py` skips: no `ANTHROPIC_API_KEY` here |

## Files Changed
Created: `src/newsletter_machine/{frontmatter,checklist,prompts,grounding,writer,checks,critic,critique_report,drafting,validation}.py`, `src/newsletter_machine/prompts/{writer,critic}.md`, `voice/critic-checklist.yaml`, `tests/test_{frontmatter,checklist,prompts,grounding,writer,checks,critic,critique_report,drafting,cli_draft,draft_live}.py`, `tests/fixtures/sources/*.md`, the plan and this report.
Updated: `src/newsletter_machine/{voice,ingest,agent,config,cli}.py`, `tests/test_{voice,ingest,agent,config}.py`, `.gitignore`, `.env.example`, `README.md`, the PRD row.

## Deviations from Plan
- **Sub-agents compiled with `langchain.agents.create_agent`, wrapped as `CompiledSubAgent`**, not declarative `SubAgent` specs. Declarative specs get deepagents' default filesystem/todo middleware, which adds tools and prompt tokens a one-shot drafter does not need. The compiled form is directly runnable and still plugs into `create_deep_agent`.
- **New `grounding.py` and `validation.py`**: `Grounding` sits apart from `drafting.py` to avoid a circular import; `validation.py` came from review (validators were duplicated).
- **`extract_text` moved to `agent.py`** (shared by CLI and writer); `cli.extract_text` still imports it.
- **`make_chat_model` passes the Anthropic key only to `anthropic:` models** (review finding: a non-Anthropic `NM_CRITIC_MODEL` would otherwise receive it).
- **`.gitignore`**: `sources/` → `/sources/` (it was ignoring `tests/fixtures/sources/`); added `/drafts/`.
- **Checklist "Avoid" rules phrased as instructions** ("Do not use ...") because the writer sees them too (review finding). Varun should still review the wording.
- **Plan not archived; PRD Phase 3 left `in-progress`**, as in Phases 1 and 2: the live run and the blind "sounds like me" check are still open.

## Issues Encountered
- With `ToolStrategy`, a fake model that answers in plain text makes the agent re-prompt until the fake runs out. A real Anthropic model is forced to call the tool, and LangGraph's recursion limit bounds the retries. The "no structured output" guard is tested with a stub runnable.
- No Anthropic key in the sandbox, so no live draft.

## Review
Three `code-review high` rounds (10, 9, 10 findings). Fixed: 28. Skipped: 1 (requiring `ANTHROPIC_API_KEY` only when a model is Anthropic; the PRD is Anthropic-only and the key requirement is Phase 1's design). Highlights: prompt-injection wrapper escape (case/spacing variants, unescaped `</draft>`), Anthropic key sent to other providers, stale critique after `--overwrite`, non-atomic draft writes, several Markdown-measurement bugs (headings, wrapped bullets, link URLs, hyphenated words). No CRITICAL/HIGH issues open.

## Open Items
- [ ] Varun: review `src/newsletter_machine/prompts/writer.md`, `src/newsletter_machine/prompts/critic.md`, `voice/critic-checklist.yaml`.
- [ ] Live: `uv run pytest -m live tests/test_draft_live.py` and a real `draft` run on a week's sources.
- [ ] Blind check (PRD success signal), then archive the plan and mark Phase 3 `complete`.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_checklist.py` | 16 (+params) | real checklist cites real sections; field validation |
| `tests/test_checks.py` | 22 | patterns, word range, paragraphs, Markdown edge cases |
| `tests/test_critic.py` | 11 | prompt, task, merge, unknown/missing/duplicate verdicts |
| `tests/test_writer.py` | 14 | prompt grounding, source formatting/escaping/truncation, draft cleanup |
| `tests/test_cli_draft.py` | 14 | happy path, exit codes, overwrite, failure paths |
| `tests/test_drafting.py` | 8 | output paths, atomic write, deep-agent integration |
| `tests/test_critique_report.py` | 6 | ordering, quotes, sections |
| `tests/test_prompts.py`, `test_grounding.py`, `test_frontmatter.py` | 7, 5, 5 | loaders |
| `tests/test_ingest.py`, `test_config.py`, `test_voice.py`, `test_agent.py` | +8, +5, +4, +1 | read_sources, critic model, style guide, key routing |
| `tests/test_draft_live.py` | 1 (live) | writer then critic on the fixture |

## Next Steps
- [ ] Complete Open Items above
- [ ] Phase 4: lead agent passes `build_subagents(...).writer/.critic` to `create_deep_agent`, adds the critique → revise loop, and considers prompt caching for the ~24k-token writer system prompt.
