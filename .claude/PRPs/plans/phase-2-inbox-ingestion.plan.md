# Plan: Phase 2 — Inbox & ingestion

## Summary
Turn a week of links into clean source text. Read the Gmail label that Varun's filter applies to mail sent to `varunbhanot+newsletter@gmail.com`, pull every link (plus his optional one-line note) out of those messages, fetch and extract articles with `trafilatura`, fetch YouTube transcripts with `youtube-transcript-api` (falling back to the video's title/description and a clear "transcript unavailable" record), and write one Markdown file per source with URL and title. Exposed as `newsletter-machine ingest --since 7d --out <dir>`.

## User Story
As Varun, I want one command that reads the links I emailed myself this week and saves each one as clean text with its URL and title, so that the research/writer agents in later phases work from real source material instead of me pasting it in by hand.

## Problem → Solution
Links sit in Gmail; reading them means opening each tab and copy-pasting → `newsletter-machine ingest --since 7d --out sources/2026-11-06` writes `01-<slug>.md`, `02-<slug>.md`, … each with front-matter (url, title, kind, status, note) and extracted body text.

## Metadata
- **Complexity**: Large (3 external integrations, all behind injectable seams)
- **Source PRD**: `.claude/PRPs/prds/newsletter-content-machine.prd.md`
- **PRD Phase**: Phase 2 — Inbox & ingestion
- **Estimated Files**: ~16 (7 src, 7 tests, config/docs)

---

## UX Design

### Before
```
┌──────────────────────────────────────────────┐
│ Links emailed to +newsletter → Gmail label    │
│ To use them: open each, copy text, paste into │
│ Claude by hand. YouTube = watch or no notes.  │
└──────────────────────────────────────────────┘
```

### After
```
┌──────────────────────────────────────────────────────────┐
│ $ uv run newsletter-machine ingest --since 7d --out src/ │
│ (first run only: browser opens for Gmail consent)        │
│ Found 6 links in label 'newsletter' since 2026-10-30     │
│   ok        01-why-agents-fail.md                        │
│   ok        02-yt-dQw4w9WgXcQ.md         (transcript)    │
│   fallback  03-some-talk.md   (transcript unavailable)   │
│   failed    04-paywalled.md   (HTTP 403)                 │
│ Wrote 6 files to src/ (4 ok, 1 fallback, 1 failed)       │
└──────────────────────────────────────────────────────────┘
$ uv run newsletter-machine ingest --links-file links.txt --out src/   # no Gmail
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Terminal | `hello` only | `ingest --since 7d --out DIR [--links-file F]` | `--links-file` bypasses Gmail (manual / offline input) |
| Config | Anthropic vars | + `NM_GMAIL_LABEL`, `NM_GMAIL_CLIENT_SECRETS`, `NM_GMAIL_TOKEN`, `NM_FETCH_TIMEOUT`, `NM_TRANSCRIPT_LANGUAGES` | ingest does NOT require `ANTHROPIC_API_KEY` |
| Gmail | — | OAuth consent once; token cached at `NM_GMAIL_TOKEN` (0600) | read-only scope |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/newsletter_machine/config.py` | all | `ConfigError`, frozen `Settings`, `load_settings(env, repo_root=)` pattern to mirror |
| P0 | `src/newsletter_machine/cli.py` | all | argparse subparsers, exit codes (2 config, 1 runtime), logging config after `.env` load |
| P0 | `tests/test_cli.py` | 1-15 | autouse fixture that blocks the real `.env` |
| P1 | `src/newsletter_machine/voice.py` | all | frozen dataclass records, tuple returns, `ValueError` naming the bad input |
| P1 | `tests/conftest.py`, `tests/test_agent.py` | live test block | `@pytest.mark.live` + `skipif` + `LIVE_ENV` pattern |
| P1 | `.claude/rules/ecc/common/coding-style.md` | all | immutability, <50-line functions, <800-line files |

## External Documentation

Verified against installed packages on 2026-11-02: `google-api-python-client 2.201.0`, `google-auth 2.62.0`, `google-auth-oauthlib 1.5.0`, `trafilatura 2.3.1`, `youtube-transcript-api 1.2.4`, `httpx 0.28.1`.

