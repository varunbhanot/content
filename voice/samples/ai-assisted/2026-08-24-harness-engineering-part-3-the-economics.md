---
title: "Harness Engineering, Part 3: The Economics of Harness Engineering (And Where Teams Lose Money)"
subtitle: ""
date: 2026-08-24
url: https://varunbhanot.substack.com/p/harness-engineering-part-3-the-economics
words: 1224
era: ai-assisted
---

# Harness Engineering, Part 3: The Economics of Harness Engineering (And Where Teams Lose Money)

In [Part 1](https://varunbhanot.substack.com/p/harness-engineering-part-1-your-ai), we explained why your AI investment is a bet on infrastructure, not on a model. In [Part 2,](https://varunbhanot.substack.com/p/harness-engineering-part-2-the-four) we mapped the four layers of a production harness, context orchestration, tool/action governance, state/memory, and observability onto real stages of building software.

Most teams piloting coding agents are running an un-budgeted manual testing shop and calling it an AI initiative. They look at token costs, see a few dollars on an API bill, and think they’re moving fast. But their senior engineers are spending 30% of their week copy-pasting stack traces into prompt boxes, reviewing code that looks fine but isn’t, and hunting down bugs that only show up once the code actually runs.

The demo was cheap. The engineering tax is bleeding them dry.

## The Two Costs Nobody Tracks

When a company checks whether an agent workflow is worth it, they almost always look at the wrong number: **how fast the model responds and what the tokens cost.**

But once it’s running in production, two other costs decide whether you’re actually saving money:

Total Task Cost = (Token Cost × Iterations) + (Human Review Time × Hourly Rate) + (Blast Radius × Incident Cost)

1. **The “Generate and Pray” Tax (the cost of humans checking the agent’s work)**

If an agent writes code and nothing automatically checks it. If there is no sandboxed test runner, no type-check, no linter then a human has to be the safety net instead. Say a senior engineer has to read a 400-line AI-written pull request to catch a tricky bug, like a race condition. That engineer costs higher than a model run.

2. **The Flaky Retry Loop (when the agent won’t stop trying)**

Without a way to save progress and a cap on retries, agents spiral. It imagines a missing import. Therefore it tries to patch it but it edits the wrong file. Therefore three other things break. But it doesn’t stop there it just keeps going, burning through 800,000 tokens chasing its own tail, before it finally gives up.

An unharnessed agent is cheap to start and expensive to run low upfront cost, high ongoing debt.

[![](https://substackcdn.com/image/fetch/$s_!Uzkr!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F07d4f2fe-f0fd-4427-b06c-63c4b3109721_2816x1536.png)](https://substackcdn.com/image/fetch/$s_!Uzkr!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F07d4f2fe-f0fd-4427-b06c-63c4b3109721_2816x1536.png)

## The Economic Crossover Curve

Why spend 4 weeks of a principal engineer’s time building an execution harness? Because of where the two cost curves cross.

- **Zero Harness (Prompt & Hope)**: Cheap on day one. But as the code gets more complex, the time humans spend checking it grows too sometimes faster than the complexity itself, because it gets harder to hold it all in your head.

- **The Harnessed Platform**: Costs more upfront since you’re building tool rules, type checks, sandboxed tests, evaluation fixtures. But once it’s live, the cost of shipping each verified feature barely grows at all.

The agent tries 5 times inside a sandboxed harness for few dollars max, checks its work against the test suite, and only pings a human once everything passes. Human review time drops from 30 minutes to 3.

On an active team of 20+ engineers, that crossover point usually shows up within 6 to 8 weeks of real use.

[![](https://substackcdn.com/image/fetch/$s_!DUU3!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd93d39d0-13ea-462b-9a62-b237d20b0c78_2816x1536.png)](https://substackcdn.com/image/fetch/$s_!DUU3!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd93d39d0-13ea-462b-9a62-b237d20b0c78_2816x1536.png)

## The 4 Levers of Harness Unit Economics

If you’re defending your platform budget to a CIO or VP, these are the four things that actually matter.

1. **Let the machine retry, not the human**. Running a model through 4 rounds of automated testing costs few dollars. A human who has to stop, switch between Slack, their editor, and a terminal just to debug a typo the agent made that costs real money. Your harness should catch the obvious failures before it ever pings a person.

2. **Staying model-agnostic protects you**. Keep tool definitions separate from the model : Model Context Protocol, typed adapters, whatever your stack uses and handle state changes outside the prompt. Do that, and the model becomes just a replaceable part. Claude gets cheaper, GPT drops its price, an open-weight model catches up on one specific task — you swap it in one config line. Bake your logic into a 2,000-word prompt string instead, and every model swap is a full rewrite.

3. **Cut the “validation rent.”** Early on, teams over-build their checks. six different “LLM as judge” passes, stacked on top of each other, slowing the pipeline and running up the bill. In production, swap the fuzzy checks for rules that give a clear yes or no:

- Did tsc --noEmit pass?

- Did the test suite exit with code 0?

- Did the output match the strict schema?

Ninety percent of your harness should run on checks this cheap and this clear-cut. Save the expensive LLM evaluation for the parts that actually need judgment.

4. **Contain the blast radius**. One uncaught bug in a production billing pipeline costs more than your entire quarterly LLM budget. So build for the crash: writes that are safe to run twice, a strict three-step human approval gate before anything touches the outside world, pipelines that checkpoint their own progress. The value of a harness isn’t only what it ships. It’s what it stops from breaking.

## When You Shouldn’t Build One

A harness pays for itself over time. You spend engineering weeks once, then spread that cost across every change the agent ships after that. That math falls apart in three situations, and it’s worth being honest about them.

**When there isn’t enough repetition**. A team of four, shipping one service, touching a handful of files a week. There’s nothing to spread that cost across. Four weeks of platform work to save minutes per change is a bad trade, and it will still be a bad trade next quarter. Buy an off-the-shelf tool and move on.

**When the code isn’t meant to survive**. Prototypes, spikes, one-off migration scripts, throwaway analysis. Nobody builds a test suite for code that gets deleted in three weeks.

**When you don’t know what “correct” looks like yet**. This one catches people out. Deterministic checks need something to check against: a type contract, a test, a schema in exploratory work. So any gate you build now is aimed at a target that keeps moving. Explore first, with someone checking the work as you go. Build the harness once the shape stops moving.

**There’s a fourth case worth naming, and it’s the uncomfortable one.**

Some of what you build will be absorbed by the models. Bigger context windows have already eaten a lot of the retrieval systems teams used to build by hand. Better tool calling has eaten a lot of scaffolding.

What doesn’t get absorbed is the part that captures how your organisation actually works, not the model’s weaknesses: your contracts, your test fixtures, your approval gates, your definition of done.

The test before you build anything: if the next model release is twice as good, does this component become unnecessary or more valuable? Unnecessary means don’t build it. More valuable means build it now.

[![](https://substackcdn.com/image/fetch/$s_!ZPhs!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe82e6f29-9241-48a2-9b2a-462081c2e452_1024x559.png)](https://substackcdn.com/image/fetch/$s_!ZPhs!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe82e6f29-9241-48a2-9b2a-462081c2e452_1024x559.png)

## The Takeaway

The model is not your moat. It’s an expense that gets cheaper and faster every six months.

The harness is different. The sandboxes, the test fixtures, the type contracts, the state machines, the governance rules that’s the thing that keeps its value. That’s your real capital asset, not the model.

You didn’t buy a model. You bought a spreadsheet problem. Build the harness, make the checks deterministic, and that leak turns into the platform that pays you back.
