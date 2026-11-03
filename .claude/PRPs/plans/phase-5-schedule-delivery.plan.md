# Plan: Phase 5 — Schedule & delivery

## Summary
Make the Phase 4 `issue` run hands-off. A new `newsletter-machine weekly` command runs `issue` headlessly for today's date (in `NM_TIMEZONE`), captures its output, optionally creates a **Substack draft** (opt-in, off by default, never publishes), and delivers the result into Varun's **Gmail inbox** with `messages.insert` (no email is sent). The same code is exposed as a LangChain tool to a tiny Managed Deep Agents (MDA) project at the repo root (`agent.py`, `instructions.md`, `identity.py`, `schedules/weekly_issue.py`) so `mda deploy` hosts it and provisions a Friday 07:00 Asia/Kolkata cron. Gmail works without a browser through an OAuth token passed as `NM_GMAIL_TOKEN_B64`. Nothing is deployed, scheduled, sent or posted by this phase; the runbook holds the exact commands.

## User Story
As Varun, I want this week's reviewed draft to appear in my inbox every Friday morning without running anything, so that publishing weekly depends only on my edit, not on remembering to trigger the machine.

## Problem → Solution
`issue` needs a laptop, a browser-capable Gmail token and a manual trigger; the output lands in local files → a scheduled hosted run reads Gmail headlessly, runs the same pipeline, and puts the draft (plus critique and notes as attachments) in Varun's inbox; an optional Substack draft saves the copy-paste.

## Metadata
- **Complexity**: Large (new hosting surface, headless auth, two external integrations)
- **Source PRD**: `.claude/PRPs/prds/newsletter-content-machine.prd.md`
- **PRD Phase**: Phase 5 — Schedule & delivery
- **Estimated Files**: ~22 (6 new src modules, 4 MDA project files, 7 test files, config/docs)

---

## UX Design

### Before
```
Friday: open laptop -> uv run newsletter-machine issue --out drafts/2026-11-06.md
        (browser consent if the token lapsed) -> open the .md files
```

### After
```
Friday 07:00 IST (LangSmith cron) -> hosted agent calls run_weekly_issue
Inbox:  "Newsletter draft: Evals are the moat (2026-11-06)"
        body = run log + the Markdown draft; attachments: .md, .critique.md, .notes.md
        [optional] "Substack draft created: https://<pub>/publish/post/123" in the body
No links this week -> "Newsletter: no links this week (2026-11-06)"
Run failed         -> "Newsletter run failed (2026-11-06)" with the run log
```
Local equivalent: `uv run newsletter-machine weekly [--out-dir drafts]`.

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Terminal | `hello`, `ingest`, `draft`, `issue` | + `weekly [--out-dir DIR]`, + `gmail-auth` | exit 0/1/2 as elsewhere |
| Gmail | read-only link inbox | + one inserted message per run (INBOX, UNREAD), never the ingest label | scope `gmail.insert` cannot send |
| Hosting | none | MDA project at repo root; `schedules/weekly_issue.py` | edit the literals to change day/time/zone |
| Config | Phase 4 vars | + `NM_TIMEZONE`, `NM_GMAIL_TOKEN_B64`, `NM_SUBSTACK_DRAFT`, `SUBSTACK_*` | secrets via env only |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/cli_issue.py` | 80-110, 335-367 | `add_issue_parser` args, `issue_paths`, `run_issue(args) -> int` |
| P0 | `src/newsletter_machine/gmail.py` | 170-241 | `GoogleGmailClient`, `_save_token`, `_cached_credentials`, `build_gmail_client` |
| P0 | `src/newsletter_machine/config.py` | all | `IngestSettings`, `_load_env`, `_resolve_path`, `ConfigError` |
| P0 | `src/newsletter_machine/cli.py` | parser + `main` | subparser registration, dispatch |
| P1 | `src/newsletter_machine/cli_common.py` | all | `EXIT_*`, `configure_logging`, `read_links` (InboxError vs ConfigError) |
| P1 | `tests/test_gmail.py` | 160-290 | fake creds/flows, `_patch_build` |
| P1 | `tests/test_cli_issue.py` | 1-80 | env fixture, `_use_models`, `main([...])` |

## External Documentation

KEY_INSIGHT: MDA project shape (managed-deepagents 0.9.4 README, wheel inspected): root `agent.py` exporting `agent` (a `define_deep_agent(...)` or a factory `def agent(runtime)` whose `name=` is an inline literal), `instructions.md` (required system prompt), `identity.py` (`define_identity(auth=auth.langsmith_api_key())`), optional `schedules/<name>.py` exporting `schedule = define_schedule(cron=..., timezone=..., prompt=...)`. `mda deploy` builds, deploys, then reconciles code-defined schedules as LangSmith crons.
APPLIES_TO: Task 7. GOTCHA: schedule declarations must be static literals or top-level constants (no env vars, no calls), so the time/zone are configured by editing that file. Absent `timezone` means UTC.

KEY_INSIGHT: `mda deploy` loads the project `.env`, uses `LANGSMITH_API_KEY` itself and forwards the other variables to the deployment as secrets; a value only exported in the shell is not deployed. Build copies the project (minus `.env`, `.venv`, caches, `.claude`, git-ignored paths) and runs `pip install -e .` when `pyproject.toml` exists; `[tool.mda] python-version = "3.13"` pins the image's Python.
APPLIES_TO: Tasks 1, 7, 9. GOTCHA: `.secrets/` is git-ignored, so the hosted run has no token file: the Gmail token must arrive as an env var.

KEY_INSIGHT: Pricing/beta (web search; docs.langchain.com was not reachable from this sandbox): MDA is in public beta; LangSmith pricing lists cron scheduling and Managed Deep Agents under Plus ($39/seat/month) rather than the free Developer tier.
APPLIES_TO: PR Notes ("needs Varun's decision"). GOTCHA: the `weekly` command also runs anywhere with cron (laptop, CI) if he declines Plus.

KEY_INSIGHT: python-substack 0.10.0 `Api(email=, password=, cookies_string=, publication_url=)`; `create_draft_from_markdown(title=, markdown=, subtitle="", ..., publish=False)` creates an unpublished draft and returns `{"draft": {"id": ...}, ...}`.
APPLIES_TO: Task 5. GOTCHA: unofficial API, logs in on construction; cookie auth is more reliable than password (captcha). Pin `==0.10.0`.

KEY_INSIGHT: Google OAuth apps in "Testing" status issue refresh tokens that expire after 7 days; a weekly unattended job needs the consent screen set to "In production" (unverified is fine for the owner's own account).
APPLIES_TO: README/runbook.

KEY_INSIGHT: `users.messages.insert` (scope `gmail.insert`) adds a message to the mailbox like IMAP APPEND: no SMTP send, no filters. `users.getProfile` (readonly) gives the account address.
APPLIES_TO: Tasks 3, 4. GOTCHA: never put the ingest label (`NM_GMAIL_LABEL`) on the inserted message, or next week's ingest would read the draft's links.

---

## Patterns to Mirror

### RECORDS
// SOURCE: src/newsletter_machine/config.py:47-58
```python
@dataclass(frozen=True)
class IngestSettings:
    gmail_label: str
    ...
