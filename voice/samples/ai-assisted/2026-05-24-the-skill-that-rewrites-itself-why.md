---
title: "The Skill That Rewrites Itself: Why Your Skills Drift and How to Stop It"
subtitle: ""
date: 2026-05-24
url: https://varunbhanot.substack.com/p/the-skill-that-rewrites-itself-why
words: 1403
era: ai-assisted
---

# The Skill That Rewrites Itself: Why Your Skills Drift and How to Stop It

Today is about what happens after day one.Because in production, most skills do not fail at launch. They drift.

[![](https://substackcdn.com/image/fetch/$s_!1_Wh!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5640cd90-2289-4e53-8eff-12e5444670fc_2160x1215.png)](https://substackcdn.com/image/fetch/$s_!1_Wh!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5640cd90-2289-4e53-8eff-12e5444670fc_2160x1215.png)

## The pattern nobody plans for

I have now seen this pattern across enough teams that it no longer looks accidental.

A skill gets written. It works. People start using it. Then the outputs begin to wobble. Sometimes solid. Sometimes strange. Someone opens `SKILL.md`, tweaks a line, adds a note, reruns the flow, and gets a temporary improvement. A week later, it drifts again.

That is the real maintenance model for most production Claude skills today. Manual. Reactive. Slow. No feedback loop. No measurement. No compounding. Just periodic patching based on whoever felt the pain most recently.

The problem is usually not that the skill was badly written.

The problem is that there is no system for making it better. And “make it better by feel” breaks the moment five engineers start using the same skill in five different ways.

Here is the part most teams miss: skill drift is usually an eval problem wearing prompt engineering clothes.

Teams think they need better wording. What they actually need is a measurable definition of good output. Once that exists, improvement stops being a creative exercise and starts becoming an engineering loop.

[![](https://substackcdn.com/image/fetch/$s_!m-7W!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb68a0a7f-e97f-47fa-8081-cf2ae2745fb8_2752x1536.png)](https://substackcdn.com/image/fetch/$s_!m-7W!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb68a0a7f-e97f-47fa-8081-cf2ae2745fb8_2752x1536.png)

## The loop, stripped down

At the smallest useful level, the loop is just four steps.

1. Define the goal. What does good output from this skill actually look like? It must be precise enough to score, not vague enough to debate.
2. Choose the file the agent can change. Usually that is `SKILL.md`. The description, body, trigger conditions, and bundled references are all fair game.
3. Run and score. Generate a batch of outputs with the current skill, evaluate them against the criteria, and calculate a pass rate.
4. Keep or discard. If a change improves the pass rate, keep it. If not, roll it back. Then repeat.

That is it.

This is test-driven development for the natural language artifact that drives agent behavior.

You would never ship a function with no tests and no way to know whether it works. Skills should not get a free pass just because they are written in English.

## What changes when you do this

I applied this to a code review skill that was supposed to detect architectural boundary violations in a Python service.

Before the loop, it was producing roughly 7 out of 10 acceptable outputs on the first pass, based on hand scoring across 30 real runs.

After a single overnight iteration loop, it moved to above 9 out of 10.

The more interesting part was not the score bump. It was the diff.

The loop made two edits I probably would not have written myself.

First, it sharpened the trigger condition. The original description said “review a pull request.” The improved version said “review a pull request where the diff touches more than one module.”

Second, it added one line exactly where the failures were clustering: “If an import crosses a layer boundary, name the boundary and the direction of the violation explicitly. Do not describe it as a general concern.”

I did not write those edits. The loop did.

That is the real point here.

The domain expertise still came from me. I knew what the skill was supposed to do. What the loop improved was the expression of that expertise: the phrasing, the order, and the emphasis.

It found a version that produced more consistent behavior because it could measure consistency. I could not. I was relying on memory, intuition, and a vague sense that the last few runs felt off.

## Why this is an eval problem

This is the reframe that matters if you are building for production.

Most teams treat skill improvement like prompt engineering. They hunt for better wording. They shuffle instructions around. They add more explanation. They hope the model behaves.

But wording is rarely the real bottleneck.

The real bottleneck is the absence of a measurable definition of good.

Without eval criteria, every change is guesswork. You see a bad output, patch the skill, and hope the patch helped. You do not know whether it improved performance, hurt performance, or simply changed the failure mode.

The loop forces the right question to come first: what does a good output from this skill actually look like?

Once that answer exists in scoreable yes or no terms, the improvement process becomes mechanical. Claude can run the loop. You do not need to sit there manually nudging wording every few days.

This is evaluation-driven development at the skill layer.

It is the same discipline that separates production AI systems from demo-stage prototypes. Skills that never get measured do not get better. They drift.

[![](https://substackcdn.com/image/fetch/$s_!QKcr!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F0960834f-41c2-4cab-9c95-8051d85f881f_2752x1536.png)](https://substackcdn.com/image/fetch/$s_!QKcr!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F0960834f-41c2-4cab-9c95-8051d85f881f_2752x1536.png)

## How to set it up

## 1. Start with the right skill

Pick the skill you use most.

The more often a skill runs, the faster improvement compounds. It also means the cost of underperformance is higher. Your highest-usage skill is usually your highest-leverage candidate.

Do not try to fix everything at once. Get the loop working on one skill. Then expand.

## 2. Define the eval criteria

This is where most teams fail.

Write 4 to 6 yes or no questions that define good output. Make them concrete. Do not ask, “Is the output good?” Ask things you can actually score.

For a code review skill, that might look like this:

* Does the review identify at least one security-relevant pattern?
* Does it give a concrete recommendation for every issue found?
* Does it stay within 400 words?
* Does it avoid generic filler like “consider adding comments”?

Vague criteria produce vague improvements.

The quality of the eval sets the ceiling for the quality of the loop.

## 3. Run the loop

Open Claude Code in the skill directory and give it a prompt like this:

> Improve my [skill name] skill using an evaluation-driven loop. The skill file is at [path]. Evaluation criteria, score each output yes/no:
>
> 1. [criterion 1]
> 2. [criterion 2]
> 3. [criterion 3]
> 4. [criterion 4]
>
> For each iteration:
>
> * Generate 10 outputs using the skill on representative inputs
> * Score each output against the criteria and produce a pass rate
> * Modify `SKILL.md` to improve the pass rate
> * If the pass rate improves, keep the change; if not, roll it back
> * Run for 10 iterations and report the final pass rate plus what changed

That is the entire loop.

The skill iterates on itself. You walk away.

## 4. Read the diff, not just the result

When the run finishes, the most useful artifact is not the final `SKILL.md`.

It is the diff.

The diff shows you which phrases were too broad, which instructions were underspecified, and where your original wording left room for failure. Over time, reading these diffs changes how you write the first version of every new skill.

The loop is not just optimizing the file.

It is training your instincts.

## What this changes in production

In a team setting, this changes the maintenance model completely.

The old model is familiar. Write the skill once, use it in production, patch it manually when somebody notices it is underperforming. Nobody knows which version is best. Nobody knows whether the latest change actually helped.

The better model looks different. Every skill has eval criteria checked into the repo beside `SKILL.md`. The loop runs on a schedule, weekly or after any meaningful workflow change. Every update is measured. Every regression gets caught before it reaches production.

This is not some nice-to-have process layer for mature teams.

It is basic engineering discipline.

The skills your agents run are software. Natural language software, yes, but still software. They deserve versioning, evaluation, rollback logic, and continuous improvement just like the rest of your stack.

Teams that understand this early will compound quality quietly for months.

Teams that keep patching by feel will keep asking why the skill got worse.

And the frustrating part is that the answer will have been sitting in front of them the whole time.

They did not have a prompt problem.

[![](https://substackcdn.com/image/fetch/$s_!7oSh!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3acf5827-a2f9-4eaa-8c58-a93c181471f6_2752x1536.png)](https://substackcdn.com/image/fetch/$s_!7oSh!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3acf5827-a2f9-4eaa-8c58-a93c181471f6_2752x1536.png)

## Conclusion

The biggest mistake in the current skills ecosystem is treating `SKILL.md` like a static instruction file.It is not static.It is a behavior surface. And behavior surfaces need feedback loops.

Once you start treating skills as measurable system components instead of handcrafted prompt assets, the whole maintenance model changes. You stop arguing about wording in the abstract. You start improving against evidence.

That is when quality begins to compound.
