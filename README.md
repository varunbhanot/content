# content

Deep-agent content machine for the *Beyond the AI Demo* newsletter. Phase 1 gives a runnable
[`deepagents`](https://docs.langchain.com/oss/python/deepagents) skeleton on Anthropic, grounded in the
hand-written voice corpus.

- Product plan: [`.claude/PRPs/prds/newsletter-content-machine.prd.md`](.claude/PRPs/prds/newsletter-content-machine.prd.md)
- Voice corpus and split rule: [`voice/README.md`](voice/README.md)
- Voice style guide (draft, pending approval): [`voice/style-guide.md`](voice/style-guide.md)

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

## Test

```bash
uv run pytest                                           # offline, no network
```

```bash
uv run pytest --cov=newsletter_machine --cov-report=term-missing
```

```bash
uv run pytest -m live                                   # calls the real API; needs ANTHROPIC_API_KEY
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
