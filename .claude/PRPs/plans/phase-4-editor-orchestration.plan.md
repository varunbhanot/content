# Plan: Phase 4 — Editor orchestration (MVP)

## Summary
One manual command, `newsletter-machine issue`, turns a week of links into a reviewed Markdown draft. It ingests the links (Phase 2 code, or reuses an `ingest` folder), then runs a lead **editor** deep agent (`deepagents.create_deep_agent`) that plans the issue with its built-in todo tool and delegates through `task` to three sub-agents: a **researcher** (fast model, per-source sourced notes), the Phase 3 **writer** and the Phase 3 **voice critic**, with at most `NM_MAX_REVISIONS` critique → revise loops. Code, not the model, owns the artifacts: sub-agents read trusted inputs from Python and write versioned files into the agent's virtual filesystem; after the run, code picks the latest draft, normalises its `## Sources` list against the ingested URLs, guarantees a critique for that exact version, and writes `issue.md`, `issue.critique.md` and `issue.notes.md`.

## User Story
As Varun, I want one command that takes this week's links and gives me a sourced draft in my voice that has already been critiqued and revised once, so that my ≤30 minutes go on opinions and polish, not on running steps by hand.

## Problem → Solution
Phase 3 needs two commands (`ingest`, then `draft`), runs writer and critic exactly once, and never acts on the critique → `newsletter-machine issue --out drafts/2026-11-06.md [--since 7d | --links-file F | --sources DIR] [--angle TEXT] [--overwrite]` runs ingest → plan → research → draft → critique → (revise → critique) and writes the final draft plus critique and editor notes.

## Metadata
- **Complexity**: Large (new orchestration subsystem, deep-agent wiring, CLI)
- **Source PRD**: `.claude/PRPs/prds/newsletter-content-machine.prd.md`
- **PRD Phase**: Phase 4 — Editor orchestration (MVP)
- **Estimated Files**: ~20 (8 src modules, 2 prompt files, 8 test files, docs)

---

## UX Design

### Before
```
$ uv run newsletter-machine ingest --since 7d --out sources/this-week
$ uv run newsletter-machine draft --sources sources/this-week --out drafts/issue.md
  (writer once, critic once; Varun applies the critique himself)
```

