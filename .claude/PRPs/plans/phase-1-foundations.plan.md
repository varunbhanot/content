# Plan: Phase 1 — Foundations

## Summary
Stand up a Python project for the newsletter content machine: a `uv`-managed package, validated env-based config, a voice-corpus loader, and a minimal `deepagents` agent on Anthropic that can read the hand-written voice samples and answer from them. Also produce `voice/style-guide.md`, distilled from the hand-written posts and approved by Varun, which Phases 3–4 will inject into the writer and critic.

## User Story
As Varun (sole newsletter author), I want a runnable deep-agent skeleton wired to my Anthropic key and grounded in my hand-written posts, plus a written style guide of my voice, so that later phases can build research, writing and critique on a working, tested base.

## Problem → Solution
Repo contains only a README, a PRD and the voice corpus → repo contains an installable package with a `newsletter-machine hello` CLI that runs a deep agent over `voice/samples/hand/`, unit tests passing offline, and an approved style guide.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `.claude/PRPs/prds/newsletter-content-machine.prd.md`
- **PRD Phase**: Phase 1 — Foundations
- **Estimated Files**: 15

---

## UX Design

### Before
```
┌──────────────────────────────────────────┐
│ Varun pastes notes into Claude chat      │
│ → generic draft → rewrites by hand       │
│ No code, no agent, no style guide        │
└──────────────────────────────────────────┘
```

### After
```
┌──────────────────────────────────────────┐
│ $ uv run newsletter-machine hello        │
│ → deep agent lists voice/samples/hand,   │
│   reads posts, replies with 3 voice      │
│   traits + quotes                        │
│ voice/style-guide.md exists & approved   │
└──────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Terminal | nothing | `newsletter-machine hello [--question ...]` | Smoke test that key, model and corpus all work |
| Config | none | `.env` (from `.env.example`) | Fails fast with a clear message if key missing |
| Voice | 23 raw posts | + `voice/style-guide.md` | Human-approved; source of truth for Phase 3 |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/prds/newsletter-content-machine.prd.md` | Technical Approach, Phase 1 | Scope and decisions |
| P0 | `voice/README.md` | all | Hand vs AI-assisted split; only `hand/` is voice ground truth |
| P0 | `voice/samples/hand/*.md` | all | Input for the style guide (13 posts) |
| P1 | `voice/samples/ai-assisted/*.md` | skim | AI-isms to list as "avoid" in the style guide |
| P1 | `.claude/rules/ecc/common/coding-style.md`, `testing.md` | all | Repo rules: immutability, small files, fail-fast validation, 80% coverage |

## External Documentation

Verified against installed packages on 2026-11-02: `deepagents 0.7.32`, `langchain 1.4.7`, `langchain-anthropic 1.7.7`, `langgraph 1.2.19`, Python 3.13, `uv 0.11.32`.

| Topic | Source | Key Takeaway |
|---|---|---|
| `create_deep_agent` | `deepagents/graph.py` (installed); docs.langchain.com/oss/python/deepagents | `create_deep_agent(model=None, tools=None, *, system_prompt=None, middleware=(), subagents=None, skills=None, memory=None, permissions=None, backend=None, interrupt_on=None, response_format=None, ..., name=None)`. Returns a LangGraph `CompiledStateGraph`; call `.invoke({"messages": [...]})`. |
| Model selection | `graph.py` docstring | Pass a `provider:model` string (e.g. `"anthropic:claude-sonnet-5-5"`) or a `BaseChatModel`. **Always pass explicitly**; the docstring warns against relying on `model=None`. |
| Filesystem | `deepagents/backends/filesystem.py:91-164` | `FilesystemBackend(root_dir=..., virtual_mode=True, max_file_size_mb=10)`. `virtual_mode=True` blocks `..`/`~` traversal and keeps paths inside `root_dir`. Default tools: `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `write_todos`, `task`. |
| Memory | `graph.py` docstring | `memory=["/path/AGENTS.md"]` loads files into the system prompt at startup. Use for the style guide in Phase 3. |
| Subagents | `deepagents/middleware/subagents.py:84` | `SubAgent` TypedDict: `name`, `description` required; `tools`, `system_prompt`, `model` optional. Not used in Phase 1. |

```
KEY_INSIGHT: FilesystemBackend(virtual_mode=True) rooted at voice/ gives the agent read access to the corpus without exposing .env or the rest of the repo.
APPLIES_TO: Task 4 (agent.py)
GOTCHA: Root it at <repo>/voice, NOT the repo root. The docstring warns agents can read secrets/.env under root_dir.

