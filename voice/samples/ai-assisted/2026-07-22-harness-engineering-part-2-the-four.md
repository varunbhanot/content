---
title: "Harness Engineering, Part 2: The Four Layers of a Production Harness, Mapped to Your SDLC"
subtitle: ""
date: 2026-07-22
url: https://varunbhanot.substack.com/p/harness-engineering-part-2-the-four
words: 1371
era: ai-assisted
---

# Harness Engineering, Part 2: The Four Layers of a Production Harness, Mapped to Your SDLC

[Previous article](https://varunbhanot.substack.com/p/harness-engineering-part-1-your-ai) argued that your AI investment is an infrastructure bet, not a vendor bet. You can swap the model. The harness is what you keep.This part is about what the harness actually is.

When teams hear “harness,” they picture a CLAUDE.md file and some prompt templates. Then they wonder why their agents work in demos and fall apart in production. A production harness is not a config file. It is a system with four layers, and each layer maps to a phase of the SDLC you already run.

That mapping matters. If you have CI/CD, observability, and IAM today, you already own the mental models needed to build one. Google’s New SDLC whitepaper (Osmani, Saboo, and Kartakis, May 2026) makes the same mapping at the framework level. What follows is that framework, extended with what it looks like when real legacy migrations run through it at enterprise scale.

[![](https://substackcdn.com/image/fetch/$s_!fVBl!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6a819d38-1b24-4852-9721-ad3c342d1b74_1024x559.png)](https://substackcdn.com/image/fetch/$s_!fVBl!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6a819d38-1b24-4852-9721-ad3c342d1b74_1024x559.png)

## Layer 1: Context Orchestration

Not one CLAUDE.md file. A hierarchy.

Org-level standards. Team-level conventions. Project-level state. Session-level task context. Each layer inherits from the one above, the way your Terraform modules inherit from org policy. The agent should know your engineering standards without being told every session, the same way a new hire stops needing the onboarding doc after week one.

The failure mode nobody warns you about is context rot. Every temporary fact that gets promoted into a durable context file is a future hallucination waiting to happen.

“We’re using the staging DB this sprint” becomes gospel eight months later. Context files need the same discipline as code: versioning, ownership, garbage collection.

Google splits this into static context (always loaded, expensive, defining who the agent is) and dynamic context (loaded on demand, cheap, retrieved when the task needs it). The boundary between the two is a genuine architectural decision. Too much static context wastes tokens and dilutes signal. Too little means the agent forgets critical rules. Treat that boundary as reviewed, versioned configuration, not as whatever someone happened to paste in last.

We learned this the expensive way. Early in our migration programme, a documentation run came back wrong and the team rejected it. The AI had not failed. An entire repository was missing from what we fed it. Once we added it, the output was correct and trust recovered. The lesson stuck: garbage-in failures read as AI failures to your stakeholders. Input completeness verification belongs in the harness, before the agent acts, not after things go wrong.

This layer has the highest ROI in the entire system. It determines what the agent knows about your world before it does anything.

[![](https://substackcdn.com/image/fetch/$s_!fEee!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6d3df9ad-43eb-4946-be9b-8a28738de48f_1024x559.png)](https://substackcdn.com/image/fetch/$s_!fEee!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F6d3df9ad-43eb-4946-be9b-8a28738de48f_1024x559.png)

## Layer 2: Tool & Action Governance

Which tools the agent can invoke. Under what conditions. With what approval gates.The mistake is treating autonomy as binary. Production harnesses run a spectrum:

* Fully autonomous for linting, test generation, formatting. Cheap to verify, cheap to reverse.
* Approval-gated for infra changes, data migrations, production deploys. A model can generate a valid Terraform plan. Deciding whether to apply it to prod still needs a human.
* Human-driven with AI assist for architecture decisions and incident response. The agent drafts, the human decides.

What the spectrum encodes is irreversibility. Gates sit exactly where undoing gets expensive. In our platform, three human gates block automated progression. The human validates the AI’s understanding of the legacy system before any planning starts. The human defines the target architecture. The human approves the migration spec.

After that third gate, the pipeline runs headless to completion. Everything before it ischeap to redo, so it stays flexible. Everything after is automated, because the human already signed off on the plan.

One more shift that sounds small: treat tool descriptions as API contracts, not prompt copy. The question changes from “does the prompt make the model use the tool correctly” to “is this interface clear enough that any model could use it reliably.” That is what makes Part 1’s vendor independence real in practice. Contracts survive model swaps. Prompt tricks survive until the next weights update, if you’re lucky.

And counterintuitively, fewer tools make better agents. Unconstrained agents waste their context exploring dead ends. Tight constraints collapse the solution space into something they can actually navigate.

[![](https://substackcdn.com/image/fetch/$s_!gN81!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F81b3867e-95eb-4095-8c61-62cddc0a363a_1024x559.png)](https://substackcdn.com/image/fetch/$s_!gN81!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F81b3867e-95eb-4095-8c61-62cddc0a363a_1024x559.png)

## Layer 3: State & Memory Management

This layer runs two loops, a fast one and a slow one. Both are the harness’s job.

The fast loop is error routing within a task. The agent writes a function, the harness provides the sandboxed environment where tests execute, a test fails, the orchestration logic captures the error output and routes it back to the model to try again. This is what turns “generate and pray” into think, act, observe, correct. Without it you are the feedback loop, copy-pasting stack traces into a chat window.

The slow loop is memory across sessions. Without it, every conversation starts cold, like an engineer beginning a new shift with total amnesia. The fix is not a smarter model. It is externalized state: progress files, structured task lists, git history as a first-class information source, checkpoints the agent reads on startup.

In our platform, every pipeline step checkpoints to a database. A migration run that crashes at hour five resumes from the last completed micro-step, not from zero. That single design decision is what converts agents from demos into infrastructure. Long-running agent work will crash. If your answer is “start over,” trust erodes before quality ever gets evaluated.

Three memory scopes, and confusing them causes most of the pain:

* Session memory. Ephemeral, dies with the task.
* Project memory. Durable, travels with the codebase.
* Organizational memory. Shared, governed like any other shared asset.

The governance questions are the ones your config management already answers: what gets persisted, where it lives, who can modify it, how it gets garbage-collected. If your team cannot answer those four questions about agent memory, you do not have a memory layer. You have a maintenance burden dressed up as a feature.

[![](https://substackcdn.com/image/fetch/$s_!YVzH!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe029a766-b2f9-40f2-988b-fd3755360067_1024x559.png)](https://substackcdn.com/image/fetch/$s_!YVzH!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe029a766-b2f9-40f2-988b-fd3755360067_1024x559.png)

## Layer 4: Observability & Feedback

How do you know the harness is working?

Not “did the code pass CI.” That is table stakes. The new metrics: token spend per task, success rate by action type, iterations to success, cost per merged change, time-to-approval bottlenecks, where the agent got stuck and needed a human.

Map it to what leadership already funds and the budget conversation gets easier. Layer 1 is knowledge management. Layer 2 is IAM and RBAC. Layer 3 is config management. Layer 4 is APM and monitoring.

You are not asking for a new category of spend. You are asking to extend four categories the business already understands to a new class of worker.

This layer is also where intelligent model routing lives. Observe which task types fail on cheaper models. Route those to capable ones. Let everything else run cheap. You cannot do this without the observability, which means Layer 4 is not optional, it is the layer that pays for the other three.

One honest confession from production: we overbuilt here. We built five validation approaches for verifying migrated code against legacy behaviour. Two are live. Three are built, hidden behind feature flags, and quietly charging us maintenance rent. The harness needs product management too. Every component you standardize before a workflow actually demands it is inventory sitting on the shelf.

## The factory, revisited

[Part 1](https://varunbhanot.substack.com/p/harness-engineering-part-1-your-ai) ended with the equation: Agent = Model + Harness.

You are building the system that builds software. The harness is the factory. The model is one machine on the factory floor, one you swap when a better one ships, because the factory was never designed around a specific machine. Your context hierarchy, your tool contracts, your memory architecture, your metrics. None of it is vendor property. All of it compounds over time.

The industry spent last year arguing about which model to bet on. The teams that are shipping this year stopped arguing and started building the thing that makes the model interchangeable. That is the work.

[![](https://substackcdn.com/image/fetch/$s_!NN5j!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F35802616-1859-429a-9bec-fb1066614b8d_1024x559.png)](https://substackcdn.com/image/fetch/$s_!NN5j!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F35802616-1859-429a-9bec-fb1066614b8d_1024x559.png)

*Next in this series: the economics of harness engineering. Why vibe coding is low-CapEx, high-OpEx debt in disguise, what the crossover point looks like in real numbers, and how to make the case to the person who actually allocates the budget.*
