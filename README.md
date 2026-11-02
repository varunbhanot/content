# content

Deep-agent content machine for the *Beyond the AI Demo* newsletter. Phase 1 gives a runnable
[`deepagents`](https://docs.langchain.com/oss/python/deepagents) skeleton on Anthropic, grounded in the
hand-written voice corpus. Phase 2 turns the week's emailed links into clean source text.

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
| `NM_VOICE_DIR` | `voice` | Voice corpus root (relative to cwd) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `NM_GMAIL_LABEL` | `newsletter` | Gmail label the inbox filter applies |
| `NM_GMAIL_ALLOWED_SENDERS` | `me` | Only mail from these senders is read (`me` = your own account; add e.g. a work address, comma-separated) |
| `NM_GMAIL_CLIENT_SECRETS` | `.secrets/gmail-client.json` | Google OAuth Desktop client JSON |
| `NM_GMAIL_TOKEN` | `.secrets/gmail-token.json` | Cached OAuth token (written on first run) |
| `NM_FETCH_TIMEOUT` | `20` | Seconds allowed per page download (and per transcript request) |
| `NM_TRANSCRIPT_LANGUAGES` | `en` | Transcript language preference, comma-separated |
