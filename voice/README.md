# Voice corpus

Source posts from *Beyond the AI Demo* (varunbhanot.substack.com), converted to Markdown with front-matter (`title`, `subtitle`, `date`, `url`, `words`, `era`).

| Folder | Posts | Dates | Use |
|---|---|---|---|
| `samples/hand/` | 13 | 2024-11 → 2026-01 | **Ground truth for voice.** Written by hand. Writer and critic agents imitate these. |
| `samples/ai-assisted/` | 10 | 2026-05 → 2026-09 | AI-assisted drafts, then edited. Use for **topics, depth and structure** only, not for voice. Also a source of AI-isms for the critic to flag. |

Split rule: posts dated on or after `2026-05-01` are tagged `ai-assisted`. This is an assumption based on when the series format changed (the "Day N" posts ended, longer essays began). Move a file between folders if the split is wrong.

## Refreshing

The archive API is `https://varunbhanot.substack.com/api/v1/archive?sort=new&limit=50`; each post is at `/api/v1/posts/{slug}` (`body_html`). Fetch with `curl` (Python `urllib` without a browser User-Agent gets 403).