KEY_INSIGHT: Default deepagents tools include write_file/edit_file.
APPLIES_TO: Task 4
GOTCHA: The hello agent could modify voice files. Inspect `deepagents.FilesystemPermission` (deepagents/middleware/filesystem.py) and pass read-only rules via `permissions=` if supported; always also hash-check the corpus in the live test.

KEY_INSIGHT: Current model IDs (2026-11-02): claude-sonnet-5-5 (drafting), claude-haiku-5-5 (cheap summarisation).
APPLIES_TO: Task 2 (config defaults)
GOTCHA: Keep IDs in config/env only, never in agent code.
```

---

## Patterns to Mirror

**Greenfield repo: there is no existing code to mirror.** The conventions below are set by this phase and become the patterns later phases mirror. They follow `.claude/rules/ecc/common/coding-style.md`.

### NAMING_CONVENTION
- Package `newsletter_machine` under `src/`; modules are nouns (`config.py`, `voice.py`, `agent.py`, `cli.py`).
- `snake_case` functions, `PascalCase` classes, `UPPER_SNAKE` constants.
- Factories start with `build_` (`build_hello_agent`); loaders with `load_` (`load_settings`, `load_voice_corpus`).

### ERROR_HANDLING
- One package exception: `class ConfigError(Exception)` in `config.py`.
- Validate at the boundary (env, filesystem) and raise with an actionable message, e.g. `ConfigError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")`.
- CLI catches `ConfigError`, prints to stderr, exits 2. Never print secrets.

### LOGGING_PATTERN
- stdlib `logging`, one logger per module: `logger = logging.getLogger(__name__)`.
- CLI configures `logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))`.
- No `print` outside `cli.py`; never log the API key.

### DATA / IMMUTABILITY PATTERN
- Config and corpus entries are `@dataclass(frozen=True)`; collections returned as `tuple`.

### TEST_STRUCTURE
- `pytest`, files `tests/test_<module>.py`, Arrange-Act-Assert, descriptive names (`test_load_settings_raises_when_api_key_missing`).
- `monkeypatch` for env, `tmp_path` for filesystem.
- LLM tests marked `@pytest.mark.live`, excluded by default, run with `-m live` when `ANTHROPIC_API_KEY` is set.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `pyproject.toml` | CREATE | uv project, deps, console script, pytest/ruff/mypy config |
| `uv.lock` | CREATE | Reproducible installs (generated) |
| `.python-version` | CREATE | Pin 3.13 |
| `.gitignore` | CREATE | `.venv/`, `.env`, `__pycache__/`, `.pytest_cache/`, `.coverage` |
| `.env.example` | CREATE | Documents env vars (no real values) |
| `src/newsletter_machine/__init__.py` | CREATE | Package marker + `__version__` |
| `src/newsletter_machine/config.py` | CREATE | `Settings`, `ConfigError`, `load_settings()` |
| `src/newsletter_machine/voice.py` | CREATE | `VoiceSample`, `load_voice_corpus()` |
| `src/newsletter_machine/agent.py` | CREATE | `build_hello_agent()` |
| `src/newsletter_machine/cli.py` | CREATE | `newsletter-machine hello` entry point |
| `tests/conftest.py` | CREATE | Shared fixtures (tmp corpus builder) |
| `tests/test_config.py` | CREATE | Config validation tests |
| `tests/test_voice.py` | CREATE | Corpus loader tests |
| `tests/test_agent.py` | CREATE | Agent construction (offline) + live smoke |
| `tests/test_cli.py` | CREATE | CLI exit codes |
| `voice/style-guide.md` | CREATE | Distilled voice, approved by Varun |
| `README.md` | UPDATE | Setup + run instructions |

## NOT Building

- Inbox, article/YouTube ingestion (Phase 2)
- Writer / critic subagents and their prompts (Phase 3)
- Editor orchestration and drafts (Phase 4)
- Managed Deep Agents deploy, scheduling, Substack (Phase 5)
- Evals and LangSmith tracing setup (deferred; LangSmith env vars optional only)

---

## Step-by-Step Tasks

