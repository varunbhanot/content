# Series Mode

## Problem Statement

Varun writes multi-part series (Harness Engineering Parts 1–4, #75DaysofGenerativeAI), and series are where his newsletter grows: readers and subscriptions rise by the end of a series. But the machine only knows single weekly issues. The series outline, what each published part said, and what the last part promised "next" all live in Varun's head and get rebuilt by hand every week. The next series, on evals, starts this week.

## Evidence

- Varun's observation: readers and subscriptions increase by the end of a series. (Baseline numbers TBD: pull from Substack stats for the Harness Engineering run.)
- Past series parts follow a consistent shape the machine does not produce: a link back to the previous part with its core claim in one sentence, mid-article callbacks ("That is what makes Part 1's vendor independence real in practice"), and a specific italic "Next in this series" teaser that the following part must honour (`voice/samples/ai-assisted/2026-07-22-harness-engineering-part-2-the-four.md:12,50,100`).
- Today a run is steered by one optional `--angle` string (`writer.py:83`); the scheduled weekly run always passes none (`weekly.py:84-87`). There is no series state anywhere in the code.
- Market: Substack creator advice consistently recommends series for retention and growth, including a free Part 1 as a funnel. Anecdotal only; no rigorous data found.

## Proposed Solution

Add a series layer on top of the existing issue pipeline. `series plan <topic>` reads the last few weeks of already-ingested sources and proposes an outline (parts, each with a basic-to-advanced arc and a free/paid flag). Varun approves it with `series approve`. From then on, `issue --series <slug>` drafts the next part: this week's links are filtered to the series topic (off-topic ones are set aside, not used, but kept for later), and the outline, this part's brief, and one-line summaries of earlier parts are injected wherever `--angle` goes today. When a week's links don't fit the planned part, the remaining outline adjusts. Series state lives in one human-readable file in the repo. This reuses the whole research → write → critique → revise pipeline instead of building a new one.

## Key Hypothesis

We believe a machine-proposed, Varun-approved series outline plus series context on every run will produce coherent series parts with less hand work for Varun as he writes up what he is studying.
We'll know we're right when evals parts need fewer edits than single issues, readers stay through the whole series, and the evals series ends with more subscribers than it started with.

## What We're NOT Building

- Deciding whether a topic deserves a series at all - a later feature, once series mode exists.
- Publishing or paywalling on Substack - stays manual; the machine only marks parts free/paid and keeps creating unpublished drafts.
- Multiple concurrent series - one active series at a time keeps the weekly run unambiguous.
- A course product (bundles, enrolment, drip email) - free-Part-1-then-paid is handled by the free/paid flag; anything more is out.
- Automatic discovery of published URLs - Varun records them with a command; RSS lookup can come later.

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Edits per series draft | Fewer than a single-issue draft (baseline TBD) | Diff between machine draft and published text, per part |
| Series completion by readers | Open rate on last part ≥ open rate on Part 1 (TBD) | Substack post stats per part |
| Subscriber growth over the series | Net gain from Part 1 to last part above Varun's normal weekly rate (TBD) | Substack subscriber count at each part's publish date |
| Part 1 shipped on time | Evals Part 1 drafted by end of this week | `drafts/<date>.md` exists |

## Open Questions

- [ ] Baselines: edits per draft and subscriber growth during Harness Engineering - pull from Substack.
- [ ] How reliable is the per-source relevance check? Wrongly dropped links would thin a part.
- [ ] Should parked (off-topic) links seed the *next* series plan automatically?
- [ ] If an adjusted outline grows past ~6 parts, should the machine propose ending the series instead?

---

## Users & Context

**Primary User**
- **Who**: Varun, sole author of *Beyond the AI Demo*, studying a topic week by week and emailing himself the links he reads.
- **Current behavior**: Drafts each series part with the machine as a standalone issue, then rebuilds the recap, callbacks and next-part teaser by hand.
- **Trigger**: After a few weeks of links he notices a pattern ("this is an evals series") and wants it planned.
- **Success state**: An approved outline, and each week a draft of the next part that already knows what earlier parts said and promised.

**Job to Be Done**
When I'm working through a topic like evals week by week, I want the machine to keep the series plan and what each published part said, so I can approve a coherent next part from this week's links without rebuilding the context by hand.

**Readers (the audience, not the operator)**
Same audience as single issues. Readers who want a structured, course-like path are a welcome target: a free Part 1 can funnel them into paid later parts.

**Non-Users**
Guest writers and other newsletters: the pipeline is built around Varun's voice corpus.

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | `series plan <topic>` from the last N weeks of saved sources | The outline is the thing Varun currently holds in his head |
| Must | `series approve` locks the outline | Varun approves; the machine proposes |
| Must | `issue --series <slug>` drafts the next part with series context | The core weekly loop |
| Must | Per-source relevance filter: off-topic links not used, but kept | Varun's rule: only series-related links feed a series part |
| Must | Each part goes basic → advanced within itself | Matches how Varun writes; a series is not "Part 1 easy, Part 4 hard" |
| Should | Earlier parts carried forward (one-line summary, teaser promised) | Enables the one-clause recap and mid-article callbacks |
| Should | Outline adjusts to the week's links | Varun's choice when links don't fit the planned part |
| Should | `series published <n> <url>` | Links back to the previous part need the live URL |
| Should | Scheduled weekly run picks up the active series | The weekly run is how issues actually get made |
| Could | Critic checks continuity (teaser honoured, recap one clause) | Extends the existing checklist |
| Could | Generate the "Next in this series" teaser from the outline | Saves a hand edit each week |
| Won't | Series-worthiness check, multi-series, publish/paywall | See "What We're NOT Building" |

### How the machine decides what a series looks like

The planner follows these rules, written into its prompt:

1. **Cluster the collected sources** into the distinct questions they answer (e.g. "why evals", "building a golden set", "LLM-as-judge", "evals in CI").
2. **One part = one reader question**, answerable in a ~1,000-word post (the style guide's length).
3. **Order by dependency**: a part comes after any part whose ideas it needs.
4. **Every part runs basic → advanced** on its own question, so a reader can join at any part.
5. **Part 1 frames the problem** with the widest appeal (demo vs production) and is marked free; deeper, hands-on parts are candidates for paid.
6. **3–6 parts.** Fewer is a single issue; more needs a split into two series.
7. **Each part notes source coverage** (which collected sources support it) and flags thin parts that need more reading.

### MVP Scope

Must-haves only, enough to draft evals Part 1 this week: `series plan`, `series approve`, `issue --series` with the relevance filter and part brief injected. Continuity, adjustment and the weekly hook follow before Part 2.

### User Flow

1. `series plan evals --since 28d` → writes `series/evals.yaml` (status `proposed`) and prints the outline.
2. Varun edits the file if he wants, then runs `series approve evals`.
3. `issue --series evals --since 7d --out drafts/<date>.md` → filters this week's links, drafts the next planned part, records the draft against that part.
4. After publishing: `series published evals 1 <url>`.
5. Next week the scheduled run does step 3 automatically.

---

## Technical Approach

**Feasibility**: HIGH. Series mode plugs into the existing input seams; the research/write/critique pipeline is reused unchanged.

**Architecture Notes**
- **Series state**: `series/<slug>.yaml`, committed (not under the git-ignored `drafts/`). Fields: topic, status (`proposed` / `approved` / `complete`), and per part: number, title, question, brief, basic→advanced arc, access (`free` / `paid`), status (`planned` / `drafted` / `published`), draft path, URL, one-line summary, teaser promised. Written atomically like other outputs (`drafting.py:63`).
- **Planning input**: past runs already save source text to `drafts/<date>.sources/` (`cli_issue.py:111-119`); `read_sources()` (`ingest.py:165`) loads them. No re-fetching.
- **Context injection**: series context goes where the angle goes today: `angle_line()` (`writer.py:83`) feeds the editor (`editor.md:25`), writer (`writer.md:36`) and researcher (`researcher.md:8`). The part brief also seeds the editor's `/plan.md`.
- **Relevance filter**: one cheap classification call per source against the series topic and outline, before the editor runs. Off-topic sources are excluded from the run but stay in `drafts/<date>.sources/`, and are listed in `drafts/<date>.parked.md` for future use.
- **Weekly run**: `weekly.py:84-87` builds `issue` args with no angle; it will read the single `approved` series, if any, and pass `--series`.
- **Voice**: the style guide already covers series openings, teasers and one-clause recaps (`style-guide.md:26,72,82`; `critic-checklist.yaml:134`).
- **Cost**: planning is a separate paid run (accepted). The relevance filter adds one small call per source.

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| A week's links don't fit the planned part | H | Adjust the remaining outline (Phase 4); until then, draft the part best supported by this week's on-topic sources and say so in the notes |
| Relevance filter drops a useful link | M | Parked list is printed every run; Varun can rerun with `--sources` |
| Too few on-topic links in a week | M | Notes flag a thin part; Varun decides to run or skip |
| Series file hand-edited into an invalid state | L | Validate on load with clear errors (exit 2, as elsewhere) |
| Deadline: Part 1 by end of week | M | Phases 1–2 only for Part 1; everything else lands before Part 2 |

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
| 1 | Series plan & approve | Series file format, `series plan` from saved sources, `series approve` | complete | - | - | [series-mode-phase-1-series-plan.plan.md](../plans/completed/series-mode-phase-1-series-plan.plan.md) |
| 2 | Draft a series part | `issue --series`: relevance filter, parked list, part brief injected, part marked drafted | complete | - | 1 | [series-mode-phase-2-series-draft.plan.md](../plans/completed/series-mode-phase-2-series-draft.plan.md) |
| 3 | Continuity | `series published`, part summaries, recap and teaser carried forward, critic checks | complete | with 4, 5 | 2 | [series-mode-phase-3-continuity.plan.md](../plans/completed/series-mode-phase-3-continuity.plan.md) |
| 4 | Outline adjustment | Re-plan remaining parts from the week's on-topic links; Varun re-approves | in-progress | with 3, 5 | 2 | [series-mode-phase-4-outline-adjust.plan.md](../plans/completed/series-mode-phase-4-outline-adjust.plan.md) |
| 5 | Weekly run integration | Scheduled run picks up the active series automatically | pending | with 3, 4 | 2 | - |

### Phase Details

**Phase 1: Series plan & approve**
- **Goal**: Turn a few weeks of collected links into an approved outline.
- **Scope**: `series/<slug>.yaml` schema with validation; `series plan <topic> [--since 28d]` reading `drafts/*.sources/` and applying the planning rules; `series approve <slug>`; `series show <slug>`.
- **Success signal**: An approved `series/evals.yaml` with 3–6 parts, each with an arc, free/paid flag and source coverage.

**Phase 2: Draft a series part**
- **Goal**: Draft evals Part 1 this week.
- **Scope**: `issue --series <slug>`; per-source relevance filter; `drafts/<date>.parked.md`; next planned part's brief and the outline injected via the angle seam; writer instructed to run basic → advanced; part status set to `drafted` with draft path.
- **Success signal**: `drafts/<date>.md` is a coherent Part 1 built only from on-topic sources; off-topic links are listed as parked.

**Phase 3: Continuity**
- **Goal**: Later parts read like a series, not standalone issues.
- **Scope**: `series published <slug> <n> <url>`; one-line summary and teaser extracted from each drafted part; previous part's URL, summary and teaser injected; critic checks the teaser is honoured and the recap stays one clause; closing teaser generated from the next planned part.
- **Success signal**: Part 2's draft links Part 1, recaps it in one clause, and delivers what Part 1's teaser promised.

**Phase 4: Outline adjustment**
- **Goal**: Let the outline follow what Varun actually read.
- **Scope**: When on-topic links fit a different or new part better, propose a revised remaining outline (published parts are frozen); Varun re-approves with `series approve`; the change is recorded in the file.
- **Success signal**: A week whose links don't match the planned part produces a revised outline proposal instead of a forced draft.

**Phase 5: Weekly run integration**
- **Goal**: The scheduled weekly run drafts the next part with no extra commands.
- **Scope**: `weekly` reads the single approved series and passes `--series`; the inbox email names the series and part, and lists parked links.
- **Success signal**: A scheduled run during the evals series delivers the next part to Gmail.

### Parallelism Notes

Phases 1 and 2 are sequential and are the critical path for this week's deadline. Phases 3, 4 and 5 touch separate seams (series file + prompts, planner, weekly runner) and can run in parallel once Phase 2 merges; all three should land before Part 2.

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Approval | CLI command (`series approve`) | Email reply, file-only | Varun's choice |
| Published URLs | Varun records them (`series published`) | Auto-discover via Substack RSS | Easiest; Varun was indifferent |
| Links that don't fit the planned part | Outline adjusts | Force the part, skip the week | Varun's choice |
| Off-topic links | Not used in the part; kept and listed as parked | Use as asides, drop | Varun's rule |
| Planning lookback | 28 days by default, `--since` to override | Fixed window | Series start after "a few weeks" of links |
| Concurrent series | One active series | Many | Keeps the weekly run unambiguous |
| Series state location | `series/<slug>.yaml`, committed | Under `drafts/` (git-ignored), database | Durable, reviewable, hand-editable |
| Context injection | Reuse the `--angle` seam | New pipeline stage | Reaches every agent with minimal change |
| Planning cost | Separate paid run | Fold into weekly run | Accepted by Varun |
| Series-worthiness check | Deferred | Build now | Varun: later feature |

---

## Research Summary

**Market Context**
Substack creator advice treats series as a retention and growth tool, with a free Part 1 as a funnel to paid parts; evidence is anecdotal ([willemtait](https://willemtait.substack.com/p/how-to-substack-think-in-series-write), [substackcourse](https://substackcourse.com/how-to-use-serialized-content-to-improve-my-substack-publications-readership-and-engagement/), [pulse.bot](https://www.pulse.bot/entertainment/blogs/how-to-grow-your-substack-in-2026-the-playbook-for-building-an-essential-newsletter-96cd7d1f-921c-4d8d-8205-66d991d8732a/)). AI tools that handle series are mostly fiction-focused and converge on: lock the outline first, keep an editable persistent series record, feed each run the outline + current brief + recent parts (not the archive), and flag contradictions for review ([Sudowrite](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/chapter-continuity/4KL8gFeLZQ6GSBjDWtSbV6), [Inkfluence](https://www.inkfluenceai.com/blog/can-ai-outline-and-write-chapters-in-sequence-2026), [Mem0](https://guide.mem0.ai/faq/what-software-helps-an-ai-storyteller-remember-previous-plot-points-and-character-names-bca047)).

**Technical Context**
Past sources persist per run in `drafts/<date>.sources/`; a single angle seam (`writer.py:83`) reaches every agent; the editor already writes a plan (`editor.md:25`); the weekly runner passes no angle (`weekly.py:84-87`); Substack integration only ever creates drafts. Series voice rules already exist in the style guide and critic checklist.

---

*Generated: 2026-11-03*
*Status: DRAFT - needs validation*
