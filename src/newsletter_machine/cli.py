"""Command-line entry point: ``newsletter-machine hello``."""

import argparse
import logging
import os
import sys
from typing import Any

from newsletter_machine.agent import build_hello_agent
from newsletter_machine.config import ConfigError, load_settings

logger = logging.getLogger(__name__)

DEFAULT_QUESTION = (
    "List the hand-written posts, read two of them, and name three concrete traits of "
    "Varun's voice with a short quote for each."
)
DEFAULT_LOG_LEVEL = "INFO"
EXIT_ERROR = 1
EXIT_CONFIG = 2


def extract_text(content: Any) -> str:
    """Flatten Anthropic message content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="newsletter-machine")
    sub = parser.add_subparsers(dest="command", required=True)
    hello = sub.add_parser("hello", help="Smoke-test the agent against the voice corpus")
    hello.add_argument("--question", default=DEFAULT_QUESTION)
    return parser


def _configure_logging() -> None:
    """Configure logging after .env is loaded; fall back to INFO on an unknown LOG_LEVEL."""
    requested = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
    level = requested if requested in logging.getLevelNamesMapping() else DEFAULT_LOG_LEVEL
    logging.basicConfig(level=level)
    if level != requested:
        logger.warning("Unknown LOG_LEVEL %r, using %s", requested, DEFAULT_LOG_LEVEL)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    _configure_logging()
    try:
        agent = build_hello_agent(settings)
        result = agent.invoke({"messages": [{"role": "user", "content": args.question}]})
    except Exception as exc:  # network/API failures surface as many types
        logger.debug("Agent run failed", exc_info=True)  # traceback with LOG_LEVEL=DEBUG
        print(f"Agent run failed: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(extract_text(result["messages"][-1].content))
    return 0
