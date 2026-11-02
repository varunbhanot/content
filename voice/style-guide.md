---
title: "Voice style guide: Beyond the AI Demo"
status: approved
derived_from: voice/samples/hand (13 posts, 2024-11 to 2026-01)
---

# Voice style guide

> **Status: APPROVED by Varun.**
> Every rule below is backed by a quote from `voice/samples/hand/` (file named in brackets).
> Nothing is derived from `ai-assisted/` except the **Avoid** list.

## Who's talking

First person, a practitioner, not a commentator. Varun builds agentic AI in production at Deutsche Telekom and says so plainly.

- "I've spent the last year building agentic AI systems at Deutsche Telekom. The teams that succeed don't have better prompts. They have better structure." [day-43-claude-skills]
- "I've spent the last few months implementing multi-agent systems at Deutsche Telekom, and here's what I've learned…" [a-practical-design-to-code-workflow]
- Admits mistakes and costs: "Running multiple agents side-by-side will accelerate your development, but watch your token usage closely. I learned this the hard way." [a-practical-design-to-code-workflow]
- Uses real, personal examples (his own finance app, his own n8n workflows): "Today I'll share two workflows that have helped me a lot recently" [day-37-practical-productivity-hacks]

## Openings

Two moves, pick one:

1. **Warm return** for a series post: "Welcome back to my #75DaysofGenerativeAI series!" then one line on what today covers. [day-22, day-34, day-37, day-38]
2. **Blunt claim**, stated as a truth the reader half-knows. Vary the wording every time. These are examples of the move, not phrases to reuse:
   - "Most LLM applications never make it past the demo stage." (day-39-42 opens it with "Here's the uncomfortable truth:")
   - "Most teams treat AI like a smart search box." (day-43, same lead-in)
   - "Building with LLMs feels like magic until reality hits." [day-33]

**Do not default to "Here's the uncomfortable truth".** It opens only 2 of 13 hand posts (a third uses "uncomfortable truths" in a heading). Using it in every post is a tic, not a voice trait. Use it at most once in a long while, and only when the claim really is uncomfortable. Otherwise open with the claim itself, a scene, a number, or a question.

Then name the symptom the reader will recognise ("Your chatbot works perfectly in demos but falls apart with real users. Sound familiar?" [day-33]).

## Rhythm

Short declarative lines. One-line paragraphs for the punch. The pivot sentence is often just a few words.

- "This works for demos. It breaks in production." [day-43]
- "You're not building systems. You're having expensive conversations." [day-43]
- "Structured workflows are robust. They work predictably." [day-43]
- "The problem isn't your prompts or your model choice." (own line, then the answer) [day-33]

Pattern: **setup, then a short sentence that lands it.** Mix with one or two longer explanatory sentences; do not stack long ones.

## Devices

- **Everyday analogy**: "That's prompt engineering—important, but honestly just the appetizer. *Context engineering* is the main course." [day-38] / "The AI's a junior on their first day, no context, just academic guesses." [day-38] / "They're like school exams testing general skills." [day-33]
- **Before/after contrast** ("Prompt-only world" vs "Context-engineered world") [day-38]; "Same system working really well on…" after a fix [day-39-42]
- **Numbered "Step N" walkthroughs** for how-tos: "Step 1: Start with ShadCN Presets … Step 4: Visual QA with Drawbridge" [a-practical-design-to-code-workflow]
- **Block-quote pull-line** that compresses the thesis: "You're flying blind without proper evaluation." [day-33]
- **Bold lead-ins on bullets** (`**Color consistency**: …`) to make lists scannable.
- **Symbolic shorthand for a rule of thumb**: "LLM evaluation ≠ benchmarking" [day-33]
- **Reader-facing "you"** and rhetorical questions: "Sound familiar?"

## Structure and length

- One topic per post. Hand posts run **~550–1,400 words, most 650–950**. Do not pad toward longer.
- H2 sections with plain, claim-like or question headings ("The Real Problem with AI Coding", "LLMs Broke Traditional Software Testing").
- Diagrams or screenshots between sections; caption-style one-liners under them.
- Bullets for lists of three or more items; prose for argument.
- A concrete example or number early (a real app, a real failure), not abstract framing.

## Closings

Short and plain. Restate the shift in one or two sentences, then stop or point forward.

- "Without evaluation, your product is just a prototype. With proper evaluation, you have a systematic way to improve, a competitive moat, and the confidence to ship AI that actually works." [day-33]
- "Remember, every AI system feature is an experiment till you start measuring it." [day-39-42]
- "This is how we move from 'cool demos' to real working solutions. The hype is over. Now it's about building systems that actually ship." [a-practical-design-to-code-workflow]
- Series posts may end with a one-line italic pointer to the next post: "*Ready to dive deeper? Next articles in series includes hands-on tutorials…*" [day-33]

Recurring theme to keep: **demo vs production**. Varun returns to it in almost every post.

## Avoid

Voice tells seen mainly in `ai-assisted/` (use as a critic checklist, not as voice):

- "quietly" as a drama word ("quietly breaks", "quietly fades"): 8 uses in 10 AI-assisted posts vs 2 in 13 hand posts. Allow rarely.
- "buried" and "without fanfare": appear only in AI-assisted posts.
- Formal series recaps: "In Part 1 we argued… In Part 2 we mapped…" before the point. Varun's recaps are one clause ("Last time we talked about…").
- Long dense paragraphs: 44 of ~1,170 hand paragraphs exceed 400 characters; 68 of ~690 AI-assisted ones do. Break them up.
- Length creep: AI-assisted posts run 1,100–1,800 words. Hand posts rarely pass 1,000.
- Vendor-brochure phrases: "revolutionizing", "enterprise-grade", "game-changing". (Hand posts occasionally slip; do not imitate.)
- Invented statistics or anecdotes the source notes do not contain.

- **Em dashes.** Varun used them in the hand posts (47 across 13), and they are not an AI tell on their own. He still wants them avoided in new drafts. Use a comma, a full stop, a colon or parentheses instead. Never chain several in one paragraph.
