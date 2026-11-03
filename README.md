# content

Deep-agent content machine for the *Beyond the AI Demo* newsletter. Phase 1 gives a runnable
[`deepagents`](https://docs.langchain.com/oss/python/deepagents) skeleton on Anthropic, grounded in the
hand-written voice corpus. Phase 2 turns the week's emailed links into clean source text. Phase 3
drafts an issue in Varun's voice from those sources and runs a voice critic over it. Phase 4
runs the whole week in one command; Phase 5 runs it on a weekly schedule and puts the result in
your Gmail inbox.

- Product plan: [`.claude/PRPs/prds/newsletter-content-machine.prd.md`](.claude/PRPs/prds/newsletter-content-machine.prd.md)
- Voice corpus and split rule: [`voice/README.md`](voice/README.md)
- Voice style guide (approved): [`voice/style-guide.md`](voice/style-guide.md)

## Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

```bash
cp .env.example .env   # then set ANTHROPIC_API_KEY
```

## Run

Smoke test: the agent lists the hand-written posts, reads two, and names three voice traits with quotes.

```bash
uv run newsletter-machine hello
```

```bash
uv run newsletter-machine hello --question "Which post is about evaluation?"
```

The agent is rooted at `voice/` and has write operations denied, so it cannot modify the corpus or read `.env`.
A missing key exits with code 2 and a message pointing at `.env.example`.

## Ingest the week's links

Email links (with an optional one-line thought) to `varunbhanot+newsletter@gmail.com`; a Gmail
filter puts them under a label. `ingest` reads that label and writes one Markdown file per source
(front-matter: `url`, `title`, `kind`, `status`, `note`, `detail`).

```bash
uv run newsletter-machine ingest --since 7d --out sources/this-week
```

```bash
uv run newsletter-machine ingest --links-file links.txt --out sources/this-week   # no Gmail; 'URL [note]' per line
```

- Articles: fetched with `httpx`, main text extracted with `trafilatura`.
- YouTube: transcript via `youtube-transcript-api`; if YouTube refuses (no captions, IP blocked),
  the file is `status: fallback` with the video description and a "Transcript unavailable" notice.
- Local/private addresses (localhost, 10.x, 192.168.x, 169.254.x, ...) are never fetched.
- A source that cannot be fetched is still written, as `status: failed` with the reason in `detail`.
- `--since` takes `7d`, `24h`, `2w` or `YYYY-MM-DD`. `--overwrite` replaces Markdown already in `--out`.
- Exit codes: 0 done (per-source failures are listed, not fatal), 1 Gmail/write failure, 2 config/usage error.
  `ingest` does not need `ANTHROPIC_API_KEY`.

### Gmail setup (once)

1. In Google Cloud Console, create a project, enable the **Gmail API**, configure the OAuth consent
   screen (External, add yourself as a test user), and create an **OAuth client ID** of type
   *Desktop app*. Download its JSON to `.secrets/gmail-client.json` (git-ignored).
2. In Gmail, create a filter `to:varunbhanot+newsletter@gmail.com` → *Apply the label* `newsletter`
   (or set `NM_GMAIL_LABEL` to your label name).
3. Links are only read from mail sent by `NM_GMAIL_ALLOWED_SENDERS` (default: your own account), so
   strangers emailing the plus-address cannot inject URLs. If you share from another account, add it.
4. First `ingest` run opens a browser for consent (read-only scope). The token is cached at
   `.secrets/gmail-token.json` with `0600` permissions and refreshed automatically.

## Draft in Varun's voice

`draft` runs the **writer** sub-agent on a folder written by `ingest`, then the **voice critic** once.

```bash
uv run newsletter-machine draft --sources sources/this-week --angle "evals are the moat" --out drafts/issue.md
```

- Writes `drafts/issue.md` (the draft, with a `## Sources` list and up to three `[VARUN: ...]`
  markers where your own experience should go) and `drafts/issue.critique.md` (pass/fail per
  checklist item, with quotes and suggested fixes; failures first).
- `--angle` is optional; without it the writer picks the strongest single topic in the sources.
  Sources that failed to ingest are skipped. `--overwrite` replaces an existing draft/critique.
- The writer is grounded in the style guide and all hand-written posts (`voice/samples/hand/`);
  AI-assisted posts are never shown to it.
- Exit codes: 0 done, 1 model or write failure (if only the critic fails, the draft is kept),
  2 config/usage error (no key, no usable sources, output exists, broken voice files).

What shapes the voice (edit these, they are versioned in git):

| File | What it does |
|---|---|
| [`src/newsletter_machine/prompts/writer.md`](src/newsletter_machine/prompts/writer.md) | Writer instructions; `$style_guide`, `$checklist`, `$samples` are filled in |
| [`src/newsletter_machine/prompts/critic.md`](src/newsletter_machine/prompts/critic.md) | Critic instructions; `$style_guide`, `$checklist` (judgement items only) |
| [`voice/critic-checklist.yaml`](voice/critic-checklist.yaml) | Checklist; each item cites a style-guide `## ` section. Items with `patterns`, `word_range` or `max_paragraph_chars` are checked exactly in code (em dashes, banned words, length) |

`NM_CRITIC_MODEL` picks the critic's model (default: the writer model).

## One command: `issue`

`issue` runs the whole week in one go: ingest the links, then a lead **editor** deep agent plans
the issue and delegates to a **researcher** (fast model, short sourced notes per source), the
**writer** and the **voice critic**, revising up to `NM_MAX_REVISIONS` times (default 1).

```bash
uv run newsletter-machine issue --since 7d --angle "evals are the moat" --out drafts/2026-11-06.md
```

- Links come from Gmail (`--since`, default `7d`), from `--links-file week.txt`, or reuse an
  existing `ingest` folder with `--sources DIR`. When ingesting, the source files go to
  `drafts/2026-11-06.sources/`.
- Writes `drafts/2026-11-06.md` (the final draft, `# Title` … `## Sources`),
  `drafts/2026-11-06.critique.md` (critique of that exact version) and
  `drafts/2026-11-06.notes.md` (the editor's summary, run log, skipped sources, plan, last
  brief and the research notes).
- The `## Sources` list is rebuilt in code from the ingested sources the writer cited (titles as
  ingested); links that are not ingested sources are dropped and listed in the notes.
- Code, not the model, enforces the limits: one research pass, `1 + NM_MAX_REVISIONS` writer
  runs, one critique per draft version. If the editor skips the final critique, the command runs
  it. Nothing is sent, posted or scheduled.
- Exit codes: 0 done (or no links), 1 model/inbox/write failure (draft kept when only the
  critique fails), 2 config/usage error, always before any model call.

| File | What it does |
|---|---|
| [`src/newsletter_machine/prompts/editor.md`](src/newsletter_machine/prompts/editor.md) | Editor (lead) instructions; `$writer_runs`, `$max_revisions` |
| [`src/newsletter_machine/prompts/researcher.md`](src/newsletter_machine/prompts/researcher.md) | Per-source research notes |

## Weekly schedule: `weekly` and Managed Deep Agents

`weekly` is `issue` made hands-off: it runs `issue` for today's date (in `NM_TIMEZONE`) on the
last 7 days of Gmail links, then puts one message in **your own Gmail inbox** (unread):

- the draft in the body (Markdown, unchanged) with `.md`, `.critique.md` and `.notes.md` attached;
- or "no links this week", or "run failed" with the run log.

Delivery uses Gmail `messages.insert` (permission `gmail.insert`): the message is added to your
mailbox like a received one. **Nothing is ever sent** (that permission cannot send mail), and the
message never gets the ingest label, so next week's `ingest` does not read it.

```bash
uv run newsletter-machine weekly --out-dir drafts   # local run; --overwrite to redo today's files
```

Without `--out-dir` the files go to a temporary folder that is removed after delivery (kept, and
named in the output, if delivery fails). The run log in the message includes warnings and errors.
Exit codes: the `issue` run's own non-zero code, else 1 if delivery failed, else 0; 2 for a
configuration problem (token, time zone, Substack settings), always before any model call (a bad
time zone or Substack setting is also reported to the inbox when Gmail works).

### Optional: Substack draft (off by default)

With `NM_SUBSTACK_DRAFT=true`, a successful run also creates an **unpublished** Substack draft
with the unofficial [`python-substack`](https://pypi.org/project/python-substack/) client (pinned
to 0.10.0). It never publishes, schedules or sends. The draft's `# Title` line becomes the
Substack title; the rest of the Markdown is passed unchanged (Sources list and any `[VARUN: ...]`
markers included). The draft link goes in the inbox message; a Substack failure is reported there
and does not stop delivery. Settings: `SUBSTACK_PUBLICATION_URL` plus `SUBSTACK_COOKIES`
(recommended: the `substack.sid=...` cookie string from a signed-in browser) or
`SUBSTACK_EMAIL` and `SUBSTACK_PASSWORD`.

### Runbook: deploy to LangSmith Managed Deep Agents

The repo root is a Managed Deep Agents (MDA) project: `agent.py` (a small runner agent whose
only tool, `run_weekly_issue`, runs the same code as `weekly`), `instructions.md` (its prompt),
`identity.py` (callers need a LangSmith API key) and `schedules/weekly_issue.py` (**Fridays
07:00 Asia/Kolkata**). MDA is in public beta; cron schedules appear to need a LangSmith Plus plan.

1. **Google, once.** In Google Cloud Console → *OAuth consent screen*, set the app's publishing
   status to **In production** (unverified is fine for your own account). In *Testing* status,
   refresh tokens expire after 7 days and the Friday run would stop working.
2. **Token with read + insert.** Opens a browser; saves `.secrets/gmail-token.json`.

   ```bash
   uv run newsletter-machine gmail-auth
   ```

3. **Put the token in `.env`** (base64, one line; `.env` is git-ignored):

   ```bash
   printf 'NM_GMAIL_TOKEN_B64=%s\n' "$(base64 < .secrets/gmail-token.json | tr -d '\n')" >> .env
   ```

4. **Try it locally** (one real issue's API cost; a message lands in your inbox):

   ```bash
   uv run newsletter-machine weekly --out-dir drafts
   ```

5. **Install the MDA CLI** and add your LangSmith key (`LANGSMITH_API_KEY`, plus
   `LANGSMITH_WORKSPACE_ID` if your key needs one) to `.env`:

   ```bash
   uv tool install "managed-deepagents==0.9.4"
   ```

6. **Deploy.** `mda deploy` reads `.env`, uses `LANGSMITH_API_KEY` itself and uploads every other
   variable as a deployment secret (`ANTHROPIC_API_KEY`, `NM_GMAIL_TOKEN_B64`, model names,
   `NM_*`, `SUBSTACK_*`). After the deployment is live it creates the cron from
   `schedules/weekly_issue.py`.

   ```bash
   mda build .     # optional: compile only, writes .mda/build
   mda deploy .
   mda logs .      # follow the deployed agent's logs
   ```

7. **Check** the deployment and its cron in LangSmith (*Deployments*). The first Friday run should
   leave "Newsletter draft: ..." in your inbox.

Change the time: edit `cron`/`timezone` in `schedules/weekly_issue.py` (literals only; MDA rejects
env vars there), set `NM_TIMEZONE` to the same zone, run `mda deploy .`. Stop the schedule:
delete that file and `mda deploy .`, or remove everything with `mda delete .`. New token: repeat
steps 2, 3 and 6.

## Test

```bash
uv run pytest                                           # offline, no network
```

```bash
uv run pytest --cov=newsletter_machine --cov-report=term-missing
```

```bash
uv run pytest -m live                                   # real Anthropic, web, YouTube and Gmail
```

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Anthropic credentials |
| `NM_WRITER_MODEL` | `anthropic:claude-sonnet-5-5` | Drafting model (`provider:model`) |
| `NM_FAST_MODEL` | `anthropic:claude-haiku-5-5` | Cheap summarisation model |
| `NM_CRITIC_MODEL` | writer model | Voice critic model |
| `NM_EDITOR_MODEL` | writer model | Lead editor model for `issue` |
| `NM_MAX_REVISIONS` | `1` | Critique → revise loops per issue (0 to 3) |
| `NM_VOICE_DIR` | `voice` | Voice corpus root (relative to cwd) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `NM_GMAIL_LABEL` | `newsletter` | Gmail label the inbox filter applies |
| `NM_GMAIL_ALLOWED_SENDERS` | `me` | Only mail from these senders is read (`me` = your own account; add e.g. a work address, comma-separated) |
| `NM_GMAIL_CLIENT_SECRETS` | `.secrets/gmail-client.json` | Google OAuth Desktop client JSON |
| `NM_GMAIL_TOKEN` | `.secrets/gmail-token.json` | Cached OAuth token (written on first run) |
| `NM_FETCH_TIMEOUT` | `20` | Seconds allowed per page download (and per transcript request) |
| `NM_TRANSCRIPT_LANGUAGES` | `en` | Transcript language preference, comma-separated |
| `NM_GMAIL_TOKEN_B64` | unset | Base64 of the `gmail-auth` token; when set, Gmail never opens a browser (scheduled runs) |
| `NM_TIMEZONE` | `Asia/Kolkata` | Time zone for the `weekly` issue date |
| `NM_RUNNER_MODEL` | `NM_FAST_MODEL` | Hosted runner agent's model (it only calls one tool) |
| `NM_SUBSTACK_DRAFT` | `false` | `true` adds an unpublished Substack draft to `weekly` |
| `SUBSTACK_PUBLICATION_URL` | unset | e.g. `https://varunbhanot.substack.com` (needed when the above is on) |
| `SUBSTACK_COOKIES` | unset | Browser cookie string (preferred), or set `SUBSTACK_EMAIL` and `SUBSTACK_PASSWORD` |
| `LANGSMITH_API_KEY` | unset | Tracing; also used by `mda deploy` |