### Task 1: Project scaffold
- **ACTION**: Create `pyproject.toml`, `.python-version`, `.gitignore`, `.env.example`, `src/newsletter_machine/__init__.py`; run `uv sync`.
- **IMPLEMENT**:
  - `requires-python = ">=3.13"`, build backend `hatchling`, `src/` layout.
  - Dependencies: `deepagents>=0.7.32,<0.8`, `langchain-anthropic>=1.7`, `python-dotenv>=1.0`, `pyyaml>=6`.
  - Dev group: `pytest`, `pytest-cov`, `ruff`, `mypy`, `types-PyYAML`.
  - `[project.scripts] newsletter-machine = "newsletter_machine.cli:main"`.
  - `[tool.pytest.ini_options] markers = ["live: calls the real Anthropic API"]`, `addopts = "-m 'not live'"`, `testpaths = ["tests"]`.
  - `.env.example`: `ANTHROPIC_API_KEY=`, `NM_WRITER_MODEL=anthropic:claude-sonnet-5-5`, `NM_FAST_MODEL=anthropic:claude-haiku-5-5`, `NM_VOICE_DIR=voice`, `LOG_LEVEL=INFO`, optional `LANGSMITH_API_KEY=`, `LANGSMITH_TRACING=false`.
- **MIRROR**: NAMING_CONVENTION
- **IMPORTS**: n/a
- **GOTCHA**: Pin `deepagents` below 0.8; the API moves fast. Commit `uv.lock`. Never commit `.env`.
- **VALIDATE**: `uv sync` succeeds; `uv run python -c "import deepagents, newsletter_machine"` exits 0.

### Task 2: Config (`config.py`)
- **ACTION**: Load and validate settings from env.
- **IMPLEMENT**:
  - `@dataclass(frozen=True) class Settings: anthropic_api_key: str = field(repr=False); writer_model: str; fast_model: str; voice_dir: Path`.
  - `def load_settings(env: Mapping[str, str] | None = None, *, repo_root: Path | None = None) -> Settings`: when `env is None`, call `load_dotenv()` then use `os.environ`. Raise `ConfigError` if the key is missing/blank, a model string lacks a `provider:` prefix, or `voice_dir/samples/hand` does not exist. Resolve relative `NM_VOICE_DIR` against `repo_root` (default `Path.cwd()`).
- **MIRROR**: ERROR_HANDLING, DATA / IMMUTABILITY PATTERN
- **IMPORTS**: `os`, `dataclasses.dataclass, field`, `pathlib.Path`, `collections.abc.Mapping`, `dotenv.load_dotenv`
- **GOTCHA**: Injectable `env` keeps tests hermetic; tests must never read the developer's real `.env`.
- **VALIDATE**: `uv run pytest tests/test_config.py`

### Task 3: Voice corpus loader (`voice.py`)
- **ACTION**: Parse `voice/samples/{hand,ai-assisted}/*.md` front-matter + body.
- **IMPLEMENT**:
  - `Era = Literal["hand", "ai-assisted"]`.
  - `@dataclass(frozen=True) class VoiceSample: title: str; date: date; url: str; words: int | None; era: Era; path: Path; body: str`.
  - `def load_voice_corpus(voice_dir: Path, era: Era | None = None) -> tuple[VoiceSample, ...]`, sorted by date. Split front-matter between the first two `---` lines, parse with `yaml.safe_load`.
  - Raise `ValueError` naming the file if front-matter is missing or `era` disagrees with its folder.
- **MIRROR**: DATA / IMMUTABILITY PATTERN, ERROR_HANDLING
- **IMPORTS**: `yaml`, `datetime.date`, `pathlib.Path`, `typing.Literal`
- **GOTCHA**: `yaml.safe_load` already returns `date` values as `datetime.date`. The generator replaced `"` with `'` inside titles, so values stay valid YAML; still test against one real file.
- **VALIDATE**: `uv run pytest tests/test_voice.py`; real corpus returns 13 hand + 10 ai-assisted.

