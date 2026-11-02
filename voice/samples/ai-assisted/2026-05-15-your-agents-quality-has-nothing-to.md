---
title: "Your Agent's Quality is not only about the Model"
subtitle: ""
date: 2026-05-15
url: https://varunbhanot.substack.com/p/your-agents-quality-has-nothing-to
words: 1418
era: ai-assisted
---

# Your Agent's Quality is not only about the Model

Here’s the uncomfortable truth: most production agent teams have been doing harness engineering for months. They just didn’t know what to call it and that’s why their controls keep fighting each other.

An engineer wires up a coding agent with a thoughtful system prompt. Leadership lights up Slack *“It built the entire CRUD endpoint in seven minutes!”* A week later the same agent ships code that passes the linter, passes the type checker, and quietly breaks an architectural boundary nobody documented. The postmortem turns into a finger pointing exercise. Was it the prompt? The CI? The model? The reviewer?

This works for demos. It breaks in production. And the discipline that fixes it now has a name.

## **The Vocabulary is becoming clear**

The core idea is one equation:

> **Agent = Model + Harness**

The model is the LLM. The harness is everything else, the constraints, the feedback loops, the tooling, the documentation, the linters, the eval pipelines, the lifecycle management. The harness is the infrastructure that wraps the model’s reasoning and turns probabilistic next token prediction into something you can ship.

The reason this matters: OpenAI built and shipped a production beta with three engineers, in five months, with roughly one million lines of code zero of which were typed by hand. Throughput hit 3.5 PRs per engineer per day, and went up as the team scaled.

That’s the line worth pinning to your wall. The model was a constant. The harness compounded.

