# SKILL.md — copado-hx Agentic Orchestrator

> This file is the instruction set loaded by the copado-hx agent at runtime.
> It defines playbooks, agent roles, guardrails, and tool bindings.

---

## Overview

`copado-hx` is an open-source CLI + agentic orchestrator for Salesforce DevOps on top of Copado.
A developer issues a **single natural language instruction**; the agent reads this SKILL.md,
selects the matching playbook, plans a command sequence, and executes it — with mandatory
human-in-the-loop checkpoints before UAT/PROD operations.

---

## Agent Roster

| Agent ID       | Role                                      | Invocation                          |
|----------------|-------------------------------------------|-------------------------------------|
| `orchestrator` | Reads SKILL.md, routes to playbook        | Automatic on every session start    |
| `build`        | Metadata analysis, commit, code fixes     | `--agent build`                     |
| `test`         | CRT script generation, test execution     | `--agent test`                      |
| `release`      | Promotion, release notes, error analysis  | `--agent release`                   |
| `security`     | Dependency audit, secret scanning         | `--agent security`                  |
| `review`       | Code review, coverage enforcement         | `--agent review`                    |

---

## Playbooks

### Playbook 1 — Full Story Delivery
**Trigger phrases:** "ready to deploy", "run tests and deploy", "deliver story", "ship it"

**Steps:**
1. `auth status` — verify Copado org authentication
2. `story show` — read active user story metadata scope
3. `build agent` — analyse modified components vs story scope
4. `commit` — commit in-scope components
5. `test run` — execute smoke test suite
6. `test status --watch` — poll until completion
7. **GUARDRAIL** → human approval required before promotion
8. `promote --env UAT --validate` — validation-only deployment
9. `release agent` — generate release notes, attach to story

**Guardrail rule:** Step 7 is non-skippable. Agent MUST pause and surface results before proceeding.

---

### Playbook 2 — Investigate Failed Deployment
**Trigger phrases:** "why did it fail", "deployment failed", "fix the error", "broken pipeline"

**Steps:**
1. `auth status`
2. `status` — surface last failed job ID, pipeline, env
3. `release agent` — root cause analysis on job execution logs
4. `build agent` — apply suggested fix to offending file
5. `commit` — commit fix with descriptive message
6. `promote --env UAT --validate` — re-run validation

**No guardrail** on this playbook (fixing a broken build is low risk; original approval was already given).

---

### Playbook 3 — Generate & Run Tests
**Trigger phrases:** "write tests", "generate CRT", "test coverage", "add test for"

**Steps:**
1. `auth status`
2. `story show` — identify target class and current coverage
3. `test agent` — generate QWord CRT script with scenarios
4. **GUARDRAIL** → human approval before test execution
5. `test run --suite <generated>`
6. `test status --watch`

---

## Guardrail Specification

```
GUARDRAIL_ENVS = ["UAT", "STAGING", "PROD"]

before_promote(env):
  if env in GUARDRAIL_ENVS:
    surface_summary()          # show test results / validation output
    require_explicit_approval() # block until user types 'yes'
    log_approval(user, timestamp, jobId)
  else:
    proceed()
```

- Approval must be a typed `yes` (not a default).
- `no` or timeout (120s) cancels the workflow cleanly.
- All approvals are logged to `.copado-hx/audit.log`.

---

## Tool Bindings

The agent translates natural language to these CLI commands:

```
copado-hx auth status
copado-hx story show [--id <US-XXXX>]
copado-hx commit --message "<msg>"
copado-hx test run --suite <suite-name>
copado-hx test status --execution <id> [--watch]
copado-hx test results --execution <id>
copado-hx promote --env <ENV> [--validate]
copado-hx ai ask --agent <agent-id> "<natural language instruction>"
copado-hx status
```

---

## Context Injection

At session start, the orchestrator automatically loads:
- Active user story (from `copado-hx story show`)
- Last 3 job execution statuses
- Current branch and commit hash
- Modified files (git diff --name-only)

This context is injected into every agent call so agents have full situational awareness
without the developer needing to repeat themselves.

---

## Error Handling

| Error Type               | Agent Response                                              |
|--------------------------|-------------------------------------------------------------|
| Auth failure             | Surface token expiry, prompt `copado-hx auth login`        |
| Apex compile error       | `release agent` root cause → `build agent` fix → re-commit |
| Test failure             | Surface failed scenarios, ask developer before retrying    |
| Governor limit breach    | Flag in output, suggest batch size reduction               |
| Metadata scope violation | Block commit, explain which components are out of scope    |

---

## Configuration

Default config lives at `.copado-hx/config.yml`:

```yaml
org_alias: Varada-Technologies-Prod
default_pipeline: Varada Main
guardrail_envs:
  - UAT
  - STAGING
  - PROD
approval_timeout_seconds: 120
audit_log: .copado-hx/audit.log
agents:
  model: claude-sonnet-4-20250514
  max_tokens: 2048
  skill_file: ./SKILL.md
```

---

## Extension Points

New playbooks can be added to this file. The orchestrator re-reads SKILL.md on every session start,
so no code changes are required — playbook updates are purely declarative.

Custom agents can be registered under `agents/` and referenced in the agent roster above.
