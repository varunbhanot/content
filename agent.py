"""Managed Deep Agents entry (``mda deploy`` reads ``agent`` from this file).

A small runner agent with one tool, ``run_weekly_issue``, which runs the same code as
``newsletter-machine weekly``. The model comes from config (``NM_RUNNER_MODEL``, else
``NM_FAST_MODEL``), so ``agent`` is a factory: ``mda build`` reads the literal ``name``
without calling it.
"""

from typing import Any

from managed_deepagents import define_deep_agent

from newsletter_machine import hosted


def agent(runtime: Any) -> Any:
    return define_deep_agent(
        name="newsletter-machine",
        model=hosted.runner_model(),
        tools=[hosted.run_weekly_issue],
    )
