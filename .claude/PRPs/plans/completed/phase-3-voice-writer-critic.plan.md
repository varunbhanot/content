# Plan: Phase 3 — Voice writer & critic

## Summary
Build two sub-agents that make drafts sound like Varun: a **writer** that turns ingested source files (Phase 2 output) plus an optional angle into a Markdown newsletter draft, grounded in all 13 hand-written posts and the approved style guide; and a **voice critic** that checks a draft against an editable checklist (`voice/critic-checklist.yaml`) derived from the style guide and returns structured pass/fail feedback with quotes and fixes. Prompts live in versioned Markdown files. A manual `newsletter-machine draft` command runs writer then critic once. Lead-agent orchestration is Phase 4.

## User Story
As Varun, I want to point one command at this week's source files and get back a draft in my voice plus a critique that flags where it drifts from my style guide, so that I spend my editing time on opinions instead of de-AI-ing prose.

## Problem → Solution
Pasting material into Claude gives generic "AI" prose that Varun rewrites by hand → `newsletter-machine draft --sources sources/this-week --angle "..." --out drafts/issue.md` writes `issue.md` (draft with a Sources list) and `issue.critique.md` (per-item pass/fail, quotes, suggested fixes).

## Metadata
- **Complexity**: Large (new subsystem, LLM structured output, editable data file, CLI)
- **Source PRD**: `.claude/PRPs/prds/newsletter-content-machine.prd.md`
- **PRD Phase**: Phase 3 — Voice writer & critic
- **Estimated Files**: ~20 (7 src, 2 prompt files, 1 checklist, 8 tests + fixtures, docs)

---

## UX Design

### Before
```
┌────────────────────────────────────────────────────┐
│ sources/this-week/*.md exist (Phase 2)             │
│ To draft: paste them into Claude, get generic      │
│ prose, rewrite into own voice by hand.             │
└────────────────────────────────────────────────────┘
```

### After
```
┌──────────────────────────────────────────────────────────────────┐
│ $ uv run newsletter-machine draft --sources sources/this-week \  │
│       --angle "evals are the moat" --out drafts/2026-11-06.md     │
│ Using 4 of 5 sources (1 failed source skipped)                    │
│ Wrote drafts/2026-11-06.md (870 words)                            │
│ Critique: 17 passed, 3 failed -> drafts/2026-11-06.critique.md    │
└──────────────────────────────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Terminal | `hello`, `ingest` | + `draft --sources DIR [--angle TEXT] --out FILE [--overwrite]` | exit 0 ok, 1 model/write failure, 2 config/usage |
| Config | `NM_WRITER_MODEL`, `NM_FAST_MODEL` | + `NM_CRITIC_MODEL` (defaults to `NM_WRITER_MODEL`) | no new model ids |
| Voice dir | samples + style guide | + `critic-checklist.yaml` (Varun edits) | each item cites a style-guide H2 |
| Prompts | `HELLO_SYSTEM_PROMPT` in code | `src/newsletter_machine/prompts/{writer,critic}.md` with `version:` front-matter | `string.Template` placeholders |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/config.py` | 31-98 | frozen `Settings`, `load_settings(env, repo_root=)`, `_require_provider_prefix` |
| P0 | `src/newsletter_machine/voice.py` | all | front-matter parsing, `load_voice_corpus`, `ValueError` naming the file |
| P0 | `src/newsletter_machine/agent.py` | all | `init_chat_model(name, api_key=settings.anthropic_api_key)`; model override for tests |
| P0 | `src/newsletter_machine/cli.py` | all | subparsers, exit codes, `_configure_logging` after `.env`, `extract_text` |
| P0 | `src/newsletter_machine/ingest.py` | 75-90, 115-130 | `render_source` (the format to read back), `check_out_dir` overwrite pattern |
| P0 | `voice/style-guide.md` | all | the source of every checklist item; H2 sections are citation targets |
| P1 | `tests/conftest.py`, `tests/test_agent.py`, `tests/test_cli.py` | all | `make_voice_dir`, `_ToolFriendlyFake`, `.env` isolation, live-test pattern |
| P1 | `voice/README.md` | all | hand = voice ground truth; ai-assisted = topics only + AI-isms for the critic |

## External Documentation

Verified against installed packages (deepagents 0.7.32, langchain >=1.4) on 2026-11-03 with a probe script.

