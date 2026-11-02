---
title: "Day 43: Claude Skills - Why Structured AI Workflows Beat Prompt Engineering"
subtitle: ""
date: 2025-11-01
url: https://varunbhanot.substack.com/p/day-43-claude-skills-why-structured
words: 1396
era: hand
---

# Day 43: Claude Skills - Why Structured AI Workflows Beat Prompt Engineering

Here’s the uncomfortable truth: Most teams treat AI like a smart search box. Throw in context, craft clever prompts, hope for consistent results.

This works for demos. It breaks in production.

I’ve spent the last year building agentic AI systems at Deutsche Telekom. The teams that succeed don’t have better prompts. They have better structure.

## The Problem: We’re Having Expensive Conversations

Typical AI workflow: Explain what you want, paste examples, iterate until something works.

The limitations:

* Every conversation starts from scratch
* Best practices disappear after the chat ends
* No way to systematically improve
* Context overload as tasks get complex

You’re not building systems. You’re having expensive conversations.

## Claude Skills: Workflows as Code

So here’s a different approach: What if instead of telling AI *what* to do every time, you just documented *how* work should be done?

That’s Claude Skills.

They’re not prompts. They’re workflow documentation that Claude reads and executes. Think of them as markdown files that define your processes—version controlled, shareable, improvable.

A skill might document:

* Your document creation standards and approval workflow
* How to validate data analysis with specific statistical tests
* Research methodology with source verification steps
* Meeting preparation checklist and follow-up procedures
* Content creation pipeline from ideation to distribution

When Claude starts a session with skills loaded, it reads the relevant ones and follows those workflows. You codify the process once, Claude executes it consistently.

The development example I’m about to show proves this works. But skills aren’t just for code—they work for any knowledge work where you have repeatable processes.

