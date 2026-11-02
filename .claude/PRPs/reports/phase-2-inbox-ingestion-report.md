# Implementation Report: Phase 2 — Inbox & ingestion

## Summary
`newsletter-machine ingest` reads the Gmail label for the `+newsletter` inbox (or a `--links-file`), extracts each link plus Varun's one-line note, fetches articles (httpx + trafilatura) and YouTube transcripts (youtube-transcript-api, falling back to the video description with an explicit "Transcript unavailable" notice), and writes one Markdown file per source with YAML front-matter (`url`, `title`, `kind`, `status`, `note`, `detail`). Everything runs offline in tests through injected fakes. Live Gmail, web and YouTube runs are still open (see Open Items).

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Large | Large |
| Confidence | High, all integrations behind seams | Met. Three review rounds added hardening the plan did not foresee: SSRF guard, sender allow-list, staged writes |
| Files Changed | ~16 | 26 (7 new src modules, 8 new test files, config/docs/lock) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Config: `IngestSettings` | Complete | Also `NM_GMAIL_ALLOWED_SENDERS` (added in review) |
| 2 | `sources.py` records and parsing | Complete | URLs keep balanced parens; `normalize_url` is only the dedupe key |
| 3 | `gmail.py` | Complete | `GmailClient` protocol, `GoogleGmailClient` adapter, OAuth with a 0600 token, HTMLParser for HTML-only mail |
| 4 | HTML fetcher | Complete, renamed `web.py` | Name avoids confusion with stdlib `http`. Adds size cap, total deadline, meta-charset sniffing, private-host guard on every redirect hop |
| 5 | `articles.py` | Complete | |
| 6 | `youtube.py` | Complete | Any transcript error leads to fallback. EU consent-page title ignored. `TimeoutSession` bounds transcript requests |
| 7 | `ingest.py` | Complete | Staged writes. `--overwrite` only touches files earlier runs wrote |
| 8 | CLI `ingest` | Complete | Exit 0/1/2. `--out` checked before any fetching |
| 9 | Docs/config | Complete | README "Ingest" and "Gmail setup", `.env.example`, `.gitignore` (`.secrets/`, `sources/`) |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | Pass | `ruff check .`, `ruff format --check .`, `mypy src` (strict): zero issues |
| Unit Tests | Pass | 160 passed offline, 4 live deselected |
| Coverage | Pass | 99% total; every new module at 100% |
| Build | Pass | `uv sync`, package import |
| CLI smoke | Pass | `ingest --links-file` end to end. The sandbox proxy blocks egress, so the run gave `failed` (403) and `fallback` (ProxyError) records as designed, with exit 0 |
| Live tests | **Not run** | Sandbox egress returns 403 for web and YouTube; no Gmail credentials here |

## Files Changed
Created: `src/newsletter_machine/{sources,gmail,web,articles,youtube,ingest}.py`, `tests/test_{sources,gmail,web,articles,youtube,ingest,cli_ingest,ingest_live}.py`, this report, the plan.
Updated: `src/newsletter_machine/{config,cli}.py`, `tests/test_config.py`, `pyproject.toml` (deps, `live` marker, ruff excludes `.claude/`), `uv.lock`, `.env.example`, `.gitignore`, `README.md`, the PRD row.

## Deviations from Plan
- **`http.py` renamed to `web.py`**, to avoid confusion with the stdlib `http` package.
- **`make_html_fetcher(transport=...)`** takes a transport instead of a client, so the private-host event hook is always installed.
- **Sender allow-list (`NM_GMAIL_ALLOWED_SENDERS`, default `me`)** was added in review. Without it, anyone emailing the plus-address could make the tool fetch URLs.
- **`requests` and `types-requests`** were added as direct deps for `TimeoutSession` (youtube-transcript-api uses requests and sets no timeout).
- **ruff `extend-exclude = [".claude"]`**: `ruff format --check .` was formatting Python snippets inside plan Markdown. Phase 1's plan already failed this check on `main`.
- **Exit codes**: an existing `--out` with earlier output exits 2 before fetching, instead of 1 after fetching.
- **Plan not archived; PRD Phase 2 left `in-progress`**, as in Phase 1: the live acceptance checks are still open.

## Issues Encountered
- Live tests showed that youtube-transcript-api raises raw `requests` errors on network or proxy failure, not its own exception types. All transcript errors now lead to the fallback, and there is a regression test for this.
- The sandbox egress proxy returns 403 for wikipedia.org and youtube.com, so live checks could not run here.

## Review
Three `code-review high` rounds (10 findings each). Fixed: 28. Skipped with reasons: 2 (sequential fetching / Gmail batching; fine at weekly volume, listed as follow-ups). No CRITICAL/HIGH issues remain open.

## Open Items
- [ ] Varun: Gmail setup (OAuth Desktop client JSON at `.secrets/gmail-client.json`, Gmail API enabled, label + filter), then `uv run pytest -m live tests/test_ingest_live.py` and `uv run newsletter-machine ingest --since 7d --out sources/this-week`.
- [ ] Confirm the files for a real week look right (titles, notes, transcripts), then archive the plan and mark Phase 2 `complete`.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_sources.py` | 31 | URL extraction/normalising, YouTube ids, `--since`, links file, failed_doc |
| `tests/test_gmail.py` | 17 | parsing (plain/HTML/multipart), notes, sender query, adapter paging, OAuth flows |
| `tests/test_web.py` | 25 | status/content-type/size/deadline, charset, scheme + private-host guard incl. redirects |
| `tests/test_articles.py` | 3 | ok / fetch error / empty page |
| `tests/test_youtube.py` | 13 | transcript, fallbacks, consent page, timeout session |
| `tests/test_ingest.py` | 17 | routing, slugify, front-matter, overwrite safety, staged writes |
| `tests/test_cli_ingest.py` | 12 | links file, Gmail paths, exit codes |
| `tests/test_config.py` | +12 | ingest settings |
| `tests/test_ingest_live.py` | 3 (live) | real article, YouTube transcript, Gmail label |

## Next Steps
- [ ] Complete Open Items above
- [ ] Phase 4 consumes `sources/<week>/*.md`. Treat source text as untrusted data in prompts.
