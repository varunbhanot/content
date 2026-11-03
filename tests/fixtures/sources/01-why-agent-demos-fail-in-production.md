---
url: https://example.com/why-agent-demos-fail
title: Why agent demos fail in production
kind: article
status: ok
note: evals are the moat, not prompts
detail: ''
---

# Why agent demos fail in production

A team shipped a support agent that resolved 80% of tickets in a demo with ten hand-picked
questions. In the first week with real customers it resolved 31%. The prompts had not changed.

The difference was the inputs. Real tickets were longer, mixed two problems in one message and
referred to orders by nicknames. Nobody had written a test set from real tickets.

After the team built an evaluation set of 200 real tickets and ran it on every prompt change,
the resolution rate climbed to 64% in a month. Most fixes were retrieval fixes, not prompt fixes.
