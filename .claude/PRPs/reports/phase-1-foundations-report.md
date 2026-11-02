# Implementation Report: Phase 1 — Foundations

## Summary
Python/uv project `newsletter_machine` with validated env config, voice-corpus loader, a read-only `deepagents` hello agent on Anthropic, a `newsletter-machine hello` CLI, offline tests, README, and a **draft** `voice/style-guide.md`. Two acceptance items remain open (see Open Items).

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium | Medium |
| Confidence | 8/10 | Met; both flagged unknowns resolved (see Notes) |
| Files Changed | ~15 | 17 created/updated (+ `uv.lock`) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Project scaffold | Complete | `uv sync` ok; import check ok |
| 2 | Config | Complete | |
| 3 | Voice loader | Complete | Real corpus: 13 hand + 10 ai-assisted |
| 4 | Hello agent | Complete | `FilesystemPermission` write-deny supported and used |
| 5 | CLI | Complete | Also exits 1 on agent/network failure |
| 6 | Tests (written first, RED then GREEN) | Complete | 22 offline + 1 live (deselected) |
| 7 | Style guide | Drafted | **Awaiting Varun's approval (human gate)** |
| 8 | README | Complete | |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | ruff check, ruff format --check, mypy strict: zero issues |
| Unit Tests | Pass | 22 passed, no network |
| Coverage | Pass | 96% (voice.py 88%, rest 100%) |
| Build | Pass | `uv sync` / package import |
| Live smoke | **Not run** | No `ANTHROPIC_API_KEY` in this environment |
| Edge cases | Pass (offline) | blank/missing key, bad model string, missing corpus, bad front-matter, era mismatch |
| CLI no-key | Pass | prints config error, exit 2 |

## Files Changed
`pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore`, `.env.example`, `README.md` (updated), `src/newsletter_machine/{__init__,config,voice,agent,cli}.py`, `tests/{conftest,test_config,test_voice,test_agent,test_cli}.py`, `voice/style-guide.md`, PRD row link.

## Deviations from Plan
- **Em dashes added to Avoid by author decision.** The counts (47 hand vs 6 AI-assisted) show they are not an AI tell, but Varun chose to avoid them in new drafts anyway.
- **Formulaic opener flagged.** "Here's the uncomfortable truth" opens only 2 of 13 hand posts; the guide now says not to reuse it by default.
- **"quietly" softened to "allow rarely".** It appears twice in hand posts (8 in AI-assisted), so an outright ban would be wrong.
- **Plan not archived and PRD left `in-progress`.** The plan makes style-guide approval a completion gate and the live test is unrun.
- `build_hello_agent` returns `CompiledStateGraph` with a `type: ignore[type-arg]` (generic params not worth spelling out).
- Added CLI exit code 1 for agent failure (plan's edge-case checklist asks for non-zero on network failure).

## Issues Encountered
- `ruff format .` reformatted a Python code block inside the plan markdown; reverted by hand. Future runs should target `src tests`.
- Fake chat model needed the `bind_tools` override the plan anticipated.

## Open Items
- [x] Varun approved `voice/style-guide.md`.
- [ ] (Waived by author at completion; still worth doing) Run `uv run pytest -m live` and `uv run newsletter-machine hello` with a real key; confirm quotes come from hand posts and `git status` shows no changes under `voice/`.
- [x] Plan archived to `.claude/PRPs/plans/completed/`; PRD Phase 1 marked `complete`.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_config.py` | 8 | validation, defaults, relative path, dotenv path, key redaction |
| `tests/test_voice.py` | 7 | parsing, filter, sort, errors, real corpus counts |
| `tests/test_agent.py` | 3 (1 live) | graph builds, invoke with fake model, live read-only check |
| `tests/test_cli.py` | 5 | exit codes, output, text-block flattening |

## Next Steps
- [ ] Complete Open Items above
- [ ] `/code-review`, then `/prp-commit` and `/prp-pr`
