---
title: "Skills, Slash Commands, MCP, Subagents — I Finally Know When to Use Which"
subtitle: ""
date: 2026-05-19
url: https://varunbhanot.substack.com/p/skills-slash-commands-mcp-subagents
words: 1239
era: ai-assisted
---

# Skills, Slash Commands, MCP, Subagents — I Finally Know When to Use Which

Skills are one of four distinct extension surfaces in Claude Code, and the number one mistake builders make is reaching for the wrong one. Not because they’re lazy, but because the layers sound interchangeable until you watch them fail.

[![](https://substackcdn.com/image/fetch/$s_!puvq!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd013a1ba-f951-4deb-a785-420552ce2483_2160x1215.png)](https://substackcdn.com/image/fetch/$s_!puvq!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd013a1ba-f951-4deb-a785-420552ce2483_2160x1215.png)

## The four surfaces, stated plainly

The mental model that finally clicked for me: **MCP is the plumbing**, connecting Claude to external services. **Skills are the instructions**, teaching Claude how to do something. **Slash commands are the trigger you control**, giving you explicit invocation with no guessing. **Subagents are parallel workers** with isolated context and concurrent execution.

Here’s how I think about them now:

![](https://substackcdn.com/image/fetch/$s_!EAAO!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F1be69f8b-1571-41e9-a53d-85a960da7de2_2930x600.png)

## The confusion that causes real failures

I built a `process-notes` skill a few months ago. Clean [SKILL.md](http://SKILL.md), tight description, the works. Then I noticed something: when I asked Claude to update my process notes, it wouldn’t use the skill. It would just read the file and update it directly. I had to explicitly say “update process notes and use your skill” every single time.

That defeated the point. So I moved it to a slash command, `/process-notes`, and the problem disappeared. I control invocation. No routing uncertainty. No “will it fire?” anxiety.

But that taught me something useful. The skill wasn’t wrong. It was in the wrong surface. I didn’t need auto-detection for that workflow. I needed explicit invocation with a clean trigger. The skill format was adding overhead (description matching, loading decisions) for a task where I always knew when I needed it.

The fix isn’t “always use slash commands.” The fix is understanding which surface each piece of knowledge belongs on. Skills stay for workflows that bundle code and benefit from auto-detection. Slash commands stay for procedures where I want to control the trigger. Different tools for different jobs.

[![](https://substackcdn.com/image/fetch/$s_!YQrh!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2a28683f-9cae-416c-a01f-bb4865a82980_2752x1536.png)](https://substackcdn.com/image/fetch/$s_!YQrh!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2a28683f-9cae-416c-a01f-bb4865a82980_2752x1536.png)

---

## When to reach for each surface

### [CLAUDE.md](http://CLAUDE.md): always-on preferences (Day 50’s “encoded preference”)

**Use when:** The knowledge is small (<200 tokens), fires on nearly every interaction, and the model must never skip it.

**Examples:** Commit message format. PR template structure. “Never use semicolons in this repo.” House TypeScript style deviations.

**Why not a Skill:** Day 50’s 30% rule. If it fires on more than 30% of session turns, the trigger-decision overhead exceeds the cost of having it always present. [CLAUDE.md](http://CLAUDE.md) costs those 200 tokens every turn, but it’s guaranteed to apply. A Skill with the same content might not fire.

**The trap:** Teams use [CLAUDE.md](http://CLAUDE.md) as a dumping ground. It grows to 5,000 tokens. Attention degrades. Keep it lean. Only rules that apply on *every* interaction belong here.

[Subscribe now](https://varunbhanot.substack.com/subscribe?)

---

### Slash commands: stored procedures you invoke yourself

**Use when:** You have a repeatable workflow, you want to decide exactly when it runs, and it doesn’t need bundled code or auto-detection.

**Examples:** `/deploy` to run a deployment checklist. `/headlines` to brainstorm title variants for a blog post. `/competitive-research` to spawn parallel agents to research competitors.

**Why not a Skill:** Slash commands give you explicit control over invocation. You type the trigger. No description-matching, no routing uncertainty, no “will it fire?” anxiety. I switched my process-notes workflow to a slash command specifically because the certainty was worth more than the auto-detection convenience.

**The trade-off:** Slash commands can’t bundle executable code in a structured way. They can *instruct* Claude to run scripts, but there’s no formal directory structure for reference files and code. Skills have that structure. If you need bundled code or multiple reference documents, a Skill is the right choice.

**Where they live:** `~/.claude/commands/` (global) or `.claude/commands/` (project). The name of the file becomes the slash command name.

---

### Skills: domain knowledge with progressive disclosure

**Use when:** The knowledge is large (>500 tokens of reference material), fires infrequently (<30% of turns), and benefits from bundled code or structured reference files.

**Examples:** PDF form-filling with Python scripts. IFRS contract review with a 50KB standard bundled as reference. An eval pipeline setup with taxonomy templates and scorer scripts.

**Why not [CLAUDE.md](http://CLAUDE.md):** Too large. It would bloat always-on context and degrade attention on unrelated turns. Progressive disclosure lets it cost ~80 tokens when dormant.

**Why not a slash command:** You want Claude to recognise when the skill is relevant without you having to remember to invoke it. A well-written description triggers automatically. Plus you need the directory structure for bundled code.

**The catch:** Auto-detection only works with a tight, specific description. Day 50 covered the 0% → 100% trigger-rate rewrite. If your description is “helps with documents,” a slash command might be a better bet until you invest in the routing predicate.

---

### MCP servers: connectivity to external services

**Use when:** Claude needs to *do* something in the outside world. Read GitHub issues, access Google Drive, query a database, interact with Slack.

**Examples:** GitHub MCP for reading issues and creating PRs. Google Drive connector for accessing shared documents. A custom MCP server wrapping your internal API.

**Why not a Skill:** Skills are instructions only. They cannot fetch data, call APIs, or connect to external services. If your problem is connecting Claude to an external service, Skills are the wrong tool. They shape behavior, not connectivity.

**The cost to know:** MCP servers announce their full tool schemas upfront. A five-server setup burns ~55,000 tokens of context overhead before you type a word. That’s a third of a 200K context window gone on declarations. Install only what you actively use.

**The complementary pattern:** Skills and MCP work together. The Skill tells Claude *how* to review a PR (the procedure, the checklist, the quality bar). The GitHub MCP Connector lets Claude *access* the PR to review it. Brain and hands.

---

### Subagents: parallel execution in isolated context windows

**Use when:** A task would pollute the main context with exploratory results, or you need multiple independent tasks running simultaneously.

**Examples:** Researching 15 competitors in parallel (each agent gets its own context window). Fact-checking different sections of an article concurrently. Deep web research where 20 search results shouldn’t clutter the main thread.

**Why not a Skill:** Subagents solve a different problem. Skills give Claude knowledge. Subagents give Claude parallelism and context isolation. A slash command might *spawn* subagents as part of its procedure, but the subagent is the execution layer, not the knowledge layer.

**The overhead:** Each subagent gets its own context window and burns tokens independently. On a Pro plan, running 15 agents in parallel can eat through your usage allocation fast. Use them for tasks where speed or context isolation is genuinely valuable, not as a default for every request.

[![](https://substackcdn.com/image/fetch/$s_!3CwN!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb0868ba6-08cc-40f8-9808-8fff20452a09_2752x1536.png)](https://substackcdn.com/image/fetch/$s_!3CwN!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb0868ba6-08cc-40f8-9808-8fff20452a09_2752x1536.png)

## The mistake that is common

The species problem from [yesterday](https://varunbhanot.substack.com/p/your-code-style-skill-is-making-claude) shows up here too. Teams build a Skill for their commit message format (30 tokens of instruction, fires on every commit) when it belongs in [CLAUDE.md](http://CLAUDE.md). They build a Skill for their deployment checklist (explicit invocation needed, no auto-detection value) when it belongs in a slash command. They expect a Skill to access their GitHub repo (connectivity problem) when they need an MCP server.

Each surface has a sweet spot. The sweet spot for Skills (large domain knowledge, infrequent triggers, bundled code, auto-detection value) is narrower than the hype suggests. That’s fine. The other surfaces exist precisely because not everything is a Skill problem.

Remember: the extension surface you reach for should match the knowledge type, not the feature that sounds most impressive.

Would love to hear which surface you use at what point?