[![](https://substackcdn.com/image/fetch/$s_!tneL!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F7975c97a-8d5b-4029-9143-0bb54522b437_1024x1024.png)](https://substackcdn.com/image/fetch/$s_!tneL!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F7975c97a-8d5b-4029-9143-0bb54522b437_1024x1024.png)

## Superpowers: Proof of Concept

Jesse Vincent built Superpowers—a plugin for Claude Code that auto-loads skill libraries at session start.

It includes skills for collaboration, debugging, testing. But here’s what matters: these skills orchestrate each other.

Let me show you.

## The Demo: Building a Todo App

Someone asks Claude: “make a todo list app”

**Brainstorming skill activates**: Claude asks clarifying questions instead of jumping to code. CLI or web? What features? Here is how terminal looks like

```
Now, let me understand what you’re envisioning. What type of todo list app do you want to build?

 A) Command-line tool - Simple CLI that stores todos locally (fastest to build)
 B) Web application - Browser-based with persistent storage
 C) Desktop GUI - Native app with local storage
 D) Mobile app - iOS/Android application
 E) Something else - Tell me what you’re thinking
```

**Git worktree skill takes over**: Initializes repo, creates isolated worktree, proper .gitignore. Standard best practices, executed automatically.

```
Now, before moving to implementation planning, I notice this directory isn’t a git repo yet. According to your version control rules, I need to ask: Should I initialize a git repository here?

 This will let us:
 - Track all changes systematically
 - Follow the git worktree workflow for isolated implementation
 - Commit incrementally as we build

> Yes! 

 Bash(git init)
 Initialized empty Git repository in /Users/jesse/tmp/new-tool/.git/

 Perfect! Now let me set up a git worktree for the implementation.

 I’m using the Using Git Worktrees skill to set up an isolated workspace.

 Read(file_path: “/Users/jesse/.claude/plugins/cache/superpowers/skills/collaboration/using-git-worktrees/SKILL.md”)
 Read 216 lines

 Bash(ls -d .worktrees 2>/dev/null || ls -d worktrees 2>/dev/null || echo “NONE”)
 NONE

 Bash(grep -i “worktree.*director” CLAUDE.md 2>/dev/null || echo “NO_CLAUDE_MD”)
 NO_CLAUDE_MD

 No worktree directory found. Where should I create worktrees?

 1. .worktrees/ (project-local, hidden)
 2. ~/.clank-worktrees/new-tool/ (global location)
```

**TDD skill guides implementation**: For each feature—write tests first, watch them fail, implement minimal code, commit. Pure TDD.

```
Response:
 Task 1 Implementation Complete

 What I Implemented

 I successfully implemented Task 1 from the plan: Set up bats testing framework. This included:

 1. Created package.json with bats testing configuration
 2. Installed bats testing framework via npm
 3. Created tests/todo.bats with initial test file including setup/teardown functions
 4. Created minimal todo script with bash shebang
 5. Made todo script executable using chmod +x
 6. Updated .gitignore to exclude node_modules/

 Test-Driven Development Process Followed

 I strictly followed TDD methodology:
 1. Wrote the test first (tests/todo.bats)
 2. Ran test and confirmed it failed (todo script didn’t exist)
 3. Implemented minimal code (created todo script)
 4. Ran test and confirmed it passed
 5. Committed the work

 Test Results

 All tests pass:
 1..1
 ok 1 todo script exists and is executable

 Test output is pristine - no errors, warnings, or extraneous output.
```

**Code review skill validates**: After each feature, Claude dispatches a code reviewer subagent. Systematic review against requirements.

Result: Fully functional CLI app with comprehensive tests, clean git history, code reviews.

**The key: Claude wasn’t given these instructions in the prompt. It read the skills and orchestrated them automatically.**

## Why This Works

**Codified best practices**: TDD, git workflows, code review—captured as reusable skills.

**Zero cognitive load**: Claude doesn’t reinvent. You don’t re-explain. The skill defines it, Claude executes it.

**Systematic improvement**: Better approach discovered? Update the skill file. Everyone benefits.

**Organizational memory**: Knowledge persists beyond sessions. New team members get instant access.

**Composition**: Skills invoke other skills. Brainstorming triggers git worktrees, which enables TDD. Complex workflows from simple components.

This is workflow engineering vs. prompt engineering.

## Beyond Code: Skills for Everything

The development example is powerful because it’s measurable—tests pass or fail. But I’ve been thinking about how this pattern applies everywhere.

**Content creation**: Your brand guidelines, editorial workflow, SEO checklist, distribution process—one skill captures your entire content SOP.

**Research processes**: Source verification standards, cross-referencing methodology, how to structure findings, citation requirements. Every research task follows the same quality bar.

**Data analysis**: Validation steps, which statistical tests to run, visualization standards, how to interpret edge cases. Consistent analysis across your team.

**Meeting management**: Agenda structure, pre-read requirements, decision framework, follow-up template. Every meeting runs the same systematic way.

**Document generation**: Corporate formatting, required sections, review checkpoints, approval workflow. Professional docs every time.

The pattern is universal: If you have a repeatable process, you can capture it as a skill. If Claude can follow markdown instructions, it can execute your workflow.

[![](https://substackcdn.com/image/fetch/$s_!9hZP!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F8d1839f3-d450-42e0-b390-095a6a229ed7_1200x500.gif)](https://substackcdn.com/image/fetch/$s_!9hZP!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F8d1839f3-d450-42e0-b390-095a6a229ed7_1200x500.gif)

## What This Means for How We Build AI Systems

This isn’t specific to Claude or coding tools. It’s about how we should architect any AI system that does knowledge work.

Most organizations are building prompt libraries—collections of clever prompts that sometimes work. What they actually need: workflow libraries that work consistently.

Ask yourself:

* Do you have documented workflows or just prompt templates?
* Can you systematically improve how AI works across your organization?
* When someone discovers a better approach, does the whole team benefit?
* Are your AI interactions repeatable and auditable?

The skills pattern makes all of this possible.

For technical leaders: Stop asking “what can AI do?” Start asking “how should AI work within our processes?”

Whether it’s coding, content creation, analysis, or documentation—teams with structured workflows ship to production. Teams without them stay stuck running endless pilots.

## Three Things to Remember

**Skills turn AI from conversation partner to process executor**. You define how work should be done once, not every single time you need it done.

**Structure beats cleverness in production systems**. Clever prompts are fragile. They work until they don’t. Structured workflows are robust. They work predictably.

**Build workflow libraries, not prompt collections**. Document your best practices as skills. Put them in version control. Improve them systematically as you learn.

The todo app example proves this works at small scale. Now imagine it at enterprise scale—every department with their workflow libraries, all systematically improving, all composable.

## Beyond Development: Skills for Any Knowledge Work

The development example is powerful because it’s measurable—tests pass or fail. But the pattern works everywhere.

**Content creation skill**: Your brand voice guidelines, approval workflows, SEO checklist, distribution process. One skill file captures your entire content SOP.

**Research skill**: Define how to verify sources, cross-reference claims, structure findings, cite properly. Every research task follows the same quality bar.

**Data analysis skill**: Validation steps, statistical tests to run, visualization standards, interpretation guidelines. Consistent analysis across teams.

**Meeting prep skill**: Agenda structure, pre-read requirements, decision framework, follow-up template. Every meeting runs the same way.

**Document creation skill**: Corporate formatting, section requirements, review process, approval chain. Professional documents every time.

The pattern is universal: If you have a repeatable process, you can capture it as a skill. If Claude can follow markdown instructions, it can execute your workflow.
