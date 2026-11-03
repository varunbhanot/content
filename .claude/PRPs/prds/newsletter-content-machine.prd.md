# Newsletter Content Machine

## Problem Statement

Varun writes a weekly Substack newsletter (varunbhanot.substack.com) built from what he learns across YouTube, videos and articles. Today those learnings are scattered with no capture system, and turning them into a post means hand-feeding material to Claude, getting generic "AI-sounding" prose with shallow research, and then rewriting it into his own style. The cost: the slowest, least enjoyable work (gathering, researching, de-AI-ing the draft) crowds out the parts only he can do (learning and forming opinions), which puts a consistent weekly cadence, and subscriber growth, at risk.

## Evidence

- Owner's own report: current workflow is "learn → give it to Claude → it writes in a certain AI way → I change it to my style."
- Owner's own report: manual Claude use produces generic writing, weak research, and is "not a holistic system."
- Owner's own report: learning inputs are multi-format (YouTube, videos, articles) and "not structured."
- External: builders of similar pipelines report voice drift by the 3rd–4th issue unless the agent is grounded in real writing samples and every issue is human-reviewed (Xero newsletter-agent guide).
- Baseline time per issue: **Assumption - needs measurement** (time the next 1–2 issues done the current way).
- Baseline subscriber count: **272** (owner, 2026-11-02), accumulated over ~24 months since the first post (2024-11-22) at an irregular cadence - roughly **11/month**.
- Voice corpus: 23 published posts; owner confirms posts before 2026-05 were hand-written and later ones AI-assisted - the hand-written set is the voice target.

## Proposed Solution

A personal multi-agent system built with LangChain `deepagents` on Anthropic models. During the week Varun drops links (plus an optional one-line thought) into a zero-friction inbox. On run, a lead "editor" agent plans the issue and delegates to sub-agents: a **researcher** that ingests articles and YouTube transcripts and produces sourced notes, a **writer** that drafts in Varun's voice grounded in his best past posts and a written style guide, and a **voice critic** that flags AI-isms and style violations before the draft reaches him. Output is a Markdown draft with sources that Varun edits, adds final opinions to, and publishes himself. This approach beats ad-hoc chat use because it is a repeatable system with persistent voice grounding and structured research, and doubles as a hands-on way for Varun to learn deep agents.

## Key Hypothesis

We believe a deep agent grounded in Varun's past posts and fed his weekly links will produce newsletter drafts that need ≤30 minutes of editing.
We'll know we're right when he ships 4 consecutive weekly issues produced with the system, with ≤30 min edit time on each, and subscribers grow at ≥+30/month (vs. ~11/month historically).

## What We're NOT Building

- Auto-publishing without approval - Varun approves every issue; final opinions are his.
- Multi-user / product features - personal tool only.
- Topic selection for him - he chooses what to learn; agents work from his inputs.
- Automated evals (DeepEval etc.) - explicitly deferred by owner for now.
- Substack Notes / LinkedIn snippets - planned as a **separate add-on** (own PRD) to push from baseline toward 1,000 subscribers.
- Analytics - deferred past v1.

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Publishing cadence | 1 issue/week, 4 weeks straight | Substack archive |
| Edit time per draft | ≤30 min | Self-timed per issue |
| Subscribers (v1 baseline) | 272 → **~450 by 2027-06-30** (≥+30/month, ~3× the historical ~11/month) from consistent weekly publishing alone | Substack dashboard, weekly |
| Subscribers (long-term) | **1,000** - owned by the future distribution add-on, not v1 | Substack dashboard |
| API cost | ≤$20–30/month (~$5–7/issue) | Anthropic console usage |

## Open Questions

- [x] ~~What does a typical issue look like?~~ Resolved: single-topic practical essays on agentic AI in production, ~550–1,400 words by hand (~1,100–1,800 AI-assisted). Corpus in `voice/` (see `voice/README.md`).
- [x] ~~Baseline subscriber count and growth target~~ Resolved: 272 on 2026-11-02; target 1,000 (see Success Metrics).
- [x] ~~Do distribution helpers need to be in v1?~~ Resolved: no. v1 sets the content-only baseline; Substack Notes / LinkedIn becomes a separate add-on PRD aimed at the 1,000 goal.
- [ ] Does Managed Deep Agents scheduling (cron) work on the free Developer tier, or need Plus? Product is in beta (docs conflict: public vs. private/US-only).
- [ ] Will YouTube transcript fetching work from LangSmith cloud IPs, or is a fallback needed?
- [ ] Confirm inbox choice (see Decisions Log) works on Varun's phone share-sheet flow.

