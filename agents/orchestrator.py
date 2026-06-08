"""
orchestrator.py - copado-hx Agentic Orchestrator Core

Reads SKILL.md, matches user intent to a playbook, builds a command plan,
executes it step-by-step, and enforces guardrails before UAT/PROD operations.
"""

import os
import json
import time
import datetime
import anthropic
from pathlib import Path
from typing import Optional

SKILL_FILE = Path(__file__).parent.parent / "SKILL.md"
AUDIT_LOG  = Path(".copado-hx/audit.log")
GUARDRAIL_ENVS = {"UAT", "STAGING", "PROD"}

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


# ---------------------------------------------------------------------------
# SKILL.md loader
# ---------------------------------------------------------------------------

def load_skill() -> str:
    if not SKILL_FILE.exists():
        raise FileNotFoundError(f"SKILL.md not found at {SKILL_FILE}")
    return SKILL_FILE.read_text()


# ---------------------------------------------------------------------------
# Session context - injected into every agent call
# ---------------------------------------------------------------------------

def build_session_context() -> dict:
    """
    Gathers live context from the Copado org and local git state.
    In production this calls the Copado REST API; here we show the interface.
    """
    from cli.copado_client import CopadoClient
    c = CopadoClient()
    return {
        "active_story":   c.get_active_story(),
        "last_jobs":      c.get_recent_jobs(limit=3),
        "branch":         c.get_current_branch(),
        "modified_files": c.get_modified_files(),
        "timestamp":      datetime.datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Intent → Playbook matching
# ---------------------------------------------------------------------------

PLAYBOOK_TRIGGERS = {
    "full-deploy":   ["ready to deploy", "run tests and deploy", "deliver story", "ship it", "deploy to uat", "tests and deploy"],
    "debug-deploy":  ["why did it fail", "deployment failed", "fix the error", "broken pipeline", "fix it"],
    "gen-test":      ["write tests", "generate crt", "test coverage", "add test for", "write a crt"],
}

def match_playbook(user_input: str) -> Optional[str]:
    lowered = user_input.lower()
    for playbook_id, triggers in PLAYBOOK_TRIGGERS.items():
        if any(t in lowered for t in triggers):
            return playbook_id
    return None


# ---------------------------------------------------------------------------
# Orchestrator - main entry point
# ---------------------------------------------------------------------------

class Orchestrator:
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.skill   = load_skill()
        self.context = {}

    def log(self, msg: str, color: str = "white"):
        colors = {"green": "\033[92m", "blue": "\033[94m", "yellow": "\033[93m",
                  "red": "\033[91m", "dim": "\033[2m", "purple": "\033[95m",
                  "orange": "\033[38;5;214m", "white": "\033[0m"}
        reset = "\033[0m"
        print(f"{colors.get(color, '')}{msg}{reset}")

    def run(self, user_input: str):
        self.log("◈ Agentic Orchestrator - reading SKILL.md and planning workflow...", "purple")

        # Load session context
        try:
            self.context = build_session_context()
        except Exception as e:
            self.log(f"  ⚠ Context load partial: {e}", "dim")
            self.context = {}

        # Match playbook
        playbook_id = match_playbook(user_input)
        if not playbook_id:
            # Fall back to LLM-based routing
            playbook_id = self._llm_route(user_input)

        self.log(f"  Matched playbook: {playbook_id}", "dim")

        # Generate command plan via LLM
        plan = self._plan(user_input, playbook_id)
        self.log(f"  Executing {len(plan['steps'])} commands with guardrails active", "dim")

        # Execute
        self._execute(plan)

    def _llm_route(self, user_input: str) -> str:
        """Ask Claude to pick the best playbook when keyword matching fails."""
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=64,
            system=(
                "You are a routing agent. Given a developer's instruction and the SKILL.md below, "
                "return ONLY the playbook id: one of [full-deploy, debug-deploy, gen-test].\n\n"
                f"SKILL.md:\n{self.skill}"
            ),
            messages=[{"role": "user", "content": user_input}],
        )
        return resp.content[0].text.strip().lower()

    def _plan(self, user_input: str, playbook_id: str) -> dict:
        """Ask Claude to produce a concrete command plan for the matched playbook."""
        system_prompt = f"""
You are copado-hx orchestrator. Using the playbook '{playbook_id}' in the SKILL.md below,
produce a JSON execution plan for the developer's instruction.

Return ONLY valid JSON, no markdown fences.
Schema:
{{
  "playbook": "<id>",
  "steps": [
    {{"cmd": "<copado-hx command or null>", "needs_approval": false, "env": null}},
    ...
  ]
}}

Set needs_approval=true and env="<ENV>" on any promote step targeting a guardrail environment.

SKILL.md:
{self.skill}

Session context:
{json.dumps(self.context, indent=2)}
"""
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_input}],
        )
        raw = resp.content[0].text.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(raw)

    def _execute(self, plan: dict):
        from cli.copado_client import CopadoClient
        client_copado = CopadoClient()

        for step in plan["steps"]:
            cmd = step.get("cmd")
            if not cmd:
                continue

            # Guardrail check
            if step.get("needs_approval") and step.get("env", "").upper() in GUARDRAIL_ENVS:
                self._guardrail(cmd, step["env"])

            # Run command
            self.log(f"\n❯ {cmd}", "white")
            result = client_copado.run(cmd)
            self._print_result(result)

        self.log("\n✓ Workflow complete - zero browser tabs opened", "green")

    def _guardrail(self, cmd: str, env: str):
        """Block execution and require explicit typed approval."""
        self.log("\n◈ Agent checkpoint - human approval required", "orange")
        self.log(f"  Next action: {cmd}", "dim")
        self.log(f"  Target environment: {env}", "yellow")
        ans = input("  Proceed? [yes/no]: ").strip().lower()
        if ans != "yes":
            self.log("  ✗ Cancelled by user.", "red")
            raise SystemExit(0)
        self._audit(cmd, env)
        self.log("  ✓ Approved - proceeding...", "green")

    def _audit(self, cmd: str, env: str):
        AUDIT_LOG.parent.mkdir(exist_ok=True)
        with open(AUDIT_LOG, "a") as f:
            entry = {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "env": env,
                "cmd": cmd,
                "approved_by": os.environ.get("USER", "unknown"),
            }
            f.write(json.dumps(entry) + "\n")

    def _print_result(self, result: dict):
        status = result.get("status", "")
        if status == "success":
            self.log(f"  ✓ {result.get('message', 'OK')}", "green")
        elif status == "error":
            self.log(f"  ✗ {result.get('message', 'Error')}", "red")
        else:
            self.log(f"  {result.get('message', '')}", "dim")
