---
title: "The Skill Nobody Builds First (And Why Anthropic Says It Should Be)"
subtitle: ""
date: 2026-06-14
url: https://varunbhanot.substack.com/p/the-skill-nobody-builds-first-and
words: 1107
era: ai-assisted
---

# The Skill Nobody Builds First (And Why Anthropic Says It Should Be)

[![](https://substackcdn.com/image/fetch/$s_!zAI5!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F98f03be2-1bb7-4ef0-a67f-0be5705656a1_2160x1215.png)](https://substackcdn.com/image/fetch/$s_!zAI5!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F98f03be2-1bb7-4ef0-a67f-0be5705656a1_2160x1215.png)

I have been building agentic skills for months now. Scaffolding scripts, automation templates, review hooks, the whole pipeline. I thought the ROI was in the generation: the code that writes code, the workflow that replaces the standup post.

Turns out, I had it backwards.

Last week, Anthropic’s Claude Code team published their [internal field report.](https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills) Thariq Shihipar laid out hundreds of skills they run in production, categorized into nine buckets. But one line buried in the middle stopped me cold:

> “Verification skills have had the most measurable impact on Claude’s output quality internally. It can be worth having an engineer spend a week just making your verification skills excellent.”

A full engineer-week. Not on a generation skill. Not on a deployment hook. On the skill that checks whether the other skills actually worked.

That hit me because we literally covered this two weeks ago, the gap between “the skill ran” and “the skill ran correctly.” Anthropic just confirmed it is the highest-leverage problem in the entire ecosystem. And they solved it with a pattern most of us are not building yet.

**What the 9 categories actually tell you**

The taxonomy itself is clean: Library reference, Product verification, Data fetching, Business automation, Scaffolding, Code review, CI/CD, Runbooks, Infrastructure. But the principle behind it matters more than the list:

> “The best skills fit cleanly into one; the ones that try to do too much straddle several and confuse the agent.”

Here is the gut check: the skill you are most proud of probably spans three categories. Mine did. I had a “deploy and verify” monolith that handled CI, babysat the PR, and checked the health endpoint. Anthropic’s data says that confusion is exactly what degrades routing accuracy. The model does not know which trigger to trust when a skill does too much.

[![](https://substackcdn.com/image/fetch/$s_!-kG0!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F67a9dd25-890b-434e-8707-18867f57d041_1254x1254.png)](https://substackcdn.com/image/fetch/$s_!-kG0!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F67a9dd25-890b-434e-8707-18867f57d041_1254x1254.png)

**Verification is not a checklist, it is a harness**

When Anthropic says “verification,” they do not mean “ask Claude if it looks good.” They mean:

* Record video of the output so you can see what it actually tested
* Enforce programmatic assertions at every state transition
* Use Playwright for browser flows, tmux for CLI interactions that need a TTY

It is a deterministic test harness wrapped in natural language. Not “did it work?” but “here is exactly how we prove it worked, and the skill fails if the proof fails.”

That inverts the build order most teams follow. The natural instinct is generation first, verification later. Anthropic’s production data says verification first makes every other skill trustworthy. Without it, you are just generating faster mistakes.

**Three things that contradict the advice you have been reading**

*“Avoid railroading Claude.”*

Every guide says Step 1, Step 2, Step 3. Anthropic says the opposite: give the goal and constraints, then let the model navigate. Their example is a cherry-pick skill. The bad version lists exact git commands. The good version says: “Cherry-pick the commit onto a clean branch, resolve conflicts preserving intent. If you cannot land cleanly, explain why.”

Same outcome. Radically different resilience. The prescriptive version breaks the moment the commit graph surprises you. The flexible version survives the edge case because you stated what good looks like, not how to get there.

*“Gotchas are the highest-signal content.”*

Not the instructions. The warnings.

> “The subscriptions table is append-only. The row you want is the one with the highest version, not the most recent created\_at.”  
> “Staging returns 200 even when the Stripe webhook did not actually process. Check payment\_events for the real state.”

Three lines. Two hours of debugging saved. Every single time. Anthropic builds these iteratively: hit a failure, add the gotcha, repeat. The best internal skills started tiny and accumulated specificity from scars, not speculation.

*“Write descriptions for the model, not humans.”*

The description field is a trigger contract, not a summary. Anthropic’s own example: a skill uses “babysit” in its description because that is the word users type when they want Claude to watch a PR through CI. Not “monitors pull requests for continuous integration status.” The word the human says, not the phrase the human would write in a spec.

[![](https://substackcdn.com/image/fetch/$s_!DKRW!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe9992647-ee6c-4bc3-8f01-b5e03b234bf4_1402x1122.png)](https://substackcdn.com/image/fetch/$s_!DKRW!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe9992647-ee6c-4bc3-8f01-b5e03b234bf4_1402x1122.png)

**The folder is the skill**

This was the other realization that rewired how I am structuring my next skill. Skills are folders, not markdown files. The directory structure is a context engineering surface:

* `references/api.md` for deep function signatures loaded only when needed
* `assets/template.md` copied and filled, not generated from scratch
* `examples/good.md` and `examples/avoid.md` for positive and negative patterns
* `scripts/` for helper functions Claude composes at runtime
* Persistent state via `${CLAUDE_PLUGIN_DATA}` for logs, JSON, or SQLite

The `avoid.md` pattern is especially sharp. It is the gotchas section made concrete. Brock Mesarich’s example: an email drafter that includes `good-emails.md` (how I sound) and `avoid.md` (corporate templates, LinkedIn thought leader speak, AI assistant voice). Negative constraints are often more specific than positive ones.

They also use on-demand hooks. `/careful` blocks `rm -rf` and `DROP TABLE` only when touching prod, not globally. `/freeze` locks edits outside a directory during debugging. These are runtime permission modifiers, not instructions. Actual enforcement.

**How they grow the marketplace (and why most enterprises get this wrong)**

No central team approves skills. Someone builds it for themselves, drops it in a sandbox, mentions it in Slack. If it gets traction through usage, it graduates to the marketplace via PR. They track two signals: high trigger rate (good) and undertriggering relative to expectation (usually a bad description, the Day 54 failure mode).

For smaller teams, `.claude/skills/` in the repo works. For larger orgs, a plugin marketplace keeps context budgets under control. Every installed skill costs tokens in the listing.

**What I am changing next**

Five principles from the playbook that I am applying to my next build:

1. **Start with verification, not generation.** First skill proves correctness. The ROI is proven; no other category comes close.
2. **Lead with gotchas, not instructions.** Claude knows how to code. It does not know what is non-obvious about your codebase.
3. **One category only.** If it scaffolds, reviews, and deploys, split it into three. Multi-category skills confuse routing.
4. **Write descriptions as trigger contracts.** Use the verbs users actually say. “Babysit,” not “monitor CI status.”
5. **Use the filesystem for progressive disclosure.** The folder is the skill. `SKILL.md` is just the entry point.

[![](https://substackcdn.com/image/fetch/$s_!jX5T!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6d21037f-d88f-42d1-a51e-191f20e1e224_1402x1122.png)](https://substackcdn.com/image/fetch/$s_!jX5T!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6d21037f-d88f-42d1-a51e-191f20e1e224_1402x1122.png)

Next week, I am building a verification skill from scratch using exactly this pattern, the kind Anthropic says is worth an engineer-week. The kind most teams do not have yet.

If you are building skills too, my question is: which of your existing skills spans the most categories? That is probably the one to split first.
