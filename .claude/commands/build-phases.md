---
description: Build every remaining PRD phase end to end (plan, implement, review, fix, PR), stopping only when a human is needed
argument-hint: [prd path; default .claude/PRPs/prds/newsletter-content-machine.prd.md]
---

# Build Phases Loop

Drive the remaining phases of the PRD to PRs with no hand-holding. The PRD's **Implementation Phases** table is the only state: `pending | in-progress | complete`. Re-running this command resumes wherever it stopped.

PRD: `$ARGUMENTS` (default `.claude/PRPs/prds/newsletter-content-machine.prd.md`).

## Loop

Repeat until no phase is `pending` or `in-progress`:

1. **Sync.** `git fetch origin main`. If an `in-progress` phase has an open, unmerged PR, go to **Stop: merge**. Otherwise branch from latest `origin/main`: `git checkout -B feat/phase-<N>-<slug> origin/main`.
2. **Pick the phase.** The lowest-numbered `pending` phase whose **Depends** are all `complete`. Run phases strictly one after another, never in parallel. Set it to `in-progress`.
3. **Run the phase in a fresh `general-purpose` Agent (foreground)**, so this session's context stays small. Brief it with: the PRD path, the phase number, the repo rules in `.claude/rules/`, and the steps below. Wait for its report; you own the result.
   1. `/ecc:prp-plan` for the phase. Write the plan, link it in the PRD table.
   2. `/ecc:prp-implement` on that plan: tests first (RED then GREEN), then lint, mypy, tests, coverage >= 80%. Fix failures at the root, never skip or weaken tests.
   3. `/code-review high`. Fix every CRITICAL/HIGH finding and every cheap correct finding, re-run checks, and call `ReportFindings` again with outcomes. Repeat at most **3 rounds**.
   4. Commit (conventional commits), push the feature branch, open a PR to `main` that mirrors the Phase 1 PR layout (Summary, Test plan with unchecked items for anything not run, Notes).
4. **Stop: merge.** Tell the user the PR link, what was built, and which checklist items they must do by hand. Do **not** merge. When the user says it is merged: `git checkout main && git pull`, set the phase `complete`, archive the plan to `plans/completed/`, commit that on a small `docs:` branch (or include it in the next phase's branch), then continue the loop.

## Stop and ask a human ONLY when

- **Merge:** after every phase PR (policy chosen by Varun: open PR, then stop).
- **Missing access:** `ANTHROPIC_API_KEY`, Gmail OAuth/label, YouTube access, LangSmith/Managed Deep Agents credentials, or Substack. Build and test everything possible offline with fakes, record the unrun live checks as unchecked PR items, and say exactly what is needed.
- **Voice or product judgement:** anything that changes how the newsletter *sounds* or what it publishes, for example the writer/critic prompts in Phase 3 or the draft format in Phase 4. Show the artifact and wait for approval. Never edit `voice/style-guide.md` or `voice/samples/` without approval.
- **Irreversible or outward-facing:** deploying (Phase 5), scheduling cron, posting to Substack, sending email, deleting data. Prepare it, show the exact command, wait.
- **Stuck:** validation still failing after 3 fix attempts, 3 review rounds with unresolved CRITICAL/HIGH findings, or a requirement the PRD leaves ambiguous in a way that changes the design. Say what you tried and give a recommendation.

Never stop for: routine decisions with an obvious default, formatting, naming, or choosing between equivalent libraries. Decide, note it in the PR, move on.

## Rules

- One phase per branch and per PR. Never push to `main`. Never merge.
- Follow `.claude/rules/ecc/common/*` (immutability, small files, fail-fast validation, no secrets).
- Keep Phase 1 conventions: `src/newsletter_machine/`, frozen dataclasses, `ConfigError`, module loggers, `@pytest.mark.live` for API tests, models only via config.
- Scope discipline: build only the current phase's scope (the PRD's **Phase Details**). Note out-of-scope ideas in the PR, do not build them.
- Final message of every stop must be short: where it stopped, why, exactly what the user needs to do, and the command to resume (`/build-phases`).
