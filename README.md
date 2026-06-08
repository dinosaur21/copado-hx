# copado-hx

> One natural language instruction. Full Salesforce DevOps pipeline. Zero browser tabs.

`copado-hx` is an open-source CLI + agentic orchestrator that wraps the Copado REST API with an AI layer powered by Claude. A developer types a single sentence; the agent reads `SKILL.md`, selects the matching playbook, plans and executes the full pipeline, and enforces human-in-the-loop guardrails before any UAT or PROD operation.

---

## Demo

```bash
$ copado-hx "My lead scoring feature is ready. Run the tests and if they pass, deploy to UAT."

◈ Agentic Orchestrator — reading SKILL.md and planning workflow...
  Matched playbook: Full Story Delivery
  Executing 8 commands with guardrails active

❯ copado-hx auth status
  ✓ Authenticated as vaani@varada.dev | Org: Varada-Technologies-Prod

❯ copado-hx story show
  User Story: US-2041 — Lead Scoring Engine v2
  Pipeline: Varada Main | Branch: feature/lead-scoring-v2

❯ copado-hx ai ask --agent build "What metadata should I commit for US-2041?"
◈ Build Agent →
  Detected 3 modified components — all within story scope. Safe to commit.

❯ copado-hx commit --message "feat: lead scoring v2 with dynamic thresholds"
  ✓ Committed | commitId: cmt_9f3a2b1c

❯ copado-hx test run --suite smoke-suite-UAT
❯ copado-hx test status --execution exec_7d4e8f2a --watch
  ✓ All 4 tests passed | Duration: 24s | Coverage: 94%

◈ Agent checkpoint — human approval required
  All smoke tests passed. Shall I promote US-2041 to UAT? [yes/no]: yes
  ✓ Approved — proceeding...

❯ copado-hx promote --env UAT --validate
  ✓ Validation passed | US-2041 promoted to UAT

✓ Workflow complete — zero browser tabs opened
```

---

## Architecture

```
copado-hx/
├── SKILL.md                  ← Declarative playbooks + guardrail rules (agent instruction set)
├── main.py                   ← CLI entry point
├── agents/
│   ├── orchestrator.py       ← Reads SKILL.md, matches intent → playbook, executes plan
│   └── agents.py             ← Build / Test / Release / Security / Review agent implementations
├── cli/
│   └── copado_client.py      ← Copado REST API wrapper + command dispatcher
└── config/
    └── config.yml.example    ← Org alias, pipeline, guardrail env list
```

### Key design decisions

**SKILL.md as the instruction set.** Playbooks are defined declaratively in Markdown, not code. Adding or modifying a workflow requires editing one file, no deployment. The orchestrator re-reads it on every session start.

**LLM-generated execution plan.** The orchestrator sends the matched playbook + live session context to Claude, which returns a JSON command plan. This means the agent adapts to the current story state rather than running a hardcoded sequence.

**Mandatory guardrails.** Any `promote` targeting a guardrail environment (UAT, STAGING, PROD) is blocked until the user explicitly types `yes`. All approvals are appended to `.copado-hx/audit.log` with timestamp and user.

**Specialised agents.** Each agent (build, test, release, security, review) has a focused system prompt. Agents share session context injected by the orchestrator but do not share conversation history — keeping each invocation clean and deterministic.

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/varani/copado-hx
cd copado-hx

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp config/config.yml.example .copado-hx/config.yml
# Edit: org_alias, copado token, pipeline name

# 4. Set env vars
export ANTHROPIC_API_KEY=sk-ant-...
export COPADO_TOKEN=your-copado-bearer-token

# 5. Run
python main.py "Run smoke tests and deploy to UAT if they pass"
```

---

## Supported Playbooks

| Playbook | Trigger Phrases | Guardrail |
|---|---|---|
| Full Story Delivery | "ready to deploy", "ship it", "tests and deploy" | Before promote |
| Investigate Failed Deployment | "why did it fail", "fix the error", "deployment failed" | None |
| Generate & Run Tests | "write tests", "generate CRT", "add test for" | Before test run |

New playbooks can be added to `SKILL.md` with no code changes.

---

## Agents

| Agent | Capability |
|---|---|
| `build` | Metadata scope analysis, commit safety check, Apex fix suggestions |
| `test` | CRT QWord script generation, coverage estimation |
| `release` | Root cause analysis on failed jobs, release note generation |
| `security` | SOQL injection, hardcoded credentials, FLS/CRUD gap detection |
| `review` | Bulkification, exception handling, test quality review |

---

## Requirements

- Python 3.11+
- Copado Enterprise (API access)
- Anthropic API key
- Salesforce org with Copado pipeline configured

---

## Why

Salesforce DevOps with Copado involves a lot of context-switching: check the story, find the right job, open the test runner, navigate to the promotion screen. `copado-hx` collapses that into a terminal command. The agent handles the orchestration; you handle the decisions.

---

## License

MIT
