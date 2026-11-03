"""The Managed Deep Agents project files at the repo root (``mda deploy`` reads them).

``managed_deepagents`` is not installed here (MDA vendors it at build time), so the files are
imported with a stand-in module that records what they declare.
"""

import ast
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from newsletter_machine import hosted

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "schedules" / "weekly_issue.py"
FRIDAY = "5"


@pytest.fixture
def mda(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    module = types.ModuleType("managed_deepagents")
    module.define_deep_agent = lambda **kw: {"kind": "agent", **kw}  # type: ignore[attr-defined]
    module.define_schedule = lambda **kw: {"kind": "schedule", **kw}  # type: ignore[attr-defined]
    module.define_identity = lambda **kw: {"kind": "identity", **kw}  # type: ignore[attr-defined]
    module.auth = types.SimpleNamespace(  # type: ignore[attr-defined]
        langsmith_api_key=lambda: {"mode": "langsmith_api_key"}
    )
    monkeypatch.setitem(sys.modules, "managed_deepagents", module)
    return module


def _load(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"mda_project_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_factory_wires_the_weekly_tool(
    mda: types.ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hosted, "runner_model", lambda: "anthropic:runner")
    definition = _load(ROOT / "agent.py").agent(None)
    assert definition == {
        "kind": "agent",
        "name": "newsletter-machine",
        "model": "anthropic:runner",
        "tools": [hosted.run_weekly_issue],
    }


def test_agent_name_is_an_inline_literal_mda_build_can_read() -> None:
    tree = ast.parse((ROOT / "agent.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    names = [kw.value for c in calls for kw in c.keywords if kw.arg == "name"]
    assert len(names) == 1 and isinstance(names[0], ast.Constant)


def test_identity_requires_a_langsmith_api_key(mda: types.ModuleType) -> None:
    identity = _load(ROOT / "identity.py").identity
    assert identity == {"kind": "identity", "auth": {"mode": "langsmith_api_key"}}


def test_schedule_is_friday_morning_in_a_real_zone(mda: types.ModuleType) -> None:
    schedule = _load(SCHEDULE).schedule
    fields = schedule["cron"].split()
    assert len(fields) == 5 and fields[4] == FRIDAY
    ZoneInfo(schedule["timezone"])
    assert schedule["prompt"].strip()


def test_schedule_uses_static_literals_only() -> None:
    """MDA rejects env vars, calls and computed values in a schedule declaration."""
    tree = ast.parse(SCHEDULE.read_text())
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert all(isinstance(kw.value, ast.Constant) for kw in call.keywords)


def test_instructions_name_the_tool() -> None:
    text = (ROOT / "instructions.md").read_text()
    assert hosted.run_weekly_issue.name in text


def test_pyproject_pins_the_deployed_python() -> None:
    assert 'python-version = "3.13"' in (ROOT / "pyproject.toml").read_text()