### Task 4: Hello agent (`agent.py`)
- **ACTION**: Build a deep agent that can read the voice corpus.
- **IMPLEMENT**:
  ```python
  from deepagents import create_deep_agent
  from deepagents.backends.filesystem import FilesystemBackend

  HELLO_SYSTEM_PROMPT = (
      "You are a read-only assistant for Varun's newsletter. "
      "Files under /samples/hand are his hand-written posts (his true voice); "
      "/samples/ai-assisted are AI-assisted and NOT his voice. "
      "Never write or edit files."
  )

  def build_hello_agent(settings: Settings, *, model: str | BaseChatModel | None = None):
      backend = FilesystemBackend(root_dir=settings.voice_dir, virtual_mode=True)
      return create_deep_agent(
          model=model or settings.writer_model,
          system_prompt=HELLO_SYSTEM_PROMPT,
          backend=backend,
          name="hello",
      )
  ```
  If `FilesystemPermission` supports read-only rules, also pass `permissions=[...]` denying `write_file`/`edit_file`.
- **MIRROR**: NAMING_CONVENTION, LOGGING_PATTERN
- **IMPORTS**: as above; `langchain_core.language_models.BaseChatModel`
- **GOTCHA**: Root at `voice/`, never the repo root. Model comes from `Settings`. `langchain-anthropic` reads `ANTHROPIC_API_KEY` from the environment, which `load_dotenv()` populates.
- **VALIDATE**: offline test compiles the graph with a fake model; live test answers citing a hand-written post.

### Task 5: CLI (`cli.py`)
- **ACTION**: `newsletter-machine hello [--question TEXT]`.
- **IMPLEMENT**: `argparse` with a `hello` subcommand. Default question: *"List the hand-written posts, read two of them, and name three concrete traits of Varun's voice with a short quote for each."* Invoke `agent.invoke({"messages": [{"role": "user", "content": q}]})` and print the final message text. Catch `ConfigError` → stderr, exit 2. `main(argv: list[str] | None = None) -> int`.
- **MIRROR**: ERROR_HANDLING, LOGGING_PATTERN
- **IMPORTS**: `argparse`, `logging`, `os`, `sys`
- **GOTCHA**: Anthropic message `.content` may be a list of blocks; join the `text` blocks when it is not a `str`.
- **VALIDATE**: no key → clear error, exit 2; with key → three traits with quotes.

### Task 6: Tests (write first)
- **ACTION**: Write tests for Tasks 2–5 before implementing them (RED → GREEN).
- **IMPLEMENT**: see Testing Strategy. Offline agent test uses `langchain_core.language_models.fake_chat_models.GenericFakeChatModel`.
- **MIRROR**: TEST_STRUCTURE
- **GOTCHA**: If the fake model's `bind_tools` raises `NotImplementedError`, subclass it and return `self` from `bind_tools`. Only assert that the graph compiles; behaviour is covered by the live test.
- **VALIDATE**: `uv run pytest --cov=newsletter_machine --cov-report=term-missing` ≥ 80%.

### Task 7: Style guide (`voice/style-guide.md`)
- **ACTION**: Distil Varun's voice from the 13 hand-written posts only.
- **IMPLEMENT**: Sections, each rule backed by a real quote and source file:
  - *Who's talking*: first person, practitioner building agentic AI in production at Deutsche Telekom.
  - *Openings*: e.g. "Welcome back…", "Here's the uncomfortable truth:".
  - *Rhythm*: short declarative lines, one-line paragraphs for emphasis ("This works for demos. It breaks in production.").
  - *Devices*: everyday analogies (appetizer vs main course; "a junior on their first day"), before/after examples, numbered "Step N" walkthroughs, pull-quotes.
  - *Structure & length*: one topic, ~550–1,400 words, H2 sections, diagrams.
  - *Closings*: derived from the posts' endings.
  - *Avoid*: AI-isms seen in `ai-assisted/` (e.g. "buried", "quietly, without fanfare", formal "we argued" recaps, dense long paragraphs, heavy em-dash chains).
- **MIRROR**: n/a (content)
- **GOTCHA**: Never derive voice rules from `ai-assisted/`; use it only for the Avoid list. Keep it ≤ ~1,500 words since it will be injected into prompts.
- **VALIDATE**: Varun reads and approves or edits it. Human gate: Phase 1 is not complete without approval.