---

## Users & Context

**Primary User**
- **Who**: Varun - sole author of a weekly Substack; comfortable with Python; has Anthropic API keys; wants to learn deep agents.
- **Current behavior**: Consumes YouTube/videos/articles ad hoc, pastes material into Claude, rewrites the generic output into his voice.
- **Trigger**: Encountering something worth sharing during the week; the weekly publishing deadline.
- **Success state**: A sourced, in-voice draft is waiting; he spends ~20 min adding opinions and polish, then publishes.

**Job to Be Done**
When I learn something worth sharing during the week, I want to drop the link with a one-line thought and get back a well-researched draft in my voice, so I can spend my time on learning and forming opinions, publish every week without fail, and grow subscribers.

**Non-Users**
Other newsletter writers, teams, and readers - this is a single-owner personal tool.

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | Link inbox (zero-friction capture from phone/desktop) | Inputs are scattered today; without capture, research stays weak |
| Must | Ingest articles + YouTube transcripts into sourced research notes | Fixes "research is weak" |
| Must | Voice-grounded draft (past posts + style guide) with voice-critic pass | Fixes "generic AI writing" - the core pain |
| Should | Weekly scheduled run on Managed Deep Agents | Removes the manual trigger; depends on tier/beta |
| Should | Substack draft creation via unofficial `python-substack` | Saves copy-paste; unofficial API may break |
| Could | Subject-line options | Small growth helper |
| Won't (v1) | Auto-publish, evals, analytics, multi-user | See "What We're NOT Building" |

### MVP Scope

Manual (non-scheduled) run on one week's real links → one Markdown draft with sources. Varun edits and times himself. Success = ≤30 min editing on 2 consecutive issues.

### User Flow

1. During the week: share a link (+ optional one-liner) to the inbox.
2. Run the agent (manually in MVP; scheduled Friday later).
3. Receive Markdown draft + source list.
4. Edit, add final opinions, paste into Substack, publish.

---

## Technical Approach

**Feasibility**: MEDIUM-HIGH - all components exist; risk sits in beta hosting, YouTube access, and the unofficial Substack API.

**Architecture Notes**
- `deepagents` (Python, MIT, LangGraph runtime): lead editor agent + sub-agents (researcher, writer, voice critic) using built-in planning, `task` delegation, and virtual filesystem for notes/drafts.
- Models: Sonnet for drafting/critique; Haiku for per-source summarisation to stay within ~$5–7/issue.
- Voice assets in repo: `voice/samples/hand/` (13 hand-written posts, 2024-11 → 2026-01) are the **voice ground truth**; `voice/samples/ai-assisted/` (10 posts, 2026-05 → 2026-09) are for topic/depth reference only and as examples of AI-isms for the critic. Plus `voice/style-guide.md` (openings, closings, phrasing, banned words), distilled from the hand-written set and injected into writer and critic.
- Inbox: Gmail label (see Decisions Log), read via Gmail API.
- Hosting: run locally/CLI first; deploy to LangSmith Managed Deep Agents (free Developer tier) with a weekly schedule once MVP is validated.
- Output: Markdown file first; optional Substack draft via `python-substack` later.

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Voice still reads generic | M | Ground in real posts; style guide with banned phrases; critic loop; iterate guide from each edit |
| YouTube blocks transcript fetch from cloud IPs | H | Fallback: transcript service or paste transcript; run ingestion locally |
| Managed Deep Agents beta/tier limits (cron may need Plus) | M | Develop locally; scheduling is a Should, not a Must |
| Unofficial Substack API breaks / auth friction | M | Markdown output is the v1 contract; Substack drafting is optional |
| API cost exceeds budget | L-M | Cap sources per issue; Haiku for summaries; track usage |

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently (e.g., "with 3" or "-")
  DEPENDS: phases that must complete first (e.g., "1, 2" or "-")
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | Foundations | Python project, deepagents + Anthropic wiring, voice assets (samples + style guide) | complete | - | - | [plan](../plans/completed/phase-1-foundations.plan.md), [report](../reports/phase-1-foundations-report.md) |
| 2 | Inbox & ingestion | Gmail-label inbox reader; article + YouTube transcript extraction | complete | with 3 | 1 | [plan](../plans/completed/phase-2-inbox-ingestion.plan.md), [report](../reports/phase-2-inbox-ingestion-report.md) |
| 3 | Voice writer & critic | Writer + voice-critic sub-agents grounded in samples/style guide | complete | with 2 | 1 | [plan](../plans/completed/phase-3-voice-writer-critic.plan.md), [report](../reports/phase-3-voice-writer-critic-report.md) |
| 4 | Editor orchestration (MVP) | Lead agent: plan → research → draft → critique → Markdown draft; manual run | complete | - | 2, 3 | [plan](../plans/completed/phase-4-editor-orchestration.plan.md), [report](../reports/phase-4-editor-orchestration-report.md) |
| 5 | Schedule & delivery | Deploy to Managed Deep Agents with weekly cron; optional Substack draft | complete | - | 4 | [plan](../plans/completed/phase-5-schedule-delivery.plan.md), [report](../reports/phase-5-schedule-delivery-report.md) |

