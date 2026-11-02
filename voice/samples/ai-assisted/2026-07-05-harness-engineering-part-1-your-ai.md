---
title: "Harness Engineering, Part 1: Your AI Investment Is an Infrastructure Bet, Not a Vendor Bet"
subtitle: ""
date: 2026-07-05
url: https://varunbhanot.substack.com/p/harness-engineering-part-1-your-ai
words: 1351
era: ai-assisted
---

# Harness Engineering, Part 1: Your AI Investment Is an Infrastructure Bet, Not a Vendor Bet

[![](https://substackcdn.com/image/fetch/$s_!0paj!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fa86d3e14-c479-406e-8e76-e2b7464a4664_1024x559.png)](https://substackcdn.com/image/fetch/$s_!0paj!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fa86d3e14-c479-406e-8e76-e2b7464a4664_1024x559.png)

Most teams evaluate AI coding tools by comparing models. Claude vs GPT vs Gemini. Benchmark scores, context windows, pricing per million tokens. An engineer runs the same prompt through three providers, eyeballs the output, picks the one that “feels” best. Leadership signs the contract.

Six weeks later the agent hallucinates a dependency that doesn’t exist. It applies a database migration to the wrong environment. It generates code that passes basic tests but violates an architectural boundary nobody wrote down. And the instinct is always the same: blame the model.

You swap providers. You upgrade to the latest model. The same class of failures keeps showing up because the model was never the problem.

## **The equation that matters**

Agent = Model + Harness

The model is one input into a running agent. Everything else, the prompts, the tools, the context policies, the hooks, the sandboxes, the sub-agents, the observability, is the harness. The scaffolding wrapped around the model that lets it actually finish something.

A raw model is not an agent. It becomes one when a harness gives it state, tool execution, feedback loops, and enforceable constraints. The behaviour you experience when working with Claude Code, Cursor, Codex, or Aider is dominated by what the harness does, not which model sits underneath.

The split is roughly 90/10.

On Terminal Bench 2.0, one team moved a coding agent from outside the Top 30 to the Top 5 by changing only the harness. Same model. A separate study at LangChain raised an agent’s score on the same benchmark by 13.7 points by tweaking only the system prompt, tools, and middleware around a fixed model. No model upgrade, no fine-tuning, just better configuration.

When an agent does something wrong, the failure more often traces to a missing tool, a vague rule, an absent guardrail, or a context window stuffed with noise. Most agent failures, examined honestly, are configuration failures.

## **What the harness actually contains**

Concretely, a harness includes the instructions and rule files that define who the agent is, what it cares about, and what it cannot do ([AGENTS.md](http://agents.md/), [CLAUDE.md](http://claude.md/), [GEMINI.md](http://gemini.md/), skill files, sub-agent prompts). It includes the tools the agent can call: functions, MCP servers, APIs, plus the prose around them that tells the model when and how to use each one.

This is where the “treat tool descriptions like API contracts, not prompt copy” insight hits hardest. A well-designed tool interface makes the model reliable. A vague one makes it creative in the wrong places.

Beyond tools, the harness includes sandboxes and execution environments (where the agent’s code runs, what it can reach, what it cannot), orchestration logic (sub-agent spawning, model routing, hand-offs between specialists), guardrails and hooks (deterministic code that fires at lifecycle points: before a tool call, after a file edit, before a commit), and observability (logs, traces, evaluations, cost metering).

Hooks are worth singling out. They exist for things the agent should never forget but often does. “Don’t push secrets.” “Run the linter before committing.” “Check whether this file is in the migration path.” You could put these in the system prompt and hope. Or you could make them deterministic.

That is a lot of surface area, and it belongs to your team. Not the model provider.

[![](https://substackcdn.com/image/fetch/$s_!QYu9!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff2c8b8ad-a2f0-4cf5-8961-aaa105376d2f_1024x559.png)](https://substackcdn.com/image/fetch/$s_!QYu9!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff2c8b8ad-a2f0-4cf5-8961-aaa105376d2f_1024x559.png)

## **The hierarchy that cuts through the buzzword pile**

The confusion is real. Prompt engineering, context engineering, harness engineering, agentic workflows, loop engineering. Every month adds a new term and everyone acts like it replaces the last one.

They don’t replace each other. They stack:

Prompt engineering is what you say to the model in a single turn. Context engineering is what you feed the model, structured so it can actually use it. Harness engineering is the system that governs what the model can do, when, and under what constraints. Loop engineering is how that system iterates, self-corrects, and escalates across multiple cycles without you in the chair.

Each layer answers the failures of the layer below. Prompt engineering breaks when the model doesn’t have enough context. Context engineering breaks when the model has too much autonomy and no guardrails. Harness engineering breaks when the system needs to run unsupervised for longer than a single turn. You don’t graduate from one to the next. You build upward.

## **The CI/CD analogy**

Your developers didn’t get better at shipping by writing better code. They got better because you built pipelines, gates, staging environments, rollback mechanisms. You invested in the system around the code, not the code itself.

Harness engineering is that discipline applied to AI agents doing work inside your org.

A solo developer’s harness is a [CLAUDE.md](http://claude.md/) file and good habits. That works at personal scale. An enterprise harness is RBAC for tool access, audit trails, approval chains, shared context across teams, observable failure modes, and versioned configurations that don’t drift when forty teams each customize their layer.

Without it, you get forty teams each vibe-coding their own brittle wrapper around the same model. Each one breaks differently. Nobody can debug anyone else’s setup. Knowledge stays trapped in individual sessions. The agent starts cold every time.

This works for prototypes. It breaks at organizational scale.

## **Vibe coding vs. agentic engineering**

The transition from vibe coding to agentic engineering is not about which tools you use. A developer can vibe code or practice agentic engineering using the exact same agent. The difference is how deliberately they configure the harness.

Vibe coding relies on minimal scaffolding aimed at speed. The developer prompts, accepts output, ships. Low friction, fast results, no upfront investment. Agentic engineering relies on extensive harness abstractions that guide the AI from the first planning document through to production monitoring. Higher upfront cost, but the marginal cost per feature drops fast.

Here is why the distinction matters in practice: telling a CTO that your team is vibe coding their payment processing system will, and should, raise alarm bells. Telling that same CTO your team practices agentic engineering, with AI handling implementation under human-designed constraints while test coverage ensures correctness, is a fundamentally different conversation. Both use the same models.

## **The economics**

Vibe coding is low CapEx, high OpEx. Cheap to start, expensive to maintain. Every interaction burns tokens with low first-pass success rates. Code lacks structural consistency. Six months later an engineer spends days reverse-engineering AI-generated spaghetti to fix a bug nobody remembers writing. The cost compounds quietly until someone notices the maintenance budget has doubled.

Agentic engineering flips that. High CapEx (context hierarchies, tool governance, eval suites, observability up front), low OpEx (once the harness exists, each new feature costs less to ship and maintain because the AI operates within a governed factory, its output pre-tested and aligned with team standards before a human ever reviews it).

After enough features shipped, the vibe coding path costs 3-10x more per feature. We’ve watched teams hit this crossover point around month four or five. The ones that invested early compound quality quietly. The ones that didn’t keep asking why everything feels so brittle.

[![](https://substackcdn.com/image/fetch/$s_!DOKi!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fa6b430c1-4bac-4711-9c28-f862248572c9_1024x559.png)](https://substackcdn.com/image/fetch/$s_!DOKi!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fa6b430c1-4bac-4711-9c28-f862248572c9_1024x559.png)

## **Why now**

Models crossed the capability threshold in 2025. They generate Terraform plans, write migrations, draft PRs, plan multi-file changes, execute them in sandboxes, run test suites, and submit pull requests without a human typing a line of code.

The bottleneck moved. It’s no longer “can the model do it” but “should it, and who decides.”

85% of professional developers now use AI coding agents regularly. 51% use them daily. An estimated 41% of all new code is AI-generated. This isn’t a forecast. It’s what’s happening in engineering orgs right now.

The companies that pull ahead over the next eighteen months won’t be the ones who picked the best model. They’ll be the ones who built the best system around whichever model they chose. Models are commoditizing fast. GPT-5, Claude Opus, Gemini Ultra will all handle most tasks competently. What won’t be equivalent is the harness each team built, and that’s a much harder thing to copy.

[![](https://substackcdn.com/image/fetch/$s_!SyE0!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd81b1d1c-db65-4be1-ad25-2707fc50c77f_1024x559.png)](https://substackcdn.com/image/fetch/$s_!SyE0!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd81b1d1c-db65-4be1-ad25-2707fc50c77f_1024x559.png)

---

*Next in this series: the four layers of a production harness, mapped to the SDLC phases you already understand.*