| Topic | Source | Key Takeaway |
|---|---|---|
| Sub-agents | `deepagents/middleware/subagents.py:84-300` | `SubAgent` (declarative) or `CompiledSubAgent{name, description, runnable}`; parent reads `structured_response` (JSON) else last AI text |
| Agent runnable | `langchain.agents.create_agent(model, tools=[], system_prompt=, response_format=, name=)` | Same entrypoint deepagents uses for sub-agents; result dict has `messages` and `structured_response` |
| Structured output | `langchain.agents.structured_output.ToolStrategy(Model)` | Works with a fake chat model that emits a tool call named after the pydantic class |

```
KEY_INSIGHT: A create_agent runnable wrapped as CompiledSubAgent is directly invokable AND accepted by create_deep_agent(subagents=[...]).
APPLIES_TO: writer.py, critic.py, Phase 4 handoff
GOTCHA: Declarative SubAgent specs get deepagents' default middleware (filesystem/todo tools). For a one-shot draft that is noise and cost; compile ourselves with tools=[].

KEY_INSIGHT: Use ToolStrategy explicitly, not AutoStrategy.
APPLIES_TO: critic.py
GOTCHA: AutoStrategy picks provider-native output for Anthropic but tool strategy for fakes; explicit ToolStrategy keeps tests and production on one path.

KEY_INSIGHT: LLMs miss em dashes and miscount words.
APPLIES_TO: critic checks
GOTCHA: Mechanical checks (patterns, word range, paragraph length) run in code; only judgement items go to the model.
```

---

## Patterns to Mirror

### RECORDS
// SOURCE: src/newsletter_machine/voice.py:17-25
```python
@dataclass(frozen=True)
class VoiceSample:
    title: str
    date: date
    ...
```

### ERROR_HANDLING (config / data files)
// SOURCE: src/newsletter_machine/voice.py:28-44, config.py:63-67
```python
raise ValueError(f"{path}: missing front-matter")
raise ConfigError(f"{name} must look like 'provider:model' (got {value!r}).")
```

### MODEL INIT
// SOURCE: src/newsletter_machine/agent.py:34-36
```python
chosen = model or settings.writer_model
if isinstance(chosen, str):
    chosen = init_chat_model(chosen, api_key=settings.anthropic_api_key)
```

### CLI / EXIT CODES
// SOURCE: src/newsletter_machine/cli.py:73-86
```python
try:
    settings = load_settings()
except ConfigError as exc:
    print(f"Config error: {exc}", file=sys.stderr)
    return EXIT_CONFIG
_configure_logging()
try: ...
except Exception as exc:  # network/API failures surface as many types
    logger.debug("Agent run failed", exc_info=True)
```

### TEST_STRUCTURE
// SOURCE: tests/test_agent.py:18-23, tests/test_cli.py:11-14
```python
class _ToolFriendlyFake(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ToolFriendlyFake":
        return self

@pytest.fixture(autouse=True)
def _ignore_real_dotenv(monkeypatch): monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/frontmatter.py` | CREATE | `split_front_matter` shared by voice, prompts, source files (moved from voice.py) |
| `src/newsletter_machine/voice.py` | UPDATE | use `frontmatter`; add `load_style_guide`, `style_guide_sections` |
| `src/newsletter_machine/checklist.py` | CREATE | `ChecklistItem`, `load_checklist` with validation against style-guide sections |
| `src/newsletter_machine/prompts.py` + `prompts/{writer,critic}.md` | CREATE | versioned prompt templates, `load_prompt`, `render` |
| `src/newsletter_machine/ingest.py` | UPDATE | `read_sources(dir)` = inverse of `render_source` |
| `src/newsletter_machine/writer.py` | CREATE | grounding → writer system prompt, sources block, `build_writer` (CompiledSubAgent), `writer_task`, `run_writer` |
| `src/newsletter_machine/checks.py` | CREATE | code-run checks: patterns, word range, paragraph length, draft stats |
| `src/newsletter_machine/critic.py` | CREATE | `Critique` schema, `build_critic`, `critic_task`, `run_critic` (merge code + model results) |
| `src/newsletter_machine/critique_report.py` | CREATE | render critique to Markdown |
| `src/newsletter_machine/drafting.py` | CREATE | `load_grounding`, `draft_issue` (writer then critic once), output paths |
| `src/newsletter_machine/agent.py` | UPDATE | `make_chat_model` helper reused by drafting |
| `src/newsletter_machine/config.py` | UPDATE | `critic_model` (`NM_CRITIC_MODEL`, defaults to writer model) |
| `src/newsletter_machine/cli.py` | UPDATE | `draft` subcommand |
| `voice/critic-checklist.yaml` | CREATE | editable checklist, each item cites a style-guide section |
| `tests/test_*.py` (+ `tests/fixtures/sources/`) | CREATE/UPDATE | offline tests with fake models; one live test |
| `README.md`, `.env.example`, PRD row | UPDATE | docs |

