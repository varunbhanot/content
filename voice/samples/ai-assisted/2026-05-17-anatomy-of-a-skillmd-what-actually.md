---
title: "Anatomy of a SKILL.md - What Actually Changed Since October 2025"
subtitle: ""
date: 2026-05-17
url: https://varunbhanot.substack.com/p/anatomy-of-a-skillmd-what-actually
words: 1347
era: ai-assisted
---

# Anatomy of a SKILL.md - What Actually Changed Since October 2025

Earlier [article](https://varunbhanot.substack.com/p/day-43-claude-skills-why-structured) covered what Claude Skills are and why structured workflows beat prompt engineering. Today starts a 30-day deep dive into actually building and shipping them - starting with the spec itself. Because most of what’s been written about Skills is describing October 2025. The docs have been quietly updated since then, and seven things changed.

[![](https://substackcdn.com/image/fetch/$s_!ybwu!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff257bcd1-ddfd-4090-9acc-fefc7011082e_2160x1215.png)](https://substackcdn.com/image/fetch/$s_!ybwu!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff257bcd1-ddfd-4090-9acc-fefc7011082e_2160x1215.png)

Let’s get precise.

### **What most builders think a SKILL.md looks like**

Search for “Claude Skills tutorial” and you’ll find the same structure everywhere:

```
name: my-skill

description: What this skill does

---

# My Skill

Instructions here.
```

That’s the minimum viable SKILL.md. It worked in October 2025 and it still works today. But it’s missing every feature that makes the difference between a skill that works for you and a skill you can actually ship.

The uncomfortable truth: the ecosystem of tutorials, YouTube walkthroughs, and Medium guides are mostly teaching the launch version. The platform docs have moved on.

Here’s what the spec actually looks like in May 2026.

## **The anatomy, field by field**

**Level 1 - What’s always loaded (the frontmatter)**

Every time Claude starts a session, it loads the `name` and `description` of every installed skill into its system prompt. This is the only content that costs tokens before any skill is triggered - approximately 100 tokens per skill. So you could theoretically install 50 skills and pay ~5,000 tokens upfront, with the rest loading on demand.

The frontmatter requirements are stricter than most tutorials show:

```
name: contract-review

description: Summarize a contract into a 1-page risk brief with red flags and suggested edits.

Use when a user provides a contract (PDF, DOCX, or text) and asks for review,

risks, or negotiation language. Do not use for general legal questions.
```

**Constraints the docs added since launch:**

- name: max 64 characters, lowercase letters and hyphens only. Cannot contain the words `anthropic` or `claude` - Claude Code will refuse to load the skill.

- description: max 1,024 characters, no XML tags. This is the field doing the routing work - we’ll come back to it in Day 52.

**The optional frontmatter fields most builders don’t know exist:**

```
---

name: pr-review

description: Review a pull request for quality, security, and style. Use when asked to review

a PR or check code changes.

allowed-tools: [Read, Bash, Glob, Grep]

agent: claude-code-explore

---
```

**allowed-tools** - grants automatic approval for these tools when the skill runs. The model won’t pause to ask permission. Note: this grants approval, it does not restrict. Any tool not listed can still be used - it just requires confirmation. Day 58 covers the security implications of this distinction in detail.

**agent** - runs the skill in a subagent instead of the main session. The subagent spins up, executes the skill’s instructions, and returns a result. The main session never sees the intermediate steps. Useful for research tasks that would clutter the primary context. Claude Code-specific extension, not part of the base agentskills.io open standard.

**disable-model-invocation: true** - prevents Claude from triggering the skill automatically. Only the user can invoke it via `/skill-name`. Useful for skills that should never fire by accident - a deployment script, a database migration helper.

**Level 2 - What loads when you trigger it (the body)**

Once Claude decides a skill is relevant, it reads the full body of SKILL.md into context. The Platform docs now document the token cost explicitly: under 5,000 tokens. That’s the soft guidance for a lean SKILL.md body - if you’re creeping toward 5K, it’s a signal to split into reference files.

The body should contain procedural knowledge: workflows, best practices, step-by-step guidance. Not encyclopedic knowledge - that belongs in reference files.

```
---

name: eval-pipeline-setup

description: Set up a production eval pipeline. Use when the user asks to build

  evals, set up evaluation infrastructure, or measure model output quality.

allowed-tools: [Read, Write, Bash, Edit]

---

# Eval Pipeline Setup

## Quick start

Run the eval audit first:

> /evals-skills:eval-audit

If audit passes, proceed to Step 2.

## Step 1 - Define failure taxonomy

Before writing a single eval, categorize your failure modes by reading 50 real

conversations. Look for patterns. See [TAXONOMY.md](TAXONOMY.md) for a template.

## Step 2 - Build the labelling set

...
```

Notice the reference to **TAXONOMY.md** - that’s a Level 3 file. Claude reads it only when reaching Step 1, not before.

**Level 3 - What loads as needed (bundled files)**

This is where the October 2025 launch and the May 2026 docs diverge most significantly. The current docs break bundled content into three distinct types:

**Instructions** - additional markdown files (`REFERENCE.md`, `FORMS.md`, `TAXONOMY.md`) containing specialized guidance. Claude reads them via bash when the main SKILL.md references them.

**Code** - executable scripts that Claude runs at its discretion. The key insight: when Claude runs `validate\_form.py`, the script’s code never enters the context window. Only the output does. A 500-line validation script costs the same in tokens as a single `echo “Validation passed”` call.

**Resources** - reference materials that don’t execute: database schemas, API documentation, example files, templates.

[![](https://substackcdn.com/image/fetch/$s_!bcOZ!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F035b10ee-c8a0-40cd-bc94-a2e4b86330f5_2816x1536.png)](https://substackcdn.com/image/fetch/$s_!bcOZ!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F035b10ee-c8a0-40cd-bc94-a2e4b86330f5_2816x1536.png)

The “effectively unlimited” token cost for Level 3 is real. A skill can bundle comprehensive API documentation, large example sets, and multiple scripts - none of it costs tokens until accessed. This is what makes Skills qualitatively different from long system prompts.

## **The three changes that matter most since October 2025**

**1. Custom commands merged into skills**

This is the quietest and most significant change. A file at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md` now create the same `/deploy` slash command and behave identically. Your existing command files keep working - they’ve been silently upgraded.

The practical implication: if you have a `.claude/commands/` folder full of procedures you’ve been maintaining as markdown files, those are already skills. You just don’t have the directory structure for Level 3 files yet.

[![](https://substackcdn.com/image/fetch/$s_!J8pG!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ffc8403f3-9b01-4515-9360-853529557c1a_2816x1536.png)](https://substackcdn.com/image/fetch/$s_!J8pG!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ffc8403f3-9b01-4515-9360-853529557c1a_2816x1536.png)

**2. Three invocation surfaces for Claude Code**

The original launch described skills as “model-invoked” - Claude decides when to trigger them based on the description. The current Claude Code docs distinguish three modes:

- **Auto-invoked** (default): Claude reads the description and decides when to use the skill

- **User-invoked via slash command**: `disable-model-invocation: true` in frontmatter. Only `/skill-name` triggers it.

- **Mixed**: The skill can be triggered either way, but auto-invocation requires explicit keywords

This matters for deployment scripts and production operations where accidental triggering has real consequences.

**3. Live change detection**

Claude Code now detects changes to SKILL.md files without restarting the session. Edit a skill while Claude is running, save the file, and the next session turn picks up the changes. This makes skill development significantly faster - you can iterate on a description, test a trigger, adjust, test again, all in the same session.

[![](https://substackcdn.com/image/fetch/$s_!TlgO!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fbeb26ced-f2c1-4e42-88b6-46d496cb3f68_2816x1536.png)](https://substackcdn.com/image/fetch/$s_!TlgO!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fbeb26ced-f2c1-4e42-88b6-46d496cb3f68_2816x1536.png)

This table is the most useful thing to have in your head when designing a skill. If your SKILL.md body is 8,000 tokens, split it. If your reference documentation is 50,000 tokens, that’s fine - it lives in Level 3 and costs nothing until someone needs it.

### **What this changes for how you write skills**

Skills beat prompt engineering for repeatability. Today’s anatomy post changes how you design them:

**The frontmatter is a routing contract, not a label.** Every word in `description` is doing routing work. Claude is pattern-matching your user’s intent against that description at session start, before any conversation happens. Write it as a trigger condition, not a summary.

**The body is a procedure, not a reference.** Keep it under 5,000 tokens. Anything factual or detailed that doesn’t need to load every time the skill fires - move it to Level 3. The body should tell Claude what to do. The reference files should tell Claude the facts needed to do it.

**Level 3 is underused.** Most of the skills in community marketplaces pack everything into SKILL.md. That’s the October 2025 approach. The current spec gives you an effectively unlimited reference layer that costs nothing until accessed. Use it.

Tomorrow we go deeper on the single design decision that makes all of this work: progressive disclosure. Why loading context in tiers is qualitatively different from loading it all upfront - and what that means for how you structure any long or complex skill.
