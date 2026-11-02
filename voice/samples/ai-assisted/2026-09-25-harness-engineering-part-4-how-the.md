---
title: "Harness Engineering, Part 4: How the Harness Becomes a Software Factory"
subtitle: ""
date: 2026-09-25
url: https://varunbhanot.substack.com/p/harness-engineering-part-4-how-the
words: 1790
era: ai-assisted
---

# Harness Engineering, Part 4: How the Harness Becomes a Software Factory

In [Part 1](https://varunbhanot.substack.com/p/harness-engineering-part-1-your-ai) of Harness Engineering, we argued that your AI investment is an infrastructure bet, not a vendor bet. In [Part 2](https://varunbhanot.substack.com/p/harness-engineering-part-2-the-four), we mapped the four layers of a production harness onto how you already ship software. In [Part 3](https://varunbhanot.substack.com/p/harness-engineering-part-3-the-economics), we did the economics: the human review tax, flaky retries, and where the cost curves cross.

This part picks up after you’ve decided the bet is worth it. What has to change in how work moves, so the harness stops being a wrapper around a model and starts running like a software factory?

[![](https://substackcdn.com/image/fetch/$s_!khfu!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F48665e97-79b9-4012-a9cf-5d8857bbc7cc_1760x588.png)](https://substackcdn.com/image/fetch/$s_!khfu!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F48665e97-79b9-4012-a9cf-5d8857bbc7cc_1760x588.png)

Four parts, one argument. This one is about factory

Every new frontier model gets the same demo. One clean repo, a README that actually helps. The agent one-shots a feature, someone shows it in standup, and for about a week everyone feels like the future showed up early.

Then you point the same setup at the real codebase. Multiple repos. Services with half the docs missing. Three teams’ conventions colliding inside one ticket. The agent churns out 400 lines per ticket. But what passes review without significant comments? Closer to 15% than the 80% the demo promised. In a fintech pilot I watched, the agent generated 47 PRs across three days. The team merged two of them unchanged.

The reason it falls over is boring: nobody changed how the work flows. Each ticket is still a chat with better autocomplete. Every session starts fresh, there’s no cap on how many half-done changes are open, quality gets checked only after the PR exists, and a crash at hour five means starting from scratch. Swap in a better model and you get the same class of mess. The mess was never in the weights. It was in how the agent lost context across files, which tests it should run, which repos were off-limits, or when to escalate instead of guessing.

So what do I mean by a factory? A system where the same five steps repeat for every ticket in the same order: gather context, plan, implement, verify, hand off. You know what to expect, and you can spot when something is taking longer than it should. There’s a hard limit on work in progress, because ten agent threads running in parallel just means ten branches waiting for someone to review them. Quality gets checked before the change lands, instead of in a Slack thread after merge. A crash means resuming from where it stopped. And the model is one machine on the floor: useful and replaceable, and the line doesn’t depend on it.

[![](https://substackcdn.com/image/fetch/$s_!QPQ0!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd7bd249e-6811-4b65-893e-c24fac0349f4_1100x735.gif)](https://substackcdn.com/image/fetch/$s_!QPQ0!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd7bd249e-6811-4b65-893e-c24fac0349f4_1100x735.gif)

One ticket through the line. A failed gate sends the work back to Build, without pulling a person in.

The greenfield demo tells you the model can write code. Your brownfield repo tells you whether you built a factory or a nicer chat window.

[![](https://substackcdn.com/image/fetch/$s_!yjUY!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2ab99f02-d0ab-4ca9-a310-971cf1bab65c_1760x898.png)](https://substackcdn.com/image/fetch/$s_!yjUY!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F2ab99f02-d0ab-4ca9-a310-971cf1bab65c_1760x898.png)

Same brownfield ticket. The chat keeps losing context and starting again. The line finishes.

## **Work has to flow like a loop, not a chat**

The change that mattered most for us was in how work is allowed to move.

In the chat version, a ticket turns into a conversation. The agent explores, edits, apologises, edits again. Humans end up as the real validation layer, pasting stack traces into prompt boxes and reviewing PRs that look fine until someone runs them. It’s like onboarding a new hire for every single task. Part 3 put a price on this: the human review tax. The factory’s job is to remove most of that tax before a person ever opens the PR.

In the factory version, a ticket is a unit of work on a line. Someone (a human, or a planning step) sets the goal and the boundaries. The run goes through stages you already know from shipping software: gather context, plan, implement, verify, hand off. Each stage has a defined input and a defined “done.” Before any code gets written, you agree on the acceptance checks for this chunk of work, so nobody is judging the result on gut feel. The agent doesn’t get to make up its own workflow each session. Most of the path is deterministic, and the model only makes decisions at the points that need judgment. Nobody hands it an open-ended loop and hopes it figures things out.

This is where Part 2’s four layers stop being a diagram and become parts you install. Context tells the run which codebase and conventions it’s working in. Tool governance decides what it’s allowed to touch. State keeps progress across crashes. Observability tells you whether the line is healthy. You build these once and attach them to the line, so every ticket reuses them.

People are still on the line. Sometimes you steer live in the IDE. Sometimes you hand off a goal and review what comes back. What changes is where you show up: at the points where a mistake is expensive to undo.

Use this rough hierarchy: run anything deterministic and fast without a human (tests, linters, type checks, sandboxed builds). Only human-gate changes that need judgment or have a blast radius: migrations, permission changes, architectural decisions. By that rule, a code review gate should see PRs that already passed 40+ automated checks, so a human’s time is spent on judgment, not hunting basic bugs. Put a person on every lint finding and you’ve built a queue. Put nobody on a data migration and you’ve built an incident.

[![](https://substackcdn.com/image/fetch/$s_!2I7F!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F974505bd-954d-4ba1-bff1-336658977773_1760x852.png)](https://substackcdn.com/image/fetch/$s_!2I7F!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F974505bd-954d-4ba1-bff1-336658977773_1760x852.png)

The machine checks every change. A person only reviews the change that is expensive to undo.

## **What a factory day actually looks like**

Mostly it looks like ordinary production habits.

Work arrives in a shape the line can handle. “Fix billing somehow” doesn’t qualify. A ticket that does has the repos in scope, the acceptance checks written up front, and a stop condition, so the agent can’t spend an afternoon chasing imaginary missing imports while the token bill and the Slack thread both grow.

Only a few units move at once. WIP limits are dull, and they’re also what stops you ending up with a pile of half-finished agent branches that nobody trusts. It’s the same logic as Part 3’s crossover curve: starting work is cheap, but every open branch costs you review time later.

Verification happens inside the stage. Nobody should be doing it later as a favour. Use whatever your stack already has, whether that’s tests, lint or sandboxes. Agree the done condition before the agent starts writing, and run the check from outside the loop that wrote the code, because agents grade their own work generously. Agent-written production code should face a higher bar. Going fully lights-out with no quality gate is a known trap: the demo metrics stay green for months while the codebase quietly gets harder to maintain.

Progress gets written down as artifacts: a plan file, progress notes, git state, whatever the next run needs so it doesn’t have to rediscover everything. Long agent runs will crash. In our first month without checkpoints, we had 12 failed runs out of 80 total. Three times a human restarted manually. Eight times the agent just stopped with no resume path. That killed adoption faster than any quality issue did. If the answer to a crash is “start over,” you won’t keep the system. The run should pick up from the last step it completed.

[![](https://substackcdn.com/image/fetch/$s_!SC99!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F37b7c515-829c-4b6b-b8c3-884cf097bf6b_1760x910.png)](https://substackcdn.com/image/fetch/$s_!SC99!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F37b7c515-829c-4b6b-b8c3-884cf097bf6b_1760x910.png)

Same crash, same step. Without checkpoints the run starts again from step 1. With them it resumes at step 4.

The model sits behind a contract. Tool descriptions work like APIs, the boring kind that still work after a model update. Behaviour lives in the line, and not in a 2,000-word prompt you rewrite every time a cheaper model comes out. Part 1’s point still holds: agent = model + harness, and the model is the part you can swap. Prompt tricks tend to break on the next release. A well-built line keeps working when you change the model.

None of this is exciting. It feels a lot more like a good CI system than a viral demo, and that’s what you want.

## **One expensive lesson**

Early on, we overbuilt the checks. Five different LLM-as-judge passes to verify data migrations. Two of them — a schema diff and a row count comparison — are in production. The other three sit in feature flags. We run all five in CI to keep them “fresh,” which adds eight minutes to every build. We should delete the three, but haven’t yet. That’s inventory you don’t see on the balance sheet, and it bleeds slower than a leak you know about.

A factory needs product management too. Every check you standardise before a real workflow needs it is stock sitting on a shelf. So WIP includes more than open PRs. Half-built harness you keep paying for counts too.

That’s when I understood what we’d been getting wrong. We had too much inventory and not enough verified output.

## **What I’d try this week**

If you’re stuck between a wrapper that demos well and something you can actually run, don’t try to fix everything at once. Pick one production workflow (a real one from your messy codebase, not a greenfield toy) and make it run as a tiny factory for seven days.

Stick to one ticket type and one path through the stages. Cap how many of those tickets can be in flight at once. Add a verify step that can fail the run before a human loses an afternoon to it. Write artifacts so a crash at hour five resumes instead of restarting. And set up the model call so you could swap it without rewriting the workflow.

You’ll know quickly. Either changes start coming off the line verified, or you’ll hit a specific wall: the agent doesn’t know when to stop, or it doesn’t understand which files are off-limits, or it keeps trying to fix things that aren’t broken. That tells you exactly what harness layer is missing, so you know what to build next.

After that week, you’ll have proven the loop works and found the gaps. From there, you scale: add the second ticket type, raise the WIP cap, hand off to the team. But only after you’ve proven one line holds.

You don’t need the whole factory on day one. You need one line that survives your messiest repo.

## **Closing the series (for now)**

Four parts, one argument. Bet on the infrastructure around the model rather than on the vendor. Build the four layers : context, tool governance, state, observability so the agent can finish real work. Watch the economics so review tax and retry loops don’t eat the gains. Then run the harness like a factory, with WIP limits, gates before merge, and runs that survive a crash.

That’s where the series stops for now. If I write more, it’ll be about what breaks when these lines hit bigger brownfield estates.

The part I’m still working out is where autonomy should stop and human judgment takes over on large, old codebases. If you’re building a factory like this, or you’re stuck between demo and production, write in. I want to see what breaks when a line hits real complexity.
