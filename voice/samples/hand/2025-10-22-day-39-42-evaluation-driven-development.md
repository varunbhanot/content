---
title: "Day 39-42 : Evaluation Driven Development. Moving your AI Apps out of POC Purgatory"
subtitle: ""
date: 2025-10-22
url: https://varunbhanot.substack.com/p/day-39-42-evaluation-driven-development
words: 774
era: hand
---

# Day 39-42 : Evaluation Driven Development. Moving your AI Apps out of POC Purgatory

[![](https://substackcdn.com/image/fetch/$s_!_RFf!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5476d8cb-d6dc-4611-91ad-6b805edf1a4b_1024x1024.jpeg)](https://substackcdn.com/image/fetch/$s_!_RFf!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5476d8cb-d6dc-4611-91ad-6b805edf1a4b_1024x1024.jpeg)

**Here’s the uncomfortable truth:** Most LLM applications never make it past the demo stage. An engineer quickly wires up ChatGPT with LlamaIndex, runs a proof-of-concept, and suddenly leadership’s lighting up Slack—”We can answer any question from our documentation!”

Then reality arrives. The responses are inconsistent. Latency spikes under real usage. The model hallucinates confidently incorrect answers. That breakthrough demo quietly fades into the backlog, another casualty of what the industry now calls “POC purgatory”—the limbo between a working prototype and a production-ready system

We’ve watched this pattern repeat across countless organizations. The teams that escape share a common strategy: they adopted **evaluation-driven development (EDD)** from day one. Instead of treating testing and monitoring as afterthoughts, they make rigorous evaluation the foundation of every decision—from initial architecture to production deployment. This mindset shift transforms how LLM systems are built, turning unpredictable experiments into reliable products.

## **What makes LLM applications fundamentally different?**

**Unstructured data chaos.** LLMs ingest messy, real-world information that doesn’t fit traditional schemas—documents, conversations, emails—all with unlimited variations in format and structure.

**Nondeterministic outputs.** The same prompt can yield different responses. Worse, user inputs are never truly identical—subtle phrasing changes or contextual shifts produce wildly divergent results.

​This combination—unpredictable inputs feeding unpredictable systems—breaks traditional software development paradigms. You can’t debug nondeterminism the way you’d fix a null pointer exception.

​**The solution:** **Evaluation-driven development.** This systematic approach uses continuous testing and assessment to guide every stage of your LLM lifecycle. It’s not revolutionary—ML and data teams have relied on rigorous evaluation cycles for decades. We’re adapting proven methodologies to address LLM-specific challenges: measuring output quality, tracking consistency, and catching regressions before they reach users.

## How is AI-Powered Software Actually That Different from Traditional Software?

When building LLM applications, the fundamental question is: **Should your SDLC change?** The answer is yes—and the differences are substantial.​

![](https://substackcdn.com/image/fetch/$s_!xlUB!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fdf7c6267-f4c9-41d5-b027-f577ab8c9ee8_2358x648.png)

Tradition Vs AI Powered SDLC

## Looking At Your Data and Rapid Iteration

Logging and iteration aren’t just debugging tools; they’re the heart of building reliable LLM apps. **You can’t fix what you can’t see.**

A typical cycle looks like this :

[![AI-generated image](https://substackcdn.com/image/fetch/$s_!TdRZ!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F70e641e4-22af-4960-acce-442f8f99c518_1472x704.jpeg "AI-generated image")](https://substackcdn.com/image/fetch/$s_!TdRZ!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F70e641e4-22af-4960-acce-442f8f99c518_1472x704.jpeg)

EDD Cycle

## Rethinking Personal Finance app using EDD

Even though we built a multi-agent apps for personal finance, specifically focussed on credit card statement analysis on [Day 22](https://varunbhanot.substack.com/p/day-22-personal-finance-via-multi). But when I tried to run the system for multiple banks statements, the following errors were found

* Credit vs Debit identification was a problem considering representation is different
* Addition of Credit card payment transaction
* No clear metrics defining data sanity and manual process to verify

#### Architecture: Two-Stage Pipeline

Evaluation framework correctly models the actual data flow:

**PDF File → LlamaParse (text extraction) → LLM (transaction extraction) → Transactions**

#### Automated Metrics (metrics.py)

- Precision: % of extracted transactions that are correct

- Recall: % of actual transactions that were extracted

- F1 Score: Harmonic mean of precision and recall

- Field-level Accuracy: Date, merchant, amount, currency accuracy

#### - Filtering Metrics: Bill payment exclusion accuracy (TP, FP, FN, TN)

#### LLM-as-a-Judge Evaluators (evaluators.py)

Three specialized evaluators using structured output:

a) **TransactionCompletenessEvaluator**

- Validates all transactions were extracted

- Returns: passed (bool), reasoning (str), confidence (float)

b) **PaymentFilteringEvaluator**

- Checks bill payments correctly excluded

- Validates “payment received” patterns filtered

c) **FieldAccuracyEvaluator**

- Assesses individual field correctness

- Returns: score (0-1), details with specific issues

### Dataset Management

**EvaluationExample Model:**

```
  {

    “pdf_path”: str,              # Original PDF location

    “llamaparse_text”: str,       # Text LlamaParse extracted

    “expected_transactions”: list, # Ground truth labels

    “metadata”: dict              # Bank, period, format

  }
```

**Langfuse Integration (langfuse\_config.py)**

- Environment-based configuration (keys from env vars)

- Client initialization with error handling

- Trace/span creation for observability

- Score tracking for metrics over time

### Tracking Metrics

Now with a clear integration and evaluation system, we are able to visualise system performance while building rather than an afterthought. An example of these metrics and how do they look in langfuse

[![](https://substackcdn.com/image/fetch/$s_!EBqK!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3a4fb810-1363-4c22-aaae-9cb0aba0ad5d_916x684.png)](https://substackcdn.com/image/fetch/$s_!EBqK!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F3a4fb810-1363-4c22-aaae-9cb0aba0ad5d_916x684.png)

Metrics for SBI Credit Card Statement

[![](https://substackcdn.com/image/fetch/$s_!XTkB!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5ea8b864-221c-4efc-8150-58f6f8cd0df2_916x684.png)](https://substackcdn.com/image/fetch/$s_!XTkB!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F5ea8b864-221c-4efc-8150-58f6f8cd0df2_916x684.png)

Same system working really well on Axis Credit Card Statement

### Conclusion

Using this approach not only I have been able to build a system that is observable and metric driven but also supports all Indian Credit Card statement formats for a very good accuracy.

The cycle of Pick a PDF → 2. Label it → 3. Run eval → 4. See what’s wrong → 5. Fix it → Repeat has been quickly able to give me confidence of getting the right data extraction and understanding of my system’s behavior well.

Remember, every AI system feature is an experiment till you start measuring it.

Breaking free from POC purgatory demands a fundamental shift in approach. The path forward isn’t paved with the latest frameworks—it’s built on evaluation-driven development embedded within an SDLC designed specifically for LLM systems. By prioritizing observability, testability, and continuous improvement, teams transform what would otherwise remain perpetual prototypes into production-ready AI applications that scale.
