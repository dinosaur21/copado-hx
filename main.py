#!/usr/bin/env python3
"""
main.py — copado-hx CLI entry point

Usage:
  copado-hx "<natural language instruction>"
  copado-hx auth status
  copado-hx ai ask --agent <agent-id> "<instruction>"
  copado-hx commit --message "<msg>"
  copado-hx test run --suite <suite>
  copado-hx promote --env UAT [--validate]
  copado-hx status
  copado-hx story show
"""

import sys
import argparse
from agents.orchestrator import Orchestrator
from agents.agents import dispatch
from cli.copado_client import CopadoClient


def cmd_ai_ask(args):
    """copado-hx ai ask --agent <id> "<instruction>" """
    client  = CopadoClient()
    context = {}
    try:
        context["active_story"]   = client.get_active_story()
        context["modified_files"] = client.get_modified_files()
        context["last_jobs"]      = client.get_recent_jobs()
    except Exception:
        pass
    result = dispatch(args.agent, args.instruction, context)
    print(f"\033[95m◈ {args.agent.title()} Agent →\033[0m")
    for line in result.splitlines():
        print(f"  {line}")


def cmd_direct(cmd_parts):
    """Run a direct copado-hx command (non-agentic)."""
    client = CopadoClient()
    result = client.run(" ".join(["copado-hx"] + cmd_parts))
    if result["status"] == "success":
        print(f"\033[92m✓ {result['message']}\033[0m")
    else:
        print(f"\033[91m✗ {result['message']}\033[0m")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    args = sys.argv[1:]

    # Natural language mode — single quoted string
    if len(args) == 1 and not args[0].startswith("-"):
        orch = Orchestrator()
        orch.run(args[0])
        return

    # ai ask --agent <id> "<instruction>"
    if args[:2] == ["ai", "ask"]:
        parser = argparse.ArgumentParser()
        parser.add_argument("ai")
        parser.add_argument("ask")
        parser.add_argument("--agent", required=True)
        parser.add_argument("instruction")
        parsed = parser.parse_args(args)
        cmd_ai_ask(parsed)
        return

    # All other direct commands
    cmd_direct(args)


if __name__ == "__main__":
    main()