| Topic | Source | Key Takeaway |
|---|---|---|
| Gmail list | Gmail API `users.messages.list` | `service.users().messages().list(userId="me", labelIds=[id], q="after:<epoch>", pageToken=...)`; pages via `nextPageToken`; returns `{"messages": [{"id","threadId"}]}` or no `messages` key when empty |
| Gmail get | `users.messages.get(format="full")` | `payload` tree of `parts`, each with `mimeType`, `body.data` (base64url, no padding) and `headers` (`Subject`, `Date`); `internalDate` is epoch ms |
| Gmail labels | `users.labels.list` | Resolve label name → id (labels with spaces/nesting are awkward in `q`, ids are not) |
| OAuth (installed app) | `google_auth_oauthlib.flow.InstalledAppFlow` | `from_client_secrets_file(path, SCOPES).run_local_server(port=0)`; cache with `Credentials.to_json()`; reload with `Credentials.from_authorized_user_file`; refresh with `creds.refresh(google.auth.transport.requests.Request())` |
| Transcripts | `youtube_transcript_api/_api.py:51` | v1.x is instance-based: `YouTubeTranscriptApi().fetch(video_id, languages=("en",))` → `FetchedTranscript` iterable of snippets with `.text`. All errors subclass `YouTubeTranscriptApiException` (`TranscriptsDisabled`, `NoTranscriptFound`, `IpBlocked`, `RequestBlocked`, `VideoUnavailable`, …) |
| Extraction | `trafilatura.bare_extraction` | `bare_extraction(html, url=url, with_metadata=True, include_comments=False)` → `trafilatura.settings.Document` (`.title`, `.description`, `.text`) or `None` for empty pages; `py.typed` shipped |

```
KEY_INSIGHT: YouTube blocks transcript fetches from many cloud IPs (IpBlocked/RequestBlocked).
APPLIES_TO: youtube.py
GOTCHA: Catch YouTubeTranscriptApiException (base class) and fall back; never crash the run. The fallback record names the reason and tells Varun to paste a transcript.

KEY_INSIGHT: Watch-page HTML carries og:title / og:description, which trafilatura's metadata reads.
APPLIES_TO: youtube.py fallback + titles for successful transcripts
GOTCHA: From some IPs YouTube serves a consent page; title then falls back to "YouTube video <id>".

KEY_INSIGHT: trafilatura.bare_extraction returns Document | dict | None.
APPLIES_TO: articles.py
GOTCHA: isinstance-check Document for mypy strict; None/empty text => status "failed" with reason "no extractable text".

KEY_INSIGHT: google-api-python-client is untyped and its resource chain is dynamic.
APPLIES_TO: gmail.py
GOTCHA: Hide it behind a small GmailClient Protocol so the reading logic is typed and fakeable; only the thin adapter touches the discovery resource.
```

---

## Patterns to Mirror

### NAMING_CONVENTION / RECORDS
// SOURCE: src/newsletter_machine/voice.py:13-24
```python
Era = Literal["hand", "ai-assisted"]

@dataclass(frozen=True)
class VoiceSample:
    title: str
    date: date
    ...
```

### ERROR_HANDLING (config)
// SOURCE: src/newsletter_machine/config.py:17-35
```python
class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""

def _require_provider_prefix(name: str, value: str) -> str:
    ...
        raise ConfigError(f"{name} must look like 'provider:model' (got {value!r}).")
```

### CONFIG LOADING
// SOURCE: src/newsletter_machine/config.py:38-46
```python
def load_settings(env: Mapping[str, str] | None = None, *, repo_root: Path | None = None) -> Settings:
    if env is None:
        load_dotenv(find_dotenv(usecwd=True))
        env = os.environ
```

### LOGGING_PATTERN
// SOURCE: src/newsletter_machine/agent.py:15,35
```python
logger = logging.getLogger(__name__)
logger.debug("Building hello agent rooted at %s", settings.voice_dir)
```

### CLI / EXIT CODES
// SOURCE: src/newsletter_machine/cli.py:52-67
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
    print(f"Agent run failed: {exc}", file=sys.stderr)
    return EXIT_ERROR