[![](https://substackcdn.com/image/fetch/$s_!VZhx!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2635a575-33e0-473a-a105-5c15b1e73df7_1536x1024.png)](https://substackcdn.com/image/fetch/$s_!VZhx!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2635a575-33e0-473a-a105-5c15b1e73df7_1536x1024.png)

## **Guides and Sensors**

Every harness component is one of two things:

**Guides** are feedforward controls. They anticipate failure before the agent acts. System prompts, coding convention documents, architecture decision records, bootstrap instructions, code mods that pre shape the workspace all guides. They increase the probability of a good first attempt.

**Sensors** are feedback controls. They observe what the agent did and feed signal back so it can self correct. Linters, type checkers, test suites, code review agents, eval pipelines all sensors. They catch what guides miss.

You need both. Feedback only produces agents that repeat the same mistake on every attempt. Feedforward only produces rules that are never validated against actual output. The guides set the rails. The sensors check whether the agent stayed on them.

Inside each category, there’s a second split that determines your cost structure:

**Computational** controls are deterministic. Static analysis, type checking, linting, mutation testing these run in milliseconds, cost almost nothing per execution, and give you yes/no answers. The signal is precise but narrow.

**Inferential** controls use an LLM. Code review agents, semantic analysis, LLM-as-judge these are richer because they understand intent, but they’re slow, expensive, and non deterministic.

The whole game of harness engineering is knowing which lever to pull where.

[![](https://substackcdn.com/image/fetch/$s_!eTVS!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F00794a95-01ff-4d72-a237-8efeb0cbf612_1536x1024.png)](https://substackcdn.com/image/fetch/$s_!eTVS!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F00794a95-01ff-4d72-a237-8efeb0cbf612_1536x1024.png)

## **The Cost Split Nobody Watches**

Here’s where teams burn money without realising it. When LLM tokens were heavily subsidised, you could afford to put an inferential reviewer on every commit. As subsidies fade and per token pricing dominates, that architecture turns into a six figure monthly line item that produces marginal signal.

The disciplined approach: push computational sensors to the front of the pipeline where they run on every change. Reserve inferential review for the CI tail, where it runs against complete changes and produces meaningful semantic verdicts.

The practical heuristic I’d offer: look at how much is in your system prompt. If it’s more than a few hundred tokens of prose, ask which parts could be replaced by a deterministic check instead. Verbose inferential guides are expensive to run and easy to contradict. Computational sensors are cheap to run and impossible to argue with.

The static analysis tools we learned to ignore in the human developer era are getting their second life. Why? Because agents actually read the lint error and fix it. A custom linter that emits a message like *“This module imports from a higher layer in the dependency graph. Move the dependency or refactor the boundary.”* that message is gospel to an agent. The same message was wallpaper to a human dev.

## **Four Layers in Practice**

Here’s what a real harness looks like on a coding agent project. Imagine a Python service with an agent contributing PRs. The layered setup:

**Layer 1: Guides (feedforward)**

A `CLAUDE.md` or `AGENT.md` at the repo root containing:

```
# Coding Conventions
- All HTTP handlers go in src/api/, all business logic in src/domain/
- Domain modules never import from src/api/ (enforced by import-linter)
- All new endpoints require an acceptance test at the HTTP boundary
- Use the venv in .venv/ — do not pip install globally

# Architecture Boundaries
Types → Config → Repo → Service → Runtime → API
Dependencies flow downward only. Upward imports fail CI.
```

Plus a system prompt that references this file and names the failure modes we’ve already seen in the codebase.

**Layer 2: Computational sensors**

A `pyproject.toml` with `ruff`, `mypy`, and `import-linter` configured to enforce the dependency direction declared in the guides. Pre commit hooks run all three on every change the agent makes. Custom rules emit messages tuned for the agent *“src/domain/user.py imports from src/api/. Move the helper into src/domain/ or invert the dependency.”*

Tests live behind `pytest`. The agent runs them on every change. Mutation testing via `mutmut` runs on the CI tail and surfaces tests that pass without actually exercising new behaviour.

**Layer 3: Inferential sensors**

A code review agent triggers on PR open. It reads the diff, the linked issue, and the architecture document. It produces a structured verdict not a “looks good” but something like *“The new repository method bypasses the existing query builder. Consider whether this introduces a second pattern for the same operation.”*

This is also where packaged eval skills fit. Skills for `error-analysis`, `generate-synthetic-data`, `write-judge-prompt`, and `validate-evaluator` can be invoked by the agent itself to evaluate its own output. The judgment about how to judge isn’t reinvented per team it’s installed once and reused.

**Layer 4: Continuous gardening**

A scheduled agent runs every Friday. Its job isn’t features it’s maintenance. It scans the codebase for:

* Deprecated dependencies and generates upgrade PRs
* Dead code with no inbound references
* Security advisories against the dependency tree
* Architectural drift files that crossed boundaries since last week

The output is a prioritised list of small PRs, each human reviewable in minutes. The technical debt sprint that used to happen quarterly happens weekly, and nobody had to schedule it.

[![](https://substackcdn.com/image/fetch/$s_!F8A_!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F639fe5cd-d6e6-4909-a2d5-df4e9e72c443_1536x1024.png)](https://substackcdn.com/image/fetch/$s_!F8A_!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F639fe5cd-d6e6-4909-a2d5-df4e9e72c443_1536x1024.png)

## **Harnessability. Not All Codebases Can Be Harnessed Equally**

Here’s the part of this that should worry every enterprise architect. Not all codebases afford effective harness construction equally and I’d call this property *harnessability*.

Strongly typed languages, clear module boundaries, opinionated frameworks score high. You can wire `import-linter` rules to Python packages because they have clear structure. You can run ArchUnit against Java because the language surfaces the metadata. You can enforce dependency direction in TypeScript because the type system understands it.

Legacy systems score near zero. A ten year old monolith with implicit conventions, inconsistent test coverage, and no documented architecture has nothing for a harness to grip onto.

The cruelest part: harness engineering is *most needed* exactly where it’s *hardest to build.*

We’ve watched this pattern repeat across organisations. The teams most excited about coding agents are sitting on the codebases least suited for harnessing. Agents accelerate what’s already there clean architecture and accumulated technical debt alike. The right move before deploying an agent on a legacy system isn’t “just point a coding agent at it.” It’s an honest harnessability audit, followed by whatever modernisation work the audit surfaces.

## **What Changes for Your Team**

If you’re shipping agents into production, the job description has already shifted. You’re not writing more code. You’re designing the feedback systems that make agents write good code. That’s a different discipline, with different muscles.

The teams getting this right share a few habits:

* They name their harness components. They know which document is a guide and which check is a sensor.
* They watch their cost split. They know what fraction of their LLM bill goes to inferential controls versus feature work, and they tune it deliberately.
* They invest in computational sensors first. Cheap, fast, deterministic. Inferential review only where deterministic checks can’t reach.
* They schedule continuous gardening. Maintenance isn’t a quarterly sprint it’s a weekly automated scan.
* They treat the behaviour harness as the open problem. They don’t pretend their eval pipeline is solved.

Every agent system is a prototype till you start designing the harness around it.

Remember, every agent is autocomplete till you start measuring what it produces.
