"""
agents.py — copado-hx AI Agent Implementations

Each agent is a focused Claude invocation with a specific system prompt.
Agents share session context injected by the orchestrator.
"""

import anthropic

client = anthropic.Anthropic()
MODEL  = "claude-sonnet-4-20250514"


def _ask(agent_id: str, system: str, user: str, max_tokens: int = 1024) -> str:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip()


# ---------------------------------------------------------------------------
# Build Agent
# ---------------------------------------------------------------------------

BUILD_SYSTEM = """
You are the copado-hx Build Agent.
Your responsibilities:
1. Analyse modified Salesforce metadata components vs the active user story scope.
2. Identify which files are safe to commit (in-scope) vs which would violate scope.
3. Diagnose Apex compile errors and suggest/apply minimal safe fixes.
4. Never modify files outside the active user story metadata scope.

Output format: concise bullet points. Be specific about file names and line numbers.
When suggesting a code fix, show before/after for the specific line only.
"""

def build_agent(instruction: str, context: dict) -> str:
    user = f"""
Session context:
- Active story: {context.get('active_story', {}).get('name', 'unknown')}
- Modified files: {context.get('modified_files', [])}
- Story metadata scope: {context.get('active_story', {}).get('metadataScope', [])}

Instruction: {instruction}
"""
    return _ask("build", BUILD_SYSTEM, user)


# ---------------------------------------------------------------------------
# Test Agent
# ---------------------------------------------------------------------------

TEST_SYSTEM = """
You are the copado-hx Test Agent.
Your responsibilities:
1. Generate CRT QWord test scripts for Salesforce Apex classes.
2. Cover positive paths, negative paths, bulk scenarios (200 records), and governor limits.
3. Ensure generated tests will push code coverage above the 75% threshold.
4. Return test scenarios as a structured list: Scenario N: <name> — <description>.

Always include a bulk test scenario. Always include a negative/error path scenario.
"""

def test_agent(instruction: str, context: dict) -> str:
    user = f"""
Target class: {context.get('active_story', {}).get('targetClass', 'unknown')}
Current coverage: {context.get('active_story', {}).get('coverage', 'unknown')}%
Story: {context.get('active_story', {}).get('name', 'unknown')}

Instruction: {instruction}
"""
    return _ask("test", TEST_SYSTEM, user)


# ---------------------------------------------------------------------------
# Release Agent
# ---------------------------------------------------------------------------

RELEASE_SYSTEM = """
You are the copado-hx Release Agent.
Your responsibilities:
1. Perform root cause analysis on failed Copado job executions from raw error logs.
2. Generate clean, concise release notes from commit history and story metadata.
3. Identify breaking changes and flag them explicitly.
4. Release notes format: bullet list — feature changes, fixes, coverage delta, breaking changes.
"""

def release_agent(instruction: str, context: dict, error_log: str = "") -> str:
    user = f"""
Story: {context.get('active_story', {}).get('name', 'unknown')}
Last jobs: {context.get('last_jobs', [])}
Error log (if any): {error_log or 'N/A'}

Instruction: {instruction}
"""
    return _ask("release", RELEASE_SYSTEM, user)


# ---------------------------------------------------------------------------
# Security Agent
# ---------------------------------------------------------------------------

SECURITY_SYSTEM = """
You are the copado-hx Security Agent.
Scan Salesforce Apex code and metadata for:
1. Hardcoded credentials, tokens, or API keys.
2. SOQL/SOSL injection vulnerabilities (user input in queries without binding).
3. Missing CRUD/FLS checks before DML or queries.
4. Exposed @future, @AuraEnabled, or REST endpoints without auth checks.

Output as structured findings: SEVERITY | FILE | LINE | ISSUE | REMEDIATION.
"""

def security_agent(instruction: str, context: dict, code_snippet: str = "") -> str:
    user = f"""
Modified files: {context.get('modified_files', [])}
Code to review:
{code_snippet or '(no snippet provided — analyse based on file names)'}

Instruction: {instruction}
"""
    return _ask("security", SECURITY_SYSTEM, user, max_tokens=2048)


# ---------------------------------------------------------------------------
# Review Agent
# ---------------------------------------------------------------------------

REVIEW_SYSTEM = """
You are the copado-hx Code Review Agent.
Review Salesforce Apex code for:
1. Bulkification — are all DML and queries outside loops?
2. Exception handling — are all callouts and DML wrapped?
3. Test coverage quality — are tests asserting behaviour, not just coverage lines?
4. Naming conventions and code clarity.

Output structured review comments: FILE | LINE | TYPE | COMMENT.
"""

def review_agent(instruction: str, context: dict, code_snippet: str = "") -> str:
    user = f"""
Code to review:
{code_snippet or '(analyse from context)'}

Story context: {context.get('active_story', {}).get('name', 'unknown')}
Instruction: {instruction}
"""
    return _ask("review", REVIEW_SYSTEM, user, max_tokens=2048)


# ---------------------------------------------------------------------------
# Agent dispatcher
# ---------------------------------------------------------------------------

AGENT_MAP = {
    "build":    build_agent,
    "test":     test_agent,
    "release":  release_agent,
    "security": security_agent,
    "review":   review_agent,
}

def dispatch(agent_id: str, instruction: str, context: dict, **kwargs) -> str:
    fn = AGENT_MAP.get(agent_id)
    if not fn:
        raise ValueError(f"Unknown agent: {agent_id}. Available: {list(AGENT_MAP.keys())}")
    return fn(instruction, context, **kwargs)