### Task 8: README
- **ACTION**: Replace the one-liner with setup (`uv sync`, `cp .env.example .env`), run (`uv run newsletter-machine hello`), test commands, and links to the PRD and `voice/README.md`.
- **VALIDATE**: fresh clone → follow README → hello runs.

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_load_settings_returns_settings_with_defaults` | env with key only, tmp voice dir | sonnet/haiku defaults | no |
| `test_load_settings_raises_when_api_key_missing` | env without key | `ConfigError` mentioning `.env.example` | yes |
| `test_load_settings_raises_when_api_key_blank` | `ANTHROPIC_API_KEY="  "` | `ConfigError` | yes |
| `test_load_settings_rejects_model_without_provider_prefix` | `NM_WRITER_MODEL=claude-sonnet-5-5` | `ConfigError` | yes |
| `test_load_settings_raises_when_hand_samples_dir_missing` | voice dir without `samples/hand` | `ConfigError` | yes |
| `test_settings_repr_hides_api_key` | key `sk-ant-secret` | repr lacks `secret` | yes |
| `test_load_voice_corpus_parses_front_matter` | tmp file with front-matter | fields correct | no |
| `test_load_voice_corpus_filters_by_era` | mixed tmp corpus, `era="hand"` | only hand samples | no |
| `test_load_voice_corpus_sorted_by_date` | out-of-order files | ascending dates | no |
| `test_load_voice_corpus_raises_on_missing_front_matter` | file without `---` | `ValueError` with filename | yes |
| `test_load_voice_corpus_raises_on_era_folder_mismatch` | `era: hand` inside `ai-assisted/` | `ValueError` | yes |
| `test_real_corpus_has_13_hand_and_10_ai_assisted` | repo `voice/` | counts match | no |
| `test_build_hello_agent_compiles_with_fake_model` | fake model, tmp voice dir | object has `invoke` | no |
| `test_cli_hello_exits_2_without_api_key` | empty env | exit 2, message on stderr | yes |
| `test_hello_agent_live_cites_hand_post` (`live`) | real key | answer names ≥1 hand-post title; corpus hash unchanged | live |

### Edge Cases Checklist
- [x] Empty input (blank key, empty corpus dir)
- [ ] Maximum size input (n/a; `max_file_size_mb=10` covers posts)
- [x] Invalid types (model string without provider)
- [ ] Concurrent access (n/a)
- [x] Network failure (live only; CLI logs the error and exits non-zero)
- [x] Permission denied (agent must not write the corpus; hash check)

---

## Validation Commands

### Static Analysis
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```
EXPECT: Zero errors

### Unit Tests
```bash
uv run pytest
```
EXPECT: All pass, no network

### Coverage
```bash
uv run pytest --cov=newsletter_machine --cov-report=term-missing
```
EXPECT: ≥ 80%

### Live Smoke (requires ANTHROPIC_API_KEY)
```bash
uv run pytest -m live
```
```bash
uv run newsletter-machine hello
```
EXPECT: Three voice traits quoting hand-written posts; `git status` shows no changes under `voice/`

### Manual Validation
- [ ] `uv run newsletter-machine hello` without `.env` prints the ConfigError and exits 2
- [ ] With key, output quotes hand-written posts (not ai-assisted)
- [ ] Varun approves `voice/style-guide.md`

---

## Acceptance Criteria
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing, coverage ≥ 80%
- [ ] No type or lint errors
- [ ] Style guide approved by Varun
- [ ] Hello agent runs on Anthropic and never modifies `voice/`

## Completion Checklist
- [ ] Conventions in "Patterns to Mirror" applied consistently (baseline for later phases)
- [ ] `ConfigError` used for all config failures
- [ ] Module loggers, no stray prints
- [ ] Frozen dataclasses / tuples
- [ ] No hardcoded model IDs or keys outside config and `.env.example`
- [ ] README updated
- [ ] No Phase 2+ scope

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `deepagents` API changes | M | M | Pin `<0.8`; commit `uv.lock` |
| Fake chat model lacks `bind_tools` | M | L | Subclass returning `self` (Task 6) |
| Agent writes into `voice/` | L | M | Read-only permissions if supported + prompt + hash test |
| Style guide drifts toward AI-assisted voice | M | H | Cite only hand-written sources; human approval gate |
| Model ID rejected by API | L | M | IDs configurable via env; live test catches it |

## Notes
- Confidence in single-pass implementation: 8/10. Remaining unknowns are the exact `FilesystemPermission` shape and fake-model tool binding; both have fallbacks above.
- The style guide is the highest-leverage deliverable here: it is what fixes "generic AI writing".
