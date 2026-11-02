---
title: "A practical design-to-code workflow using agents (Day 45)"
subtitle: ""
date: 2026-01-06
url: https://varunbhanot.substack.com/p/a-practical-design-to-code-workflow
words: 623
era: hand
---

# A practical design-to-code workflow using agents (Day 45)

Welcome back! Today I'm sharing something that's been on my mind lately—how we actually build frontend applications in production using AI agents, not the demo-quality stuff you see on Twitter.

I've spent the last few months implementing multi-agent systems at Deutsche Telekom, and here's what I've learned: single-prompt design doesn't work for production apps. Sure, Opus 4.5 and Gemini 3 Pro are impressive, but asking an AI to "build me an app" rarely gives you something you can ship.

[![](https://substackcdn.com/image/fetch/$s_!yzkv!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Faeb88208-bfc7-4e01-9c46-4d10f8db339e_2500x822.png)](https://substackcdn.com/image/fetch/$s_!yzkv!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Faeb88208-bfc7-4e01-9c46-4d10f8db339e_2500x822.png)

Let me walk you through a practical pipeline that actually works.

## The Real Problem with AI Coding

The biggest mistake I see? Developers asking agents to “make it look good” without any visual reference. This leads to endless tweaking loops where you’re just guessing what the AI will generate next.

Here’s what I do instead.

## Step 1: Start with ShadCN Presets

[ShadCN](https://ui.shadcn.com/) recently added a feature that changed how I work with AI coding tools. You can now experiment with accessible UI components on their interface and create presets. Once you find a style that fits, you’re not just getting a mockup—you select your framework (Next.js in my case), copy an install command, and inject the preset directly into your terminal.

This gives your agent a codebase that’s architecturally sound from minute one. No more random prompting.

[![](https://substackcdn.com/image/fetch/$s_!53NR!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F266f8ea1-a085-44ef-93a4-493bab6cbe47_2354x902.png)](https://substackcdn.com/image/fetch/$s_!53NR!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F266f8ea1-a085-44ef-93a4-493bab6cbe47_2354x902.png)

## Step 2: Map Your Logic with Google Stitch

Before I hand anything off to a coding agent, I need a validated design plan. Google Stitch has become critical here, especially now that it supports Gemini 3 Pro Thinking.

Two features that matter for production:

**Color consistency**: Integrates with tools like [Coolers](https://coolors.co/) to balance main and accent colors before generation. Simple but saves hours of back-and-forth.

**Automated prototyping**: [Stitch](https://stitch.withgoogle.com/create) can ingest a static design and generate a working prototype that identifies navigation flows automatically. You’re not sending a flat image to your coding agent—you’re sending a logic map.

You can export these designs directly to AI Studio, the Jules coding agent, or as a zip file to import into Claude. This drastically reduces hallucination about how the app should “behave”.

[![](https://substackcdn.com/image/fetch/$s_!_IyJ!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F0ec04f9e-9f9d-4152-a063-3ca6a5a9142c_2354x876.png)](https://substackcdn.com/image/fetch/$s_!_IyJ!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F0ec04f9e-9f9d-4152-a063-3ca6a5a9142c_2354x876.png)

## Step 3: Parallel Execution in Claude

Here’s where it gets interesting. The bottleneck in agentic coding has always been latency—watching a cursor blink while an agent thinks.

Claude now lets sub-agents run in the background. This is a massive shift. For example, I configure a PLaywright MCP to handle browser testing. Since that’s time-intensive, I let it run in the background while I assign the main agent a different implementation task.

This is how real engineering teams work—parallel processing, not serial waiting.

**A word of caution**: These background agents consume tokens independently. Running multiple agents side-by-side will accelerate your development, but watch your token usage closely. I learned this the hard way.

## Step 4: Visual QA with Drawbridge

Even with perfect prompts, LLMs struggle with “pixel pushing”—those small, nuanced UI fixes that take forever to describe.

[Drawbridge](https://github.com/breschio/drawbridge) integrates directly with Claude Code and acts as your visual QA layer. It allows precise section selection, so non-technical users can convey specific UI issues without knowing the CSS behind them. Recent updates have fixed screenshot reliability issues and automated the slash command setup, removing the manual configuration friction we had earlier.

[![](https://substackcdn.com/image/fetch/$s_!RB8Y!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5ad3abb2-2df6-4b48-a95c-49c8c9c51a61_2558x822.png)](https://substackcdn.com/image/fetch/$s_!RB8Y!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5ad3abb2-2df6-4b48-a95c-49c8c9c51a61_2558x822.png)

## The Reality Check

We’re moving from using AI as a text generator to using it as a technical co-pilot. By chaining these specific tools—ShadCN for structure, Stitch for logic, Claude for parallel execution, and Drawbridge for QA—I can replicate the output of a small technical team.

This is how we move from “cool demos” to real working solutions. The hype is over. Now it’s about building systems that actually ship.