### Phase Details

**Phase 1: Foundations**
- **Goal**: Runnable deep agent skeleton and voice assets.
- **Scope**: Project layout, deps, config/secrets via env vars, `voice/style-guide.md` distilled from `voice/samples/hand/` (corpus already committed).
- **Success signal**: A hello-world deep agent runs on Anthropic; style guide committed and approved by Varun.

**Phase 2: Inbox & ingestion**
- **Goal**: Turn a week of links into clean source text.
- **Scope**: Read Gmail label; fetch/extract articles; fetch YouTube transcripts with fallback.
- **Success signal**: Given a week's links, produces a text file per source with URL and title.

**Phase 3: Voice writer & critic**
- **Goal**: Drafts that sound like Varun.
- **Scope**: Writer and critic sub-agent prompts; critic checklist from style guide.
- **Success signal**: Blind comparison - Varun rates a sample draft as "sounds like me" with light edits.

**Phase 4: Editor orchestration (MVP)**
- **Goal**: End-to-end draft from one command.
- **Scope**: Lead agent planning + delegation; Markdown draft with sources.
- **Success signal**: Two consecutive real issues need ≤30 min of edits.

**Phase 5: Schedule & delivery**
- **Goal**: Hands-off weekly draft.
- **Scope**: Managed Deep Agents deploy + Friday cron; optional `python-substack` draft.
- **Success signal**: Draft appears on schedule without manual trigger.

### Parallelism Notes

Phases 2 and 3 are independent once the foundation exists - ingestion produces text, the writer consumes text - so they can be built concurrently and joined in Phase 4.

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Approval model | Agents draft, Varun approves | Fully automatic | Final opinions are his; protects voice |
| Framework | LangChain `deepagents` (Python) | Claude Agent SDK, custom | Owner wants to learn deep agents; planning/sub-agents/filesystem built in |
| Hosting | LangSmith Managed Deep Agents (free tier) | Laptop cron, GitHub Actions | Owner's choice; local-first until validated |
| Hosting (2026-11-03) | Laptop scheduler (launchd/cron) running `newsletter-machine weekly` | Managed Deep Agents (deploy files kept in repo) | MDA cron needs LangSmith Plus ($39/seat/month), over budget; owner wants to run locally and pay nothing beyond API usage for now |
| Link inbox | Gmail: email links to `varunbhanot+newsletter@gmail.com` (filter → label) | Notion, Telegram bot, repo file | "Most convenient, nothing fancy": works from any phone/desktop share sheet, no new app or bot |
| v1 output | Markdown draft + sources | Direct Substack draft | No official Substack API; unofficial one may break |
| Evals | Deferred | DeepEval | Owner: "forget evals for now" |
| Growth target | v1 = content-only baseline (≥+30/month); 1,000 via later distribution add-on | 1,000 ASAP in v1 | Measure what consistent content alone does before adding distribution |

---

## Research Summary

**Market Context**
Hobbyist newsletter pipelines converge on gather → score → research → draft → review → publish (e.g. Paxrel's autonomous pipeline). Voice consistency, not research, is the recurring hard problem; grounding in real samples plus human review is the common fix. No mature open-source voice-matched newsletter tool was found - building is justified.

**Technical Context**
`deepagents` provides planning, sub-agent delegation, virtual filesystem and detailed prompts, modelled on Claude Code, and supports Anthropic models. Managed Deep Agents supports code-defined cron schedules but is in beta; cron may require a paid tier. Substack has no official API; `python-substack` (unofficial) can create drafts from Markdown with password auth. Repo is greenfield (README only).

Sources: docs.langchain.com/oss/python/deepagents; docs.langchain.com/langsmith/python/managed-deep-agents-tutorial; langchain.com/pricing; pypi.org/project/python-substack; dev.to/paxrel; dev.to/michael_xero_ai.

---

*Generated: 2026-11-02*
*Status: DRAFT - needs validation*
