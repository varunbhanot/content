"""Managed Deep Agents identity: only callers with a LangSmith API key for this workspace
may run the deployed agent (the schedule runs inside the workspace)."""

from managed_deepagents import auth, define_identity

identity = define_identity(auth=auth.langsmith_api_key())