### After
```
$ uv run newsletter-machine issue --since 7d --angle "evals are the moat" --out drafts/2026-11-06.md
Found 5 links in label 'newsletter' from me since 2026-10-27
Wrote 5 files to drafts/2026-11-06.sources (4 ok, 0 fallback, 1 failed)
Using 4 of 5 sources (1 failed source skipped)
Editor: research done, draft v1 (3 failed), draft v2 (1 failed)
Wrote drafts/2026-11-06.md (870 words, final draft v2)
Critique: 17 passed, 1 failed, 1 not checked -> drafts/2026-11-06.critique.md
Notes -> drafts/2026-11-06.notes.md
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Terminal | `hello`, `ingest`, `draft` | + `issue --out FILE [--since S \| --links-file F \| --sources DIR] [--angle] [--overwrite]` | exit 0 ok, 1 model/write failure, 2 config/usage |
| Outputs | `issue.md`, `issue.critique.md` | + `issue.notes.md`, + `issue.sources/` (when ingesting) | draft format unchanged: `# Title` … `## Sources` |
| Config | writer/critic/fast models | + `NM_EDITOR_MODEL` (blank = writer model), `NM_MAX_REVISIONS` (0–3, default 1) | no new model ids |
| Prompts | `writer.md`, `critic.md` | + `editor.md`, `researcher.md` (versioned) | writer/critic prompts untouched |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/cli.py` | all | subparsers, `_prepare_*` (exit 2) vs model failures (exit 1), `_collect_links`, `_save_draft`, `_critique_draft` |
| P0 | `src/newsletter_machine/drafting.py` | all | `build_subagents`, `OutputPaths`, `check_outputs`, `write_atomic` |
| P0 | `src/newsletter_machine/writer.py` | all | `writer_task`, `format_sources`, `neutralise_tags`, `clean_draft`, `build_writer` |
| P0 | `src/newsletter_machine/critic.py` | all | `critic_task`, `run_critic`, `Critique`, `build_critic` (ToolStrategy) |
| P0 | `src/newsletter_machine/config.py` | all | `Settings`, `_require_provider_prefix`, `ConfigError` |
| P1 | `src/newsletter_machine/ingest.py` | 75-90, 115-173 | `render_source`, `check_out_dir`, `write_sources`, `read_sources` |
| P1 | `src/newsletter_machine/critique_report.py` | all | `ReportMeta`, `render_critique` |
| P1 | `tests/test_cli_draft.py` | 1-60 | FakeModel, `_use_models` monkeypatching `cli.make_chat_model` |
| P2 | `.venv/.../deepagents/middleware/subagents.py` | 747-860 | how `task` builds sub-agent state and returns results |

## External Documentation

KEY_INSIGHT: `task` passes a CompiledSubAgent the parent state minus `messages/todos/structured_response/...`, with `messages=[HumanMessage(description)]`. Non-excluded keys the sub-agent returns (e.g. `files`) are merged into the parent state; only its last AI text (or `structured_response` as JSON) goes back as the ToolMessage.
APPLIES_TO: writer/critic/researcher wrappers read `state["files"]` and return `{"messages": [...], "files": {...}}`.
GOTCHA: verified with a probe (fake lead + `RunnableLambda` sub-agent): seeded `/sources/01.md` reached the sub-agent and its `/drafts/v1.md` came back in `result["files"]`. File values are `deepagents.backends.utils.create_file_data(text)` dicts (`{"content": str, ...}`).

KEY_INSIGHT: `create_deep_agent` auto-adds a `general-purpose` sub-agent (full tools, lead's model) unless a sub-agent with that name is supplied.
APPLIES_TO: editor wiring. GOTCHA: supply a `general-purpose` CompiledSubAgent that refuses, so the lead cannot spend tokens outside the pipeline.

KEY_INSIGHT: `FilesystemPermission(operations=["write"], paths=[...], mode="deny")` blocks the lead's `write_file`/`edit_file`; state updates from sub-agents are not tool calls and are unaffected.
APPLIES_TO: lead may write `/plan.md` but never `/sources/**`, `/drafts/**`, `/critiques/**`, `/research/**`.

KEY_INSIGHT: The Phase 3 critic uses `ToolStrategy(CriticOutput)`. Branch `fix/critic-structured-output` (e87dbdf, not on main) switches to the bare schema because newer Claude models reject the forced `tool_choice`. Phase 4 calls `run_critic` unchanged, so live runs on such models depend on that fix; offline tests do not.

---

## Patterns to Mirror

### RECORDS
// SOURCE: src/newsletter_machine/drafting.py:24-27, 48-55
```python
@dataclass(frozen=True)
class OutputPaths:
    draft: Path
    critique: Path
```

### ERROR_HANDLING (CLI)
// SOURCE: src/newsletter_machine/cli.py:247-261
```python
    try:
        job = _prepare_draft(args)
    except (ConfigError, ValueError, KeyError, OSError, ImportError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    ...
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Writer run failed", exc_info=True)
        print(f"Writer failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
```

### CONFIG
// SOURCE: src/newsletter_machine/config.py:78-83
```python
    critic_model = _require_provider_prefix(
        "NM_CRITIC_MODEL", env.get("NM_CRITIC_MODEL", "").strip() or writer_model
    )
```

### LOGGING
// SOURCE: src/newsletter_machine/writer.py:114
```python
    logger.info("Writer drafting from a %d-character task", len(task))
```

### SUB-AGENT
// SOURCE: src/newsletter_machine/writer.py:94-97
```python
def build_writer(model: BaseChatModel, system_prompt: str) -> CompiledSubAgent:
    runnable = create_agent(model, tools=[], system_prompt=system_prompt, name=WRITER_NAME)
    return CompiledSubAgent(name=WRITER_NAME, description=WRITER_DESCRIPTION, runnable=runnable)
```

### TEST_STRUCTURE
// SOURCE: tests/test_cli_draft.py:20-50
```python
class FakeModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeModel":
        return self

def _use_models(monkeypatch, writer, critic):
    ...
    monkeypatch.setattr(cli, "make_chat_model", _make)
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/workspace.py` | CREATE | Virtual-filesystem layout: paths, seeding, versioned drafts/critiques, reading text |
| `src/newsletter_machine/researcher.py` | CREATE | Researcher: per-source sourced notes with the fast model |
| `src/newsletter_machine/editor_subagents.py` | CREATE | State-aware wrappers around researcher, writer, critic; revision task; refusing `general-purpose`; attempt caps |
| `src/newsletter_machine/editor.py` | CREATE | Editor prompt, `build_editor`, `run_editor` → `EditorRun` |
| `src/newsletter_machine/issue_output.py` | CREATE | Normalise the `## Sources` list; render `issue.notes.md` |
| `src/newsletter_machine/cli_common.py` | CREATE | `configure_logging`, exit codes (shared by `cli.py` and `cli_issue.py` without a cycle) |
| `src/newsletter_machine/cli_issue.py` | CREATE | The `issue` command |
| `src/newsletter_machine/prompts/{editor,researcher}.md` | CREATE | Versioned prompts |
| `src/newsletter_machine/config.py` | UPDATE | `editor_model`, `max_revisions` |
| `src/newsletter_machine/cli.py` | UPDATE | register `issue`, use `cli_common` |
| `src/newsletter_machine/drafting.py` | UPDATE | docstring (Phase 4 now exists); `OutputPaths` gains nothing (notes path built in `cli_issue`) |
| `tests/test_{workspace,researcher,editor_subagents,editor,issue_output,cli_issue,issue_live}.py`, `tests/test_config.py` | CREATE/UPDATE | TDD |
| `README.md`, `.env.example`, PRD row | UPDATE | Docs |

## NOT Building

- Scheduling/cron, Managed Deep Agents deploy, Substack drafts (Phase 5)
- Evals of draft quality (deferred by owner)
- Changes to `voice/style-guide.md`, `voice/samples/`, or the substance of `writer.md` / `critic.md`
- Prompt caching, cost tracking, subject-line options, web search beyond the ingested links
- Async/parallel sub-agents

---

## Step-by-Step Tasks

### Task 1: Config
- **ACTION**: add `editor_model: str` and `max_revisions: int` to `Settings`.
- **IMPLEMENT**: `NM_EDITOR_MODEL` blank → writer model (same as critic). `NM_MAX_REVISIONS` integer 0..3, default `1`; anything else → `ConfigError` naming the variable.
- **MIRROR**: CONFIG. **VALIDATE**: `tests/test_config.py` new cases.

### Task 2: Workspace (`workspace.py`)
- **IMPLEMENT**: constants `SOURCES_DIR="/sources"`, `NOTES_PATH="/research/notes.md"`, `PLAN_PATH="/plan.md"`, `DRAFTS_DIR="/drafts"`, `CRITIQUES_DIR="/critiques"`, `BRIEFS_DIR="/briefs"`, `ERRORS_DIR="/errors"`; `seed_files(docs, paths)` → `{"/sources/01-x.md": file_data(render_source(doc))}`; `file_text(files, path) -> str | None`; `versioned(dir, n, ext)`; `latest_version(files, dir, ext) -> int` (0 if none); `count_files(files, dir)`; `text_file(text)` = `create_file_data`.
- **GOTCHA**: file values may lack `content` or hold a list (older format) — treat non-str content as `"\n".join(lines)`; never trust the lead to have kept them.

### Task 3: Researcher (`researcher.py`, `prompts/researcher.md`)
- **IMPLEMENT**: `build_researcher(model, prompt)` = tool-less `create_agent`; `research_task(doc, index, angle, brief)` wraps one source with `format_sources`-style tags (reuse `writer._attrs`-equivalent via `format_sources((doc,))`? no: index must stay global → build `<source index=...>` with `neutralise_tags`); `research_notes(runnable, docs, angle, brief) -> ResearchNotes(text, failures)` where each usable source gets a `## [n] Title` section with its URL and the model's bullet notes; one failing source is recorded, not fatal.
- **GOTCHA**: source and model text are untrusted; notes later go to the writer inside `<research_notes>` with `neutralise_tags` applied.

### Task 4: Sub-agent wrappers (`editor_subagents.py`)
- **IMPLEMENT**: `EditorInputs(docs, angle, checklist, max_revisions, draft_name)` frozen. Wrappers are `CompiledSubAgent`s over `RunnableLambda(fn)` where `fn(state) -> {"messages": [AIMessage(summary)], "files": {...}}`:
  - `researcher`: once per run (refuse if notes exist or researcher error recorded); writes `/research/notes.md`.
  - `writer`: attempts = drafts + writer errors; refuse when attempts ≥ `1 + max_revisions`. First draft: `writer_task(docs, angle)` + brief + notes. Revision: also `<draft>` (previous, neutralised) + failed items from the latest critique summary. Writes `/drafts/vN.md`, `/briefs/vN.md`; returns "Draft vN saved (W words)".
  - `voice-critic`: critiques the latest draft once (refuse if `/critiques/vN.md` or a critic error for vN exists); writes `/critiques/vN.md` (rendered via `render_critique`) and `/critiques/vN.json` (counts + failed ids + fixes); returns a compact summary listing failed items so the lead can decide.
  - `general-purpose`: always refuses.
  - Each wrapper catches exceptions, writes `/errors/<agent>-<n>.md` and returns "<agent> failed: …" (the lead and the caps stop loops).
- **GOTCHA**: inputs (docs, angle, checklist) come from the closure, never from state, so the lead cannot change what the writer sees except via its brief.

### Task 5: Editor (`editor.py`, `prompts/editor.md`)
- **IMPLEMENT**: `editor_system_prompt(prompt, max_revisions)`; `build_editor(model, subagents)` with `permissions` denying writes outside `/plan.md`; `editor_task(docs, angle)` (source list: index, title, url, note — not full text; full text is in `/sources`); `run_editor(editor, task, files) -> EditorRun(files, summary)` with `recursion_limit` constant.
- **GOTCHA**: invoke config `{"recursion_limit": EDITOR_RECURSION_LIMIT}`.

### Task 6: Output (`issue_output.py`)
- **IMPLEMENT**: `normalise_sources(draft, docs) -> SourcesFix(draft, dropped)` — strip from the `## Sources` heading on; keep links whose `normalize_url` matches a usable source (titled from the ingested title, writer order, deduped); if none → list every usable source. `render_notes(meta, files, docs, summary)` → Markdown: run log per version, failed/skipped sources, dropped links, editor summary, last brief, research notes.

### Task 7: CLI (`cli_common.py`, `cli_issue.py`, `cli.py`)
- **IMPLEMENT**: prepare (exit 2): settings, `output_paths(out)` + notes path, `check_outputs`, source mode (`--sources` XOR ingest), ingest out dir `<stem>.sources` checked with `check_out_dir`, grounding, models (`make_chat_model` for editor/writer/critic/fast). Ingest (Gmail exit 1 on runtime failure). Editor run (exit 1 "Editor failed"). Finalise: latest draft (none → exit 1 with recorded writer error), normalise sources, save draft, ensure critique for the final version (direct `run_critic` fallback), write critique + notes.
- **GOTCHA**: `--sources` with `--since`/`--links-file` → argparse mutually exclusive group.

### Task 8: Docs
- README "One command: issue", configuration rows, `.env.example`, PRD row link.

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| config editor model | blank / set / bad prefix | writer model / value / ConfigError | yes |
| config max revisions | "0", "3", "4", "x", "true" | 0, 3, error, error, error | yes |
| workspace latest_version | `/drafts/v1.md`, `/drafts/v2.md`, junk | 2 | yes |
| researcher notes | 2 usable + 1 failed doc | 2 sections, failed skipped | yes |
| researcher one source raises | fake model error | failure recorded, others kept | yes |
| writer wrapper first draft | state files | `/drafts/v1.md` written, message | |
| writer wrapper revision | v1 + critique json | task contains previous draft + failed ids | |
| writer cap | max_revisions=0, v1 exists | refusal, no model call | yes |
| critic wrapper | v1 | `/critiques/v1.md` + json | |
| critic once per version | critique exists | refusal | yes |
| wrapper error | runnable raises | `/errors/...`, failure message | yes |
| general-purpose | any | refusal | |
| normalise sources | known/unknown/duplicate links; no section | dropped list, fallback list | yes |
| editor end-to-end (fake lead) | scripted tool calls research→write→critique→write→critique | v2 final, files present | |
| lead denied write to /drafts | write_file tool call | denied | yes |
| cli issue happy path (links file + fakes) | | draft, critique, notes, sources dir; exit 0 | |
| cli issue --sources | fixture dir | no ingest | |
| cli exit 2 cases | existing out, bad flags, no key | before model calls | yes |
| cli lead skips critic | | fallback critic runs | yes |
| cli no draft | lead never writes | exit 1 | yes |
| cli critic fallback fails | | exit 1, draft kept | yes |

### Edge Cases Checklist
- [x] Empty input (no links → exit 0 "nothing to draft"; all sources failed → exit 2)
- [x] Maximum size input (writer caps per-source chars, Phase 3)
- [x] Invalid types (config, front-matter)
- [ ] Concurrent access (N/A, single-user CLI)
- [x] Network failure (wrapped in sub-agents; editor failure exit 1)
- [x] Permission denied (write failures exit 1; lead write deny)

---

## Validation Commands

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest
uv run pytest --cov=newsletter_machine --cov-report=term-missing   # >= 80% (project runs ~99%)
uv run pytest -m live tests/test_issue_live.py                       # needs ANTHROPIC_API_KEY
```

### Manual Validation
- [ ] `uv run newsletter-machine issue --links-file week.txt --out drafts/test.md` with a real key
- [ ] Gmail run: `uv run newsletter-machine issue --since 7d --out drafts/<date>.md`
- [ ] Varun times his edit of the draft (PRD success signal)

---

## Acceptance Criteria
- [ ] All tasks completed; validation commands pass; coverage ≥ 80%
- [ ] Writer/critic prompts unchanged; voice files untouched
- [ ] One command produces draft + sources + critique + notes offline with fakes

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Lead loops or wanders | M | cost | code caps per sub-agent, refusing general-purpose, recursion limit |
| Critic structured output rejected by newer models | M | no critique | depends on `fix/critic-structured-output`; draft is still saved (exit 1) |
| Lead skips a step | M | missing critique | code-side fallback critic on the final version |
| Writer cites a non-ingested URL | M | wrong source | `normalise_sources` drops it and lists it in notes |
| Cost: lead reads full sources | L-M | budget | editor task lists sources; prompt says read only if needed |

## Notes
- Draft format (needs Varun's approval): unchanged from Phase 3 — `# Title`, body with ≤3 `[VARUN: ...]` markers, `## Sources` list of `- [Title](url)` limited to ingested sources. Sidecars: `.critique.md`, `.notes.md`, `.sources/`.
- Sub-agents read inputs from Python, not from the lead's messages, so the lead never retypes 24k-character sources into `task` descriptions (cheaper, no transcription errors).