```

### CONFIG / ERRORS
// SOURCE: src/newsletter_machine/config.py:125-133
```python
def _positive_float(name: str, value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise ConfigError(f"{name} must be a number of seconds (got {value!r}).") from None
```

### CLI ERROR HANDLING
// SOURCE: src/newsletter_machine/cli_issue.py:337-350
```python
    except (ConfigError, ValueError, KeyError, OSError, ImportError) as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
```

### PROTOCOL + ADAPTER
// SOURCE: src/newsletter_machine/gmail.py:46-52, 170-176
```python
class GmailClient(Protocol):
    def label_id(self, name: str) -> str | None: ...

class GoogleGmailClient:
    """Thin adapter over the google-api-python-client Gmail resource."""
```

### LOGGING
// SOURCE: src/newsletter_machine/gmail.py:163
```python
    logger.info("Found %d messages under label %r", len(message_ids), label)
```

### TEST_STRUCTURE
// SOURCE: tests/test_cli_issue.py:22-30 (env fixture with `config.load_dotenv` patched), tests/test_gmail.py:193-200 (`_patch_build`).

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/newsletter_machine/config.py` | UPDATE | `gmail_token_info` on `IngestSettings`; `WeeklySettings`, `SubstackSettings`, `load_weekly_settings`; voice-dir fallback to the project root |
| `src/newsletter_machine/gmail.py` | UPDATE | scopes parameter, headless token, scope check, `profile_address`, `insert_message` |
| `src/newsletter_machine/delivery.py` | CREATE | build the inbox message (pure) and insert it |
| `src/newsletter_machine/substack_draft.py` | CREATE | opt-in draft-only Substack step behind a Protocol |
| `src/newsletter_machine/weekly.py` | CREATE | headless orchestration: run `issue`, capture output, Substack, deliver |
| `src/newsletter_machine/cli_weekly.py` | CREATE | `weekly` and `gmail-auth` commands |
| `src/newsletter_machine/hosted.py` | CREATE | `run_weekly_issue` tool (once per day per process), `runner_model()` |
| `src/newsletter_machine/cli.py` | UPDATE | register the new subcommands |
| `agent.py`, `instructions.md`, `identity.py`, `schedules/weekly_issue.py` | CREATE | MDA project files |
| `pyproject.toml` | UPDATE | `python-substack==0.10.0`, `tzdata`, `[tool.mda]` |
| `tests/test_config_weekly.py`, `test_gmail_headless.py`, `test_delivery.py`, `test_substack_draft.py`, `test_weekly.py`, `test_cli_weekly.py`, `test_hosted.py`, `test_mda_project.py` | CREATE | offline tests with fakes |
| `tests/test_gmail.py` | UPDATE | fake creds gain `scopes` |
| `README.md`, `.env.example`, PRD row | UPDATE | runbook, vars, links |

## NOT Building
- Deploying, registering the cron, minting tokens, creating a Substack draft or calling LangSmith/Gmail/Substack for real.
- Sending email (SMTP or `messages.send`), publishing on Substack, scheduling Substack posts.
- Slack `deliver_to`, MDA memory, sandbox, channels, evals, cost reports, a GitHub Actions fallback.
- Any change to the voice files or the writer/critic/editor/researcher prompts, or to the Phase 4 Markdown format.

---

## Step-by-Step Tasks

### Task 1: Config
- **ACTION**: extend `config.py`.
- **IMPLEMENT**: `IngestSettings.gmail_token_info: Mapping[str, str] | None = field(default=None, repr=False)` from `NM_GMAIL_TOKEN_B64` (base64 → JSON object with non-empty `refresh_token`, `client_id`, `client_secret`; else `ConfigError` naming the var but never its value). `SubstackSettings(publication_url, cookies, email, password)` (secrets `repr=False`). `WeeklySettings(timezone: ZoneInfo, substack: SubstackSettings | None)` from `NM_TIMEZONE` (default `Asia/Kolkata`, `ZoneInfoNotFoundError` → `ConfigError`) and `NM_SUBSTACK_DRAFT` (`true/false/1/0/yes/no`, default false; when true require `SUBSTACK_PUBLICATION_URL` (https) and either `SUBSTACK_COOKIES` or both `SUBSTACK_EMAIL`/`SUBSTACK_PASSWORD`). Default voice dir: when `NM_VOICE_DIR` is unset and `cwd/voice` is missing, use `<project root>/voice` (the hosted image's cwd is not the repo).
- **GOTCHA**: keep `load_settings` behaviour unchanged when `cwd/voice` exists.
- **VALIDATE**: `tests/test_config_weekly.py`.

### Task 2: Headless Gmail
- **ACTION**: update `gmail.py`.
- **IMPLEMENT**: `READ_SCOPES`, `DELIVERY_SCOPES = READ + gmail.insert`; `build_gmail_client(settings, scopes=READ_SCOPES)`. With `gmail_token_info`: `Credentials.from_authorized_user_info(info, None)`, require `has_scopes(scopes)`, refresh, never open a browser; any failure → `ConfigError` telling him to re-run `gmail-auth`. Cached-file path: load with `None` scopes, reuse only if it covers `scopes`, else consent again. `GoogleGmailClient.profile_address()`, `insert_message(raw: bytes, label_ids) -> str`.
- **GOTCHA**: a token minted for read-only lacks `gmail.insert`; detect before any model call.
- **VALIDATE**: `tests/test_gmail_headless.py`; existing `tests/test_gmail.py` still passes.

### Task 3: Delivery
- **ACTION**: create `delivery.py`.
- **IMPLEMENT**: `Mailbox` Protocol (`profile_address`, `insert_message`); `Delivery` record (subject, body, attachments: tuple[(name, text)]); `build_message(delivery, address) -> EmailMessage` with `From`/`To` = his address, `X-Newsletter-Machine: weekly`, text/plain UTF-8 body, `text/markdown` attachments; `deliver(mailbox, delivery) -> str` inserts with `INBOX`, `UNREAD` only.
- **VALIDATE**: `tests/test_delivery.py` parses the raw bytes back with `email`.

### Task 4: Substack (opt-in)
- **ACTION**: create `substack_draft.py`.
- **IMPLEMENT**: `split_title(markdown) -> (title, body)` (first `# ` line; body is the rest, unchanged); `SubstackClient` Protocol `create_draft(title, markdown) -> Mapping`; `create_substack_draft(client, draft, publication_url) -> SubstackResult(draft_id, edit_url)`; `make_substack_client(settings)` lazily imports `substack.Api` and calls `create_draft_from_markdown(..., publish=False)`.
- **GOTCHA**: never pass `publish=True`; Markdown is passed as-is (title moved to Substack's title field) and flagged for Varun's approval.
- **VALIDATE**: `tests/test_substack_draft.py` with a fake client and a fake `substack` module.

### Task 5: Weekly orchestration
- **ACTION**: create `weekly.py`.
- **IMPLEMENT**: `issue_date(now, tz)`; `WeeklyDeps(run_issue, mailbox, substack)` callables; `run_weekly(out_dir, now, settings, deps) -> WeeklyReport(status, exit_code, subject, delivered_id, substack_line)`. Steps: build args `Namespace(out=out_dir/f"{date}.md", angle=None, sources=None, links_file=None, since=None, overwrite=False)`; run with stdout/stderr teed into a buffer; read draft/critique/notes; status `drafted` / `no_links` (exit 0, no draft) / `failed`; Substack only for `drafted` and enabled (its failure is reported, not fatal); deliver.
- **VALIDATE**: `tests/test_weekly.py`.

### Task 6: CLI
- **ACTION**: create `cli_weekly.py`; register in `cli.py`.
- **IMPLEMENT**: `weekly [--out-dir DIR]` (default: temporary dir, removed afterwards). Gmail client with `DELIVERY_SCOPES` is built first (config errors exit 2 before any model call). Exit: issue's non-zero code, else 1 if delivery failed, else 0. `gmail-auth`: local browser consent for `DELIVERY_SCOPES`, saves the token file (0600), prints the next step without printing the token.
- **VALIDATE**: `tests/test_cli_weekly.py`.

### Task 7: Hosted tool + MDA project
- **ACTION**: create `hosted.py` and root `agent.py`, `instructions.md`, `identity.py`, `schedules/weekly_issue.py`; `[tool.mda] python-version = "3.13"`.
- **IMPLEMENT**: `OncePerDay` runner (lock; a second call on the same issue date returns the first result; a concurrent call is refused); `run_weekly_issue` `@tool` with no arguments; `runner_model()` from `NM_RUNNER_MODEL` or `NM_FAST_MODEL`. `agent.py` exports a factory `def agent(runtime)` returning `define_deep_agent(name="newsletter-machine", model=runner_model(), tools=[run_weekly_issue])`. Schedule: `cron="0 7 * * 5"`, `timezone="Asia/Kolkata"`, prompt "Run this week's newsletter issue."
- **GOTCHA**: `managed_deepagents` is not a project dependency (MDA vendors it); tests import the root files with a fake module in `sys.modules`.
- **VALIDATE**: `tests/test_hosted.py`, `tests/test_mda_project.py` (static literals via `ast`, valid 5-field cron on Friday, valid zone).

### Task 8: Docs
- **ACTION**: README "Weekly schedule" section (runbook), `.env.example`, PRD row links.

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| token b64 | valid / bad base64 / not JSON / missing refresh_token | info / ConfigError (no secret in message) | yes |
| timezone | unset / `Europe/London` / `Mars/Base` | Kolkata / London / ConfigError | yes |
| substack opt-in | unset, `true` without creds, cookies, email+password, `maybe` | None / ConfigError / settings / ConfigError | yes |
| headless gmail | info w/o insert scope; refresh error; good | ConfigError; ConfigError; client, no browser | yes |
| cached token scope | readonly file, delivery scopes | consent flow rerun | yes |
| message | draft + attachments | headers, body, 3 attachments, labels INBOX/UNREAD only | |
| weekly | drafted / no links / failure / substack on+fail | subjects, statuses, codes | yes |
| once per day | two calls same day; concurrent | one run; refusal | yes |
| MDA files | ast + fake module | literal name, Friday cron, zone | |

### Edge Cases Checklist
- [x] No links this week (notice delivered)
- [x] Pipeline failure (log delivered, non-zero exit)
- [x] Delivery failure (exit 1, reported)
- [x] Expired/insufficient token (config error before model calls)
- [x] Concurrent/duplicate tool calls

---

## Validation Commands
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest --cov=newsletter_machine --cov-report=term-missing
uv build --wheel
```
EXPECT: zero issues, all tests pass, coverage >= 80%.

### Manual Validation (Varun, not run here)
- [ ] `uv run newsletter-machine gmail-auth`, then `uv run newsletter-machine weekly --out-dir drafts` delivers to the inbox
- [ ] `mda deploy .`; first Friday run delivers

## Acceptance Criteria
- [ ] All tasks completed; validation passes; coverage >= 80%
- [ ] No real deploy/cron/email/Substack call made
- [ ] Runbook has the exact deploy, schedule and secret commands

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cron needs LangSmith Plus | H | M | `weekly` runs from any cron; flagged for decision |
| Google testing-mode refresh token expires in 7 days | H | H | runbook: publish consent screen "In production" |
| Run longer than the platform run timeout | L-M | M | one research pass, capped revisions; note in PR |
| YouTube blocks cloud IPs | H | L | existing fallback; noted |
| MDA beta contract changes | M | M | pin `managed-deepagents==0.9.4` in the runbook |

## Notes
- Delivery target is Gmail `messages.insert`, not a Gmail draft: a draft needs `gmail.compose`, which can also send mail; `gmail.insert` cannot send and the message lands unread in the inbox where Varun already works.
- The hosted runner is a cheap model with one tool; the Phase 4 editor still runs exactly as in `issue`.
