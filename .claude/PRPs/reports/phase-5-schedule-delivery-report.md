# Implementation Report: Phase 5 — Schedule & delivery

## Summary
`newsletter-machine weekly [--out-dir DIR]` runs the Phase 4 `issue` command unchanged for today's date (in `NM_TIMEZONE`, default `Asia/Kolkata`) on the last 7 days of Gmail links, keeps a copy of everything it prints, and puts one unread message in Varun's own Gmail inbox: the Markdown draft in the body with `.md`, `.critique.md` and `.notes.md` attached, or a "no links this week" notice, or "run failed" with the run log. Delivery uses Gmail `messages.insert` (scope `gmail.insert`), so nothing is ever sent. Scheduled runs authenticate headlessly from `NM_GMAIL_TOKEN_B64` (a token minted once by the new `gmail-auth` command) and never open a browser. An optional, off-by-default Substack step (`NM_SUBSTACK_DRAFT=true`) creates an unpublished draft with `python-substack==0.10.0`. The repo root is now a Managed Deep Agents project (`agent.py`, `instructions.md`, `identity.py`, `schedules/weekly_issue.py`, `[tool.mda]`) whose runner agent has one tool, `run_weekly_issue`, running the same code; the schedule is Fridays 07:00 Asia/Kolkata. Nothing was deployed, scheduled, sent or posted; the README runbook has the commands.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Large | Large |
| Confidence | Medium-high: MDA contract read from the 0.9.4 wheel, docs site unreachable | Met; the `mda` binary could not be run here, so `mda build` is unverified |
| Files Changed | ~22 | 31 (5 new src modules, 4 MDA project files, 8 new test files, config/docs/lock) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Config | Complete | `NM_GMAIL_TOKEN_B64`, `NM_TIMEZONE`, `NM_SUBSTACK_DRAFT` + `SUBSTACK_*`, `NM_RUNNER_MODEL`; voice dir falls back to the project root |
| 2 | Headless Gmail | Complete | scopes per use; token-in-env path; scope check; `profile_address`, `insert_message`; `authorize` |
| 3 | Delivery | Complete | `delivery.py`; labels `INBOX`, `UNREAD` only |
| 4 | Substack | Complete | `substack_draft.py`; `publish=False` explicit; lazy import |
| 5 | Weekly orchestration | Complete | `weekly.py`; output teed to the real streams and the message |
| 6 | CLI | Complete | `cli_weekly.py`: `weekly`, `gmail-auth` |
| 7 | Hosted tool + MDA project | Complete | `hosted.py` (once per day, concurrent calls refused); root project files |
| 8 | Docs | Complete | README runbook, `.env.example`, PRD row |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | `ruff check .`, `ruff format --check .`, `mypy src` (strict): zero issues |
| Unit Tests | Pass | 537 passed offline, 7 live deselected (81 new) |
| Coverage | Pass | 99% total; every new module 100% |
| Build | Pass | `uv build --wheel` |
| CLI smoke | Pass | `weekly`/`gmail-auth` without a token or client file exit 2 with a clear message; a malformed `NM_GMAIL_TOKEN_B64` exits 2 without echoing it |
| MDA build / deploy | **Not run** | out of scope (no deploy); running the `mda` binary was not permitted in this sandbox |

## Files Changed
Created: `src/newsletter_machine/{weekly,cli_weekly,hosted,delivery,substack_draft}.py`, `agent.py`, `identity.py`, `instructions.md`, `schedules/weekly_issue.py`, `tests/test_{config_weekly,gmail_headless,delivery,substack_draft,weekly,cli_weekly,hosted,mda_project}.py`, the plan and this report.
Updated: `src/newsletter_machine/{config,gmail,cli}.py`, `tests/test_gmail.py` (fake credentials gain `scopes`), `pyproject.toml` (+`python-substack==0.10.0`, +`tzdata`, `[tool.mda]`), `uv.lock`, `README.md`, `.env.example`, the PRD row.

## Deviations from Plan
- **`load_ingest_settings(ignore_token=True)`**: `gmail-auth` must work even when the old `NM_GMAIL_TOKEN_B64` is broken, since it is the fix.
- **Network vs config errors**: building the Gmail client splits `ConfigError` (exit 2) from everything else (exit 1), because timeouts are `OSError` and would otherwise read as configuration problems.
- **Runner model**: `NM_RUNNER_MODEL`, defaulting to `NM_FAST_MODEL`, so the hosted agent's model is configurable and cheap.

## Issues Encountered
- docs.langchain.com is blocked by the sandbox proxy. The MDA contract (project shape, `define_schedule`, `.env` forwarding, `[tool.mda]`) was read from the `managed-deepagents` 0.9.4 wheel's README and source instead; pricing came from web search.
- Running the `mda` CLI binary was not permitted, so `mda build .` has not been run on this project.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_config_weekly.py` | 16 (+params) | token decoding, time zone, Substack opt-in, voice-dir fallback |
| `tests/test_gmail_headless.py` | 7 | headless refresh, scope checks, consent, insert/profile |
| `tests/test_delivery.py` | 4 | message headers, body, attachments, labels |
| `tests/test_substack_draft.py` | 7 | title split, result, adapter never publishes |
| `tests/test_weekly.py` | 14 | drafted / no links / failed / crash / log tail / delivery and Substack failures |
| `tests/test_cli_weekly.py` | 9 | exit codes, temp folder cleanup, `gmail-auth` |
| `tests/test_hosted.py` | 8 | runner model, once per day, concurrency, tool |
| `tests/test_mda_project.py` | 7 | root project files with a stand-in `managed_deepagents` |

## Next Steps
- [ ] Varun: runbook steps 1 to 7 in the README (consent screen to production, `gmail-auth`, `.env`, local `weekly`, `mda deploy .`)
- [ ] Varun: decide on LangSmith Plus (cron) vs running `weekly` from another scheduler
- [ ] Varun: approve the inbox message format and, if he opts in, the Substack conversion
- [ ] PRD success signal: a draft appears on schedule without a manual trigger; then mark Phase 5 `complete`