## NOT Building

- Lead "editor" agent, planning, research sub-agent, critique→rewrite loop (Phase 4).
- Automatic revision based on the critique (Phase 4 loop); this phase runs writer then critic once.
- Prompt caching, cost tracking, evals (deferred per PRD).
- Any edit to `voice/style-guide.md` or `voice/samples/` (suggestions go in the PR).
- Feeding ai-assisted posts to the writer (they are not his voice).

---

## Step-by-Step Tasks

### Task 1: `frontmatter.py` + voice grounding loaders
- **ACTION**: Move `_split_front_matter` to `frontmatter.split_front_matter(path, text)`; voice.py imports it. Add `load_style_guide(voice_dir) -> str` (body without front-matter; `ValueError` if missing) and `style_guide_sections(text) -> tuple[str, ...]` (H2 titles).
- **MIRROR**: RECORDS, ERROR_HANDLING.
- **GOTCHA**: Existing voice tests must keep passing unchanged.
- **VALIDATE**: `tests/test_frontmatter.py`, `tests/test_voice.py` (real style guide has the 7 sections).

### Task 2: Checklist data file + loader
- **ACTION**: `voice/critic-checklist.yaml` with `version` and `items`. Item fields: `id` (kebab), `section` (style-guide H2), `rule`, `check` (what the critic looks for), `severity` (`must`|`should`), optional mechanical fields `patterns` (regex list) + `allowed` (hits allowed, default 0), `word_range: [min, max]`, `max_paragraph_chars` (+ `allowed`).
- **IMPLEMENT**: `checklist.py`: frozen `ChecklistItem`; `load_checklist(path, sections)` validates unique ids, known section, known keys, regexes compile, ranges sane; errors name file and item id. `is_mechanical` property.
- **GOTCHA**: YAML booleans/ints: validate types explicitly.
- **VALIDATE**: real checklist loads and every item's section is in the real style guide.

### Task 3: Prompt files + loader
- **ACTION**: `prompts/writer.md`, `prompts/critic.md` with front-matter `version: 1`, body as `string.Template` (`$style_guide`, `$samples`, `$checklist`).
- **IMPLEMENT**: `prompts.py`: `Prompt(name, version, template)`, `load_prompt(name)` via `importlib.resources`, `render(prompt, **values)` uses `substitute` (missing key fails fast).
- **GOTCHA**: hatch wheel must include the `.md` files (it includes all package files by default); literal `$` in prompts must be `$$`.

### Task 4: Read sources back (`ingest.read_sources`)
- **ACTION**: Parse `NN-*.md` files written by `render_source` into `SourceDoc`s (strip the `# title` line). Validate kind/status values. Return sorted tuple. `ValueError` on bad file or empty dir.
- **VALIDATE**: round-trip `render_source` → `read_sources` equals original.