```

### TEST_STRUCTURE
// SOURCE: tests/test_cli.py:10-13, tests/test_agent.py:84-92
```python
@pytest.fixture(autouse=True)
def _ignore_real_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)

@pytest.mark.live
@pytest.mark.skipif(not LIVE_ENV.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
def test_...(...)
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `pyproject.toml`, `uv.lock` | UPDATE | deps (done via `uv add`), `live` marker text |
| `src/newsletter_machine/config.py` | UPDATE | `IngestSettings` + `load_ingest_settings` (no Anthropic key needed) |
| `src/newsletter_machine/sources.py` | CREATE | records (`InboxLink`, `SourceDoc`), URL extraction/normalisation, YouTube id parsing, `--since` parsing |
| `src/newsletter_machine/gmail.py` | CREATE | `GmailClient` protocol, `read_inbox_links`, `GoogleGmailClient` adapter, `build_gmail_client` (OAuth) |
| `src/newsletter_machine/http.py` | CREATE | `HtmlFetcher` type, `FetchError`, `make_html_fetcher` (httpx, timeout, size cap, http/https only) |
| `src/newsletter_machine/articles.py` | CREATE | `extract_article(url, fetch_html)` → `SourceDoc` |
| `src/newsletter_machine/youtube.py` | CREATE | `TranscriptFetcher` type, `make_transcript_fetcher`, `ingest_youtube(...)` with fallback |
| `src/newsletter_machine/ingest.py` | CREATE | `ingest_links`, `write_sources` (Markdown + front-matter per source) |
| `src/newsletter_machine/cli.py` | UPDATE | `ingest` subcommand |
| `tests/test_sources.py`, `test_gmail.py`, `test_http.py`, `test_articles.py`, `test_youtube.py`, `test_ingest.py`, `test_cli_ingest.py` | CREATE | offline tests with fakes |
| `tests/test_config.py` | UPDATE | ingest settings tests |
| `.env.example`, `.gitignore`, `README.md` | UPDATE | new vars, `.secrets/`, ingest docs + Gmail setup |

## NOT Building
- Summarisation / research notes (researcher sub-agent is Phase 4)
- Writer/critic, editor orchestration, scheduling, Substack
- Marking Gmail messages as processed / modifying labels (read-only scope)
- Transcript proxy services, Whisper audio transcription, PDF extraction
- Parallel fetching, caching, per-run source caps

---

## Step-by-Step Tasks

### Task 1: Config — `IngestSettings`
- **ACTION**: add to `config.py`.
- **IMPLEMENT**: frozen `IngestSettings(gmail_label: str, gmail_client_secrets: Path, gmail_token: Path, fetch_timeout: float, transcript_languages: tuple[str, ...])`. `load_ingest_settings(env=None, *, repo_root=None)`: same dotenv behaviour as `load_settings`; defaults `NM_GMAIL_LABEL=newsletter`, `NM_GMAIL_CLIENT_SECRETS=.secrets/gmail-client.json`, `NM_GMAIL_TOKEN=.secrets/gmail-token.json`, `NM_FETCH_TIMEOUT=20`, `NM_TRANSCRIPT_LANGUAGES=en`; relative paths resolved against `repo_root or cwd`. `ConfigError` for blank label, non-positive/non-numeric timeout, empty language list. Do NOT check secrets files exist here (only needed for Gmail; `--links-file` runs without them) — check in `build_gmail_client`.
- **MIRROR**: CONFIG LOADING, ERROR_HANDLING.
- **GOTCHA**: share a `_load_env` helper with `load_settings` (DRY) and a `_resolve_path` helper.
- **VALIDATE**: `tests/test_config.py` new cases.

### Task 2: `sources.py` — records and pure parsing
- **IMPLEMENT**:
  - `SourceKind = Literal["article", "youtube"]`, `SourceStatus = Literal["ok", "fallback", "failed"]`.
  - `@dataclass(frozen=True) InboxLink(url, note, subject, received_at: datetime)`.
  - `@dataclass(frozen=True) SourceDoc(url, title, kind, status, text, note="", detail="")` (`detail` = failure/fallback reason).
  - `extract_urls(text) -> tuple[str, ...]`: regex `https?://[^\s<>"'\]\)]+`, strip trailing `.,;:!?`, dedupe preserving order.
  - `normalize_url(url) -> str`: drop fragment and `utm_*`/`fbclid`/`gclid` params, lowercase scheme/host.
  - `youtube_video_id(url) -> str | None`: `youtube.com|www.|m.|music.` `/watch?v=`, `/shorts/`, `/embed/`, `/live/`, `youtu.be/<id>`; id must match `[A-Za-z0-9_-]{11}`.
  - `parse_since(value, now) -> datetime`: `Nd`, `Nh`, `Nw` or `YYYY-MM-DD` (UTC); `ValueError` otherwise or N <= 0.
  - `read_links_file(path, now) -> tuple[InboxLink, ...]`: one URL per line, optional note after whitespace, `#` comments.
- **GOTCHA**: `received_at` always tz-aware UTC.

### Task 3: `gmail.py`
- **IMPLEMENT**:
  - `GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)`; `GmailError(Exception)`.
  - `class GmailClient(Protocol)`: `label_id(name) -> str | None`, `list_message_ids(label_id, query) -> list[str]`, `get_message(message_id) -> Mapping[str, Any]`.
  - `read_inbox_links(client, label, since) -> tuple[InboxLink, ...]`: resolve label (missing → `GmailError` naming the label and listing setup hint); `q=f"after:{int(since.timestamp())}"`; per message: decode `text/plain` parts (fallback: `href`s/text from `text/html`), extract URLs, skip `mailto:`/unsubscribe/google-account links, note = non-URL plain text lines joined (≤ 280 chars), subject from headers, `received_at` from `internalDate`. Dedupe by `normalize_url` across messages (first wins), sorted oldest first.
  - `GoogleGmailClient(service)`: adapter over discovery resource, paging `nextPageToken`.
  - `build_gmail_client(settings)`: missing client secrets → `ConfigError` with setup steps; load token if present, refresh if expired, else `InstalledAppFlow.run_local_server(port=0)`; write token with mode 0600 (create parent dir); `build("gmail", "v1", credentials=creds, cache_discovery=False)`.
- **GOTCHA**: base64url bodies lack padding — pad before decoding; decode with `errors="replace"`.

### Task 4: `http.py`
- **IMPLEMENT**: `HtmlFetcher = Callable[[str], str]`; `FetchError(Exception)`; `make_html_fetcher(timeout, client=None)` using `httpx.Client(follow_redirects=True, timeout=..., headers={"User-Agent": ...})`; reject non-http(s) schemes; raise `FetchError` on HTTP status ≥ 400 (`"HTTP 403"`), transport errors, and bodies > 5 MB (stream and count). Non-HTML content types → `FetchError("unsupported content type …")`.
- **VALIDATE**: `httpx.MockTransport` in tests (no network).

### Task 5: `articles.py`
- **IMPLEMENT**: `extract_article(link, fetch_html) -> SourceDoc`. `FetchError` → `failed` with detail. `bare_extraction` → None/empty text → `failed` ("no extractable text"). Title = doc.title or URL.

### Task 6: `youtube.py`
- **IMPLEMENT**: `TranscriptFetcher = Callable[[str], str]`; `make_transcript_fetcher(languages)` joining snippet text; `ingest_youtube(link, video_id, fetch_transcript, fetch_html) -> SourceDoc`: metadata (title/description) best-effort via `fetch_html(watch URL)` + `trafilatura.extract_metadata`; transcript ok → `status="ok"`; `YouTubeTranscriptApiException` → `status="fallback"`, text = description (if any) + clear "Transcript unavailable (<ErrorClass>). Paste a transcript manually if this video matters." Title fallback `YouTube video <id>`.

### Task 7: `ingest.py`
- **IMPLEMENT**: `ingest_links(links, *, fetch_html, fetch_transcript) -> tuple[SourceDoc, ...]` routing by `youtube_video_id`; catch-all per source so one bad link never aborts the run (log + `failed`). `write_sources(docs, out_dir) -> tuple[Path, ...]`: `NN-<slug>.md` (slug from title, ≤ 60 chars, ascii), YAML front-matter via `yaml.safe_dump` (url, title, kind, status, note, detail), then `# title`, blank line, text. Refuse to write into a non-empty dir unless all existing files are ours? Simpler: create dir; if it contains `*.md` already raise `FileExistsError` unless `overwrite=True`.

### Task 8: CLI `ingest`
- **IMPLEMENT**: `ingest --since 7d --out DIR [--links-file FILE] [--overwrite]`. Load `IngestSettings` (ConfigError → 2); bad `--since` → argparse error (exit 2). Source links from file or Gmail (`GmailError`/other exceptions → 1). Build fetchers, ingest, write, print one line per file + summary. Exit 0 when the run completes (per-source failures are reported, not fatal); exit 1 if writing fails.
- **MIRROR**: CLI / EXIT CODES; keep `hello` untouched.

### Task 9: Docs/config
- `.env.example` new vars; `.gitignore` add `.secrets/` and `sources/`; README "Ingest" + "Gmail setup" sections; `live` marker description: "calls real external services (Anthropic, Gmail, web, YouTube)".

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| extract_urls | text with trailing `.`/`)` and duplicates | clean, deduped tuple | yes |
| normalize_url | utm params + fragment | stripped | |
| youtube_video_id | watch/shorts/youtu.be/embed/live/non-YT/bad id | id or None | yes |
| parse_since | `7d`, `24h`, `2w`, `2026-10-30`, `0d`, `abc` | datetime / ValueError | yes |
| read_links_file | comments, notes, blank lines | InboxLinks | yes |
| read_inbox_links | fake client: plain + html-only + multipart messages, dup URLs | ordered deduped links with notes | yes |
| read_inbox_links | label missing | GmailError | yes |
| GoogleGmailClient | fake discovery resource with 2 pages | all ids | |
| build_gmail_client | no client secrets / cached valid token / expired token refresh / first-run flow writes 0600 token | ConfigError / client | yes |
| html fetcher | MockTransport 200, 404, non-HTML, oversize, ftp:// , transport error | text / FetchError | yes |
| extract_article | good html / FetchError / empty page | ok / failed / failed | yes |
| ingest_youtube | transcript ok / TranscriptsDisabled / metadata fetch fails | ok / fallback / title fallback | yes |
| ingest_links | mixed links + fetcher raising unexpected error | per-source docs, no abort | yes |
| write_sources | docs → files; existing md without overwrite | files with front-matter / FileExistsError | yes |
| CLI ingest | links-file happy path; gmail path via monkeypatched builder; GmailError → 1; bad --since → 2 | exit codes + output | yes |

### Live tests (`@pytest.mark.live`, deselected by default)
- Gmail read of real label (skip unless token file exists).
- Article fetch of a stable page (e.g. `https://example.com`).
- YouTube transcript of a known captioned video.

### Edge Cases Checklist
- [x] Empty inbox (no messages) → "No links found", exit 0, no files
- [x] Network failure → per-source `failed`
- [x] Invalid input (`--since`, links file, URLs)
- [x] Permission: token written 0600

---

## Validation Commands
```bash
uv run ruff check . && uv run ruff format --check src tests && uv run mypy src
uv run pytest --cov=newsletter_machine --cov-report=term-missing   # >= 80%, offline
uv run pytest -m live                                              # manual, needs creds/network
uv run newsletter-machine ingest --links-file links.txt --out /tmp/sources
uv run newsletter-machine ingest --since 7d --out sources/this-week
```

## Acceptance Criteria
- [ ] Given a week's links (Gmail label or links file), one text file per source with URL and title
- [ ] YouTube without transcript yields a clear fallback record, never a crash
- [ ] All offline tests pass, coverage >= 80%, ruff + mypy strict clean
- [ ] No secrets in repo; Gmail paths/label from env

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| YouTube blocks transcript fetch | H | M | Fallback record + description; run locally |
| Gmail OAuth "testing" app tokens expire after 7 days | M | L | Refresh failure → re-run consent flow automatically |
| Paywalled / JS-only articles | M | L | `failed` record with reason; Varun can paste text |
| Label name mismatch | M | L | Clear GmailError naming the label + env var |

## Notes
- `ingest` deliberately does not require `ANTHROPIC_API_KEY`: separate `IngestSettings`.
- `--links-file` gives a Gmail-free path for testing and for weeks when the inbox is not set up.
