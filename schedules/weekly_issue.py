"""When the weekly run happens: Fridays 07:00 India time.

MDA only accepts literal values here (no env vars or function calls). To move the run, edit
``cron`` (minute hour day-of-month month day-of-week; 5 = Friday) and ``timezone``, keep
``NM_TIMEZONE`` (the issue date) in step, then run ``mda deploy .`` again.
"""

from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 7 * * 5",
    timezone="Asia/Kolkata",
    prompt="Run this week's newsletter issue.",
)