### Task 5: Writer
- **IMPLEMENT**: `writer.py`:
  - `writer_system_prompt(grounding) -> str`: renders writer.md with style guide, all hand samples (title, date, body) and the checklist rules.
  - `format_sources(docs) -> str`: usable docs only (status != failed), each in `<source index= url= title= kind= status=>` with note; text capped at `MAX_SOURCE_CHARS` with a truncation marker. Sources are untrusted data.
  - `writer_task(docs, angle) -> str`.
  - `build_writer(model, system_prompt) -> CompiledSubAgent` (create_agent, tools=[]).
  - `run_writer(subagent, task) -> str`: invoke, take last AI message text, strip a wrapping ```markdown fence; `ValueError` on empty.

### Task 6: Mechanical checks
- **IMPLEMENT**: `checks.py`: `body_without_sources(draft)`, `count_words`, `paragraphs` (blank-line blocks; headings, code, tables skipped; list lines counted singly), `run_mechanical(item, draft) -> CheckResult`.

### Task 7: Critic
- **IMPLEMENT**: `critic.py`: pydantic `ItemVerdict{item_id, passed, quotes, fix}`, `CriticOutput{verdicts, summary}` (model schema); frozen dataclass `CheckResult{item, status: pass|fail|not-checked, quotes, fix, by: code|critic}` and `Critique{results, summary}`. `critic_system_prompt(grounding)` renders the judgement items only. `critic_task(draft, docs)`. `build_critic(model, system_prompt)` with `ToolStrategy(CriticOutput)`. `run_critic(subagent, task, checklist, draft)` merges code results + model verdicts in checklist order; unknown ids dropped with a warning, missing → `not-checked`.

### Task 8: Report + drafting service
- **IMPLEMENT**: `critique_report.render_critique(critique, meta)` Markdown: counts, failures first with quotes/fixes, then passes; prompt/checklist versions. `drafting.py`: `Grounding` dataclass + `load_grounding(voice_dir)`; `draft_paths(out)`; `check_draft_out(out, overwrite)`; `draft_issue(docs, angle, grounding, writer_model, critic_model) -> DraftResult`.

### Task 9: Config + CLI
- **IMPLEMENT**: `Settings.critic_model` (`NM_CRITIC_MODEL`, default = writer model). `agent.make_chat_model(name, api_key)`. CLI `draft`: load settings (2), load sources/grounding/out check (2), run writer (1), write draft, run critic (1, draft kept), write critique; summary lines.

### Task 10: Docs
- README "Draft" section, `.env.example` `NM_CRITIC_MODEL`, PRD row link.

---

## Testing Strategy

| Test | Input | Expected |
|---|---|---|
| checklist loads real file | `voice/critic-checklist.yaml` | items; every section in style guide |
| checklist rejects unknown section / dup id / bad regex / unknown key | tmp YAML | `ValueError` naming file + id |
| prompt render missing key | `render(p)` | `KeyError` |
| read_sources round-trip | `render_source(doc)` | equal doc |
| format_sources skips failed, truncates long | docs | no failed doc; marker present |
| run_writer strips fence / rejects empty | fake model | text / ValueError |
| em dash / banned word / word range / paragraph | drafts | fail with quote |
| run_critic merge | fake tool-call output | code + model results, missing → not-checked, unknown dropped |
| CLI draft happy path | fake builders | exit 0, two files |
| CLI no sources / no key / out exists | — | exit 2 |
| CLI critic fails | — | exit 1, draft kept |
| live draft | fixture sources | non-empty draft + critique (`-m live`) |

### Edge Cases Checklist
- [x] Empty sources dir / all failed
- [x] Very long transcript (cap)
- [x] Model returns no text / wrapping code fence
- [x] Model omits or invents checklist ids
- [x] Network failure (exit 1)
- [x] Existing output files (`--overwrite`)

---

## Validation Commands
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest --cov=newsletter_machine --cov-report=term-missing
uv run pytest -m live tests/test_draft_live.py   # needs ANTHROPIC_API_KEY
```
EXPECT: zero lint/type errors; all offline tests pass; coverage >= 80%.

### Manual Validation
- [ ] `newsletter-machine draft --sources tests/fixtures/sources --out /tmp/d.md` with a real key
- [ ] Blind check: Varun reads the draft mixed with a hand post excerpt and rates "sounds like me"

## Acceptance Criteria
- [ ] Writer + critic built as sub-agent runnables usable by a Phase 4 lead agent
- [ ] Checklist is an editable data file; each item cites a style-guide section (validated)
- [ ] Prompts in versioned files
- [ ] `draft` CLI writes draft + critique
- [ ] All validation commands pass

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Draft still generic | M | H | Full hand corpus in prompt; checklist given to writer; critic flags drift; Varun edits prompts |
| Prompt injection from source text | M | M | Sources wrapped as data with explicit instruction; agents have no tools |
| Token cost (13 samples ≈ 17k tokens + sources) | L | M | Per-source cap; samples once per call; prompt caching noted for Phase 4 |
| Critic hallucinates quotes | M | L | Mechanical items in code; report labels which items were checked by code |

## Notes
- Critic model defaults to the writer model (PRD: Sonnet for drafting/critique).
- The critic receives the sources so it can flag invented statistics (style guide, Avoid).
