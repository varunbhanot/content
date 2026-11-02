---
title: "Your Code Style Skill Is Making Claude Worse"
subtitle: ""
date: 2026-05-18
url: https://varunbhanot.substack.com/p/your-code-style-skill-is-making-claude
words: 1477
era: ai-assisted
---

# Your Code Style Skill Is Making Claude Worse

Yesterday we walked through the [anatomy of a SKILL.md](https://varunbhanot.substack.com/p/anatomy-of-a-skillmd-what-actually) - the three-tier loading model, what goes in frontmatter versus body versus bundled files. Today we break progressive disclosure open from a different angle. Not the mechanics. The failure modes. Because progressive disclosure doesn't always help and the teams that learn this the hard way share a common misunderstanding about what kind of skill they built.

[![](https://substackcdn.com/image/fetch/$s_!h6Tv!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F05374372-8a73-47ff-8a4d-53b70e5acd2c_2160x1215.png)](https://substackcdn.com/image/fetch/$s_!h6Tv!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F05374372-8a73-47ff-8a4d-53b70e5acd2c_2160x1215.png)

## **Anthropic’s buried distinction: capability uplift vs encoded preference**

Anthropic’s engineering blog distinguishes them quietly, without fanfare, in a single sentence buried in the “equipping agents for the real world” post: skills divide into **capability uplift** and **encoded preference**.

A capability-uplift skill teaches Claude something it can’t do natively. Parse a PDF. Review a contract against IFRS standards. Run an eval pipeline with your company’s specific taxonomy. The knowledge is large, domain-specific, and only needed when someone actually asks for the capability.

An encoded-preference skill captures how you want something done - not what. Your team’s commit message format. Your PR description template. Your house code style that deviates from the linter defaults in three specific ways. The knowledge is small, universal across tasks, and relevant on *every* interaction that touches code.

Progressive disclosure is perfect for one species and actively harmful for the other. That’s the split this article is about.

## **Capability uplift: the 80-token-to-7,000-token payoff curve**

Take Anthropic’s PDF skill as the clean example. The description field is ~80 tokens in the listing. The body loads only when someone says “fill this W-9.” The reference file `forms.md` loads only when the body says “see forms.md for field mappings.” The Python script `fill_form.py` executes without ever entering context - only its output does.

A session where no one mentions PDFs pays ~80 tokens for the skill’s existence. A session where someone fills three forms pays ~7,000. Same skill, two cost profiles, determined entirely by usage.

This is the textbook progressive-disclosure win. The economics only work because the capability is triggered infrequently and the reference material is large. If you have a 50KB IFRS standard bundled as Level 3 files, progressive disclosure means the buyer of your skill pays for storage, not for tokens. Runtime cost is the same as a trivial skill.

We covered this in [previous article](https://varunbhanot.substack.com/p/anatomy-of-a-skillmd-what-actually). No need to re-derive it. The point today is that this beautiful economics has a precondition most builders ignore: **the skill must fire infrequently relative to total session turns.**

---

## **Encoded preferences: when on-demand loading costs more than always-on**

Now take the opposite case. You build a skill called `commit-style` with this description:

```
description: Format commit messages using conventional commits with scope,
  body wrapping at 72 chars, and footer references to Linear tickets.
```

Progressive disclosure says: load the body only when the user asks for a commit message. In theory, efficient. In practice, a developer using Claude Code makes 15-30 commits per session. The skill fires on nearly every interaction. The body loads, gets used, potentially exits context, loads again on the next commit.

Worse - if your preference skill is thin enough (under 200 tokens of actual instruction), the overhead of *triggering* it - Claude reading the description, deciding it’s relevant, loading the body, applying the rules - can exceed the cost of just having those 200 tokens in the system prompt permanently.

Pere Villega calls this the “cheat sheet taped to your monitor” pattern. A cheat sheet works because it’s always visible. You don’t file it in a cabinet and retrieve it every time you need it - that defeats the purpose. Encoded preferences are cheat sheets. They need to be always-on.

[![](https://substackcdn.com/image/fetch/$s_!_bjg!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd88ee185-cec6-4542-9c8c-a18003f58251_2816x1536.png)](https://substackcdn.com/image/fetch/$s_!_bjg!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd88ee185-cec6-4542-9c8c-a18003f58251_2816x1536.png)

---

## **Vercel’s A/B test: Skills scored 56% where always-on context scored 100%**

Vercel ran an internal A/B test on their Next.js 16 API knowledge base. Three conditions:

* **AGENTS.md** (always loaded, passive context): **100% accuracy** on API knowledge tasks
* **Claude Skills with rich descriptions**: **79%**
* **Claude Skills with minimal descriptions**: **56%**

The Skills *lost*. Not because the content was worse - same knowledge, same coverage. Because the knowledge needed to be passively available for every API-related question, not gated behind a trigger decision. Every time Claude had to decide “is this relevant enough to load?” it sometimes decided wrong. And 21-44% of the time, that wrong decision meant the answer was worse than having the context always present.

This isn’t a failure of Skills. It’s a failure of using the wrong species. Vercel’s API knowledge is an encoded preference - “when you see a Next.js 16 API question, always answer using these updated signatures.” It belongs in always-on context. Progressive disclosure was the wrong tool for the job.

---

## **The 1% budget ceiling: 15-25 skills before silent truncation**

Here’s where it gets worse for teams that mix species without thinking about it. Claude Code allocates a fixed fraction of the context window - 1% by default, controlled by a hidden `skillListingBudgetFraction` setting - to skill descriptions at session start.

On a 200K-token context window, that’s ~2,000 tokens for all skill listings combined. Each skill costs 75-150 tokens in the listing. Do the math: **15-25 skills before silent truncation.** Not an error. Not a warning. Claude just stops seeing skills that don’t fit.

The ranking is recency and frequency weighted. Skills you trigger often stay visible. Skills you installed three weeks ago and never used drift to the bottom and eventually fall off. Experts field observation matches: “5-8 active skills per project before they start interfering with each other.” Beyond that, skills start competing for the description budget, and the model’s trigger accuracy drops.

This is the Monkey’s Paw. You asked for a system that doesn’t waste tokens on unused capabilities. You got it. The cost: when you install too many encoded-preference skills - the ones that *should* fire constantly - they compete for the same limited listing budget as your capability-uplift skills that fire rarely. The frequently-needed preferences crowd out the rarely-needed capabilities, and neither species works optimally.

---

## **From 0% to 100% trigger rate with one description rewrite**

Alireza Rezvani audited 235 production skills and found the most common failure: a skill with a vague description that never fires at all. His case study - a `security-audit` skill - had a 0% trigger rate with this description:

```
description: Helps with security-related code reviews.
```

After rewriting to include specific verbs, conditions, and exclusions:

```
description: Run OWASP Top 10 checks against modified files when a user asks
  for security review, penetration testing, or vulnerability scanning.
  Do not use for general code review or style checks.
```

Trigger rate jumped to 100% on relevant queries. The description isn’t a summary - it’s a routing predicate. Claude pattern-matches user intent against it at session start. Vague predicates match nothing reliably. Specific predicates fire precisely.

This matters more for capability-uplift skills than for encoded preferences. A capability skill that never triggers is invisible - zero value. An encoded-preference skill that doesn’t trigger is worse than invisible, because the user expects the preference to be applied and it silently isn’t. The commit messages come out in the wrong format. No error. No indication that the skill exists but didn’t fire.

---

## **The 30% rule: count triggers, then decide where knowledge lives**

If you hold both species in your head, a clean decision tree emerges:

**If the knowledge is large and fires infrequently** - capability uplift. Build it as a Skill with progressive disclosure. Put the heavy reference material in Level 3 files. Let it cost ~80 tokens when dormant and ~5,000 when active.

**If the knowledge is small and fires on nearly every interaction** - encoded preference. Don’t build a Skill. Put it in `CLAUDE.md` or `.claude/settings.json` or whatever always-on context your harness provides. Pay the 200-token cost on every turn. That’s cheaper than the trigger-decision overhead of loading it on demand.

**If you’re not sure** - count triggers. Run the skill for a week. If it fires on more than 30% of session turns, it’s a preference. Move it to always-on context. If it fires on fewer than 10%, it’s a capability. Leave it as a skill and invest in a sharper description.

The uncomfortable implication: some of the most popular community skills - code style enforcers, PR templates, test naming conventions - are the wrong species. They’re encoded preferences packaged as on-demand capabilities. They’d work better as three lines in CLAUDE.md. But “I wrote a Skill!” sounds more impressive than “I added a line to my config file.”

---

Tomorrow we put Skills in context with the other three customisation surfaces - slash commands, MCP servers, and subagents - and figure out which one to reach for when. The species distinction makes that decision much cleaner than it looks.

Remember: not every piece of knowledge wants to be loaded on demand. Some knowledge wants to be a cheat sheet taped to the monitor.
