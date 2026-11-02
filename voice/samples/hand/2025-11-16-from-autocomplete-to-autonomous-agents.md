---
title: "From autocomplete to autonomous agents: how the dev stack really changed (Day 44)"
subtitle: ""
date: 2025-11-16
url: https://varunbhanot.substack.com/p/from-autocomplete-to-autonomous-agents
words: 923
era: hand
---

# From autocomplete to autonomous agents: how the dev stack really changed (Day 44)

In a decade, coding tools jumped from inline hints to semi‑autonomous agents that plan, edit, test, and open PRs—shifting the bottleneck from typing speed to spec quality and review discipline.

[![](https://substackcdn.com/image/fetch/$s_!mOFB!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F56f6a6cd-be97-4c77-bdb8-aa98398fa76c_864x606.png)](https://substackcdn.com/image/fetch/$s_!mOFB!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F56f6a6cd-be97-4c77-bdb8-aa98398fa76c_864x606.png)

## TL;DR

* **Three modes**: IDE‑native, CLI‑first, and cloud agent platforms—choose based on feedback loop speed, repeatability, and governance needs.
* **Practical picks**: Copilot for inline speed; Cursor/Windsurf for multi‑file edits; Claude Code/Codex for scripted and CI use; GitHub Agent HQ for orchestrated cloud missions.
* **Action**: Start with bounded tasks, write mini‑spec prompts, and wire agents into lint/SAST/tests before they draft PRs.

## Why this matters now

Assistants have evolved from reactive suggestions to proactive execution: they plan tasks, run terminals/tests/linters, and draft PRs with checkpoints—compressing the SDLC and changing how teams design guardrails.

## Phase 0 → Phase 3, briefly

* Pre‑LLM: ESLint, SonarQube, CodeQL, Sourcegraph—useful hygiene/search, no task planning.
* Phase 1: Copilot/Tabnine predicted lines/blocks, cutting boilerplate and search hopping.
* Phase 2: Chat copilots (Copilot Chat, Cody, Continue, Amazon Q, Gemini) added repo‑aware Q&A, refactors, tests, and docs with larger context windows.
* Phase 3: Agent modes accept goals, decompose work, run tools, and iterate until checks pass—opening draft PRs for review.

# IDE vs CLI vs cloud

* **IDE‑native agents**: Work inside your editor for tight feedback loops, multi‑file diffs you can inspect visually, and chat/explain/test flows without leaving the IDE.

* **CLI‑first agents**: Run from the terminal or CI for scriptable, repeatable, policy‑enforced changes; ideal for batch refactors, test generation, and headless audits.

* **Cloud agent platforms**: Spin up ephemeral dev envs, orchestrate planner/code/test/docs agents, and open draft PRs with approvals and full audit trails.

[![](https://substackcdn.com/image/fetch/$s_!dB2j!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F20a51c5b-2f8b-4e8f-bb47-c8c43566375a_600x600.png)](https://substackcdn.com/image/fetch/$s_!dB2j!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F20a51c5b-2f8b-4e8f-bb47-c8c43566375a_600x600.png)

### IDE‑native agents: tools and how they work

​

* GitHub Copilot Chat/Workspace: inline suggestions, side‑panel plans, doc/test generation, and controlled multi‑file edits in VS Code/JetBrains.

* Cursor, Windsurf: propose multi‑file diffs, run tests/linters in context, and iterate on failures; Windsurf’s Cascade agent takes broader actions with fewer prompts.

* Cody, Continue.dev: repo‑aware chat via embeddings/code‑intel for large monorepos, improving symbol navigation and reducing hallucinations.

* **Mechanics**: Combine editor buffer with repo indexes (RAG) to reason across files; propose patch sets; run tests/linters locally; accept/reject visually.

* **Best for**: Single‑dev flow, scoped changes, and fast comprehension of unfamiliar code regions.

### CLI‑first agents: tools and how they work

* Claude Code CLI: agentic coding via terminal with claude.md project prompts, MCP tools, sub‑agents, and headless runs; excellent for refactors/docs/tests at scale.

* Copilot CLI: terminal‑native assistant for file edits, PR analysis, and workflow automation; supports programmatic and CI‑friendly modes.

* Codex: semantic search, code actions, and scripted edit recipes for big repos; easy to wire into pre‑commit/CI.

* **Open‑source alts**: Aider and Cline for local/privacy‑strict orgs and model flexibility.

* **Mechanics**: Plan→edit→validate loops scripted as commands; chain with linters (eslint/ruff), type checks (mypy/tsc), SAST (Semgrep/Snyk), and tests to fail fast before PRs.

* **Best for**: Mechanical refactors, test generation, audits, and migrations encoded as reusable recipes across repos.

### Cloud agent platforms: tools and how they work

* GitHub Agent HQ: mission control that plans steps, spins up cloud dev envs, runs terminals/tests/linters, pushes to draft branches, and opens PRs with reviewer gates and logs.

* Replit Agents, Bolt.new, Lovable, v0 by Vercel: intent‑to‑app pipelines with hosted previews, strong for UI/full‑stack scaffolds and shareable demos.

* Enterprise cloud copilots: Amazon Q Developer and Gemini Code Assist with IAM/policy controls and integrations to enterprise CI/code hosts.

* **Mechanics**: Agents decompose missions, coordinate tools (shell, tests, linters), synchronize context, and record artifacts; branch protections, required checks, and code owners enforce governance.

* **Best for**: Cross‑repo upgrades, large migrations, and standardized missions with compliance/audit needs and parallelism.

# SDLC impact with tool anchors

* **Design**: Copilot Chat/Cursor for architecture Q&A and design docs; Workspace for plan scaffolds; v0 for text‑to‑UI drafts and quick experiments.

* **Implementation**: Copilot/Tabnine for inline speed; Cursor/Windsurf for multi‑file refactors; Bolt/Lovable/Replit for prototypes with instant preview links to share.

* **Testing/quality**: Agent HQ runs unit/integration tests in‑loop; add Snyk/CodeQL/SonarQube/Semgrep gates to raise code hygiene and catch vulnerabilities.

* **Maintenance/migrations**: Claude Code CLI/Codex recipes for mechanical changes; Agent HQ/Gemini/Q for framework/dependency upgrades at scale with draft PRs.

[![](https://substackcdn.com/image/fetch/$s_!fcRB!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F147e869d-93aa-49a6-9ad3-f46e5d6e5fe0_650x590.png)](https://substackcdn.com/image/fetch/$s_!fcRB!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F147e869d-93aa-49a6-9ad3-f46e5d6e5fe0_650x590.png)

# Adoption, productivity, and new bottlenecks​

Teams see faster first drafts and smoother onboarding, but gains depend on spec clarity, test depth, and disciplined review as constraints shift upstream from typing to definition and verification.​  
Success correlates with CI instrumentation and policy gates in the agent loop—lint, SAST, coverage thresholds, risk scoring, and required reviews on agent PRs.

# How to work with the new stack

​

* Write mini‑spec prompts: constraints, edge cases, acceptance tests, and conventions; store as claude.md or prompt recipes for reuse.

* Start bounded: tests, mechanical refactors, docs, and scripted migrations before multi‑repo features; add rollbacks and approvals to reduce blast radius.

* Instrument and govern: connect agents to CI with lint/type/SAST/coverage checks; protect branches and require review for agent PRs to maintain quality.

# What comes next

Agent platforms will deepen org context, compliance, and analytics, normalizing templates like “bugfix,” “refactor + tests,” and “upgrade X” missions across repos with dashboards and KPIs.​  
Expect hybrid workflows—IDE for ideation, CLI for repeatability, and cloud for scale—rather than one tool to rule them all in day‑to‑day engineering.
