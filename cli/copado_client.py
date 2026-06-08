"""
copado_client.py - Copado REST API wrapper

Wraps the Copado v1 REST API for:
- User Story metadata
- Job Execution status polling
- Commit, Promote, Test Run operations
- Org authentication check
"""

import os
import time
import requests
from typing import Optional

COPADO_BASE = os.environ.get("COPADO_API_URL", "https://api.copado.com/json/v1")
COPADO_TOKEN = os.environ.get("COPADO_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {COPADO_TOKEN}", "Content-Type": "application/json"}

POLL_INTERVAL = 5   # seconds between job status polls
POLL_TIMEOUT  = 600  # 10 minutes max


class CopadoClient:

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def auth_status(self) -> dict:
        r = requests.get(f"{COPADO_BASE}/auth/status", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # User Stories
    # ------------------------------------------------------------------

    def get_active_story(self) -> Optional[dict]:
        """Returns the currently checked-out user story from the local .copado-hx config."""
        config = self._load_local_config()
        story_id = config.get("active_story_id")
        if not story_id:
            return None
        return self.get_story(story_id)

    def get_story(self, story_id: str) -> dict:
        r = requests.get(f"{COPADO_BASE}/userstory/{story_id}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    def commit(self, story_id: str, message: str, files: list[str]) -> dict:
        payload = {
            "userStoryId": story_id,
            "commitMessage": message,
            "files": files,
        }
        r = requests.post(f"{COPADO_BASE}/commit", json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        job = r.json()
        return self._poll_job(job["jobExecutionId"])

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def run_test_suite(self, suite_name: str, story_id: str) -> dict:
        payload = {"suiteName": suite_name, "userStoryId": story_id}
        r = requests.post(f"{COPADO_BASE}/test/run", json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.json()  # returns {executionId, jobId, status}

    def get_test_status(self, execution_id: str) -> dict:
        r = requests.get(f"{COPADO_BASE}/test/status/{execution_id}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_test_results(self, execution_id: str) -> dict:
        r = requests.get(f"{COPADO_BASE}/test/results/{execution_id}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json()

    def watch_test(self, execution_id: str) -> dict:
        """Poll until test execution is terminal; stream scenario results."""
        elapsed = 0
        while elapsed < POLL_TIMEOUT:
            status = self.get_test_status(execution_id)
            for scenario in status.get("completedScenarios", []):
                icon = "✓" if scenario["passed"] else "✗"
                print(f"  [{scenario['elapsed']:05.1f}s] {scenario['name']:<40} {icon}")
            if status["status"] in ("Succeeded", "Failed", "Cancelled"):
                return status
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        raise TimeoutError(f"Test execution {execution_id} timed out after {POLL_TIMEOUT}s")

    # ------------------------------------------------------------------
    # Promotions
    # ------------------------------------------------------------------

    def promote(self, story_id: str, env: str, validate_only: bool = False) -> dict:
        payload = {
            "userStoryId": story_id,
            "targetEnvironment": env,
            "validateOnly": validate_only,
        }
        r = requests.post(f"{COPADO_BASE}/promote", json=payload, headers=HEADERS, timeout=30)
        r.raise_for_status()
        job = r.json()
        return self._poll_job(job["jobExecutionId"])

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def get_recent_jobs(self, limit: int = 3) -> list:
        r = requests.get(f"{COPADO_BASE}/jobs?limit={limit}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json().get("jobs", [])

    def _poll_job(self, job_id: str) -> dict:
        elapsed = 0
        while elapsed < POLL_TIMEOUT:
            r = requests.get(f"{COPADO_BASE}/jobs/{job_id}", headers=HEADERS, timeout=10)
            r.raise_for_status()
            job = r.json()
            if job["status"] in ("Completed Successfully", "Failed", "Cancelled"):
                return job
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
        raise TimeoutError(f"Job {job_id} timed out")

    # ------------------------------------------------------------------
    # Git helpers (local)
    # ------------------------------------------------------------------

    def get_current_branch(self) -> str:
        import subprocess
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else "unknown"

    def get_modified_files(self) -> list[str]:
        import subprocess
        result = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                                capture_output=True, text=True)
        return result.stdout.strip().splitlines() if result.returncode == 0 else []

    # ------------------------------------------------------------------
    # Generic command dispatcher (used by orchestrator)
    # ------------------------------------------------------------------

    def run(self, cmd: str) -> dict:
        """
        Parses a copado-hx CLI command string and dispatches to the right method.
        Returns a normalized {status, message, data} dict.
        """
        parts = cmd.strip().split()
        if len(parts) < 2:
            return {"status": "error", "message": f"Unrecognised command: {cmd}"}

        # copado-hx <verb> <subverb> [flags]
        verb = parts[1] if parts[0] == "copado-hx" else parts[0]
        sub  = parts[2] if len(parts) > 2 else ""

        try:
            if verb == "auth" and sub == "status":
                data = self.auth_status()
                return {"status": "success", "message": f"Authenticated as {data.get('email')}", "data": data}

            elif verb == "status":
                jobs = self.get_recent_jobs(limit=1)
                last = jobs[0] if jobs else {}
                return {"status": "success", "message": f"Last job: {last.get('id')} - {last.get('status')}", "data": last}

            elif verb == "commit":
                msg_idx = parts.index("--message") + 1 if "--message" in parts else -1
                message = parts[msg_idx] if msg_idx > 0 else "feat: automated commit"
                config  = self._load_local_config()
                result  = self.commit(config["active_story_id"], message, self.get_modified_files())
                return {"status": "success", "message": f"Committed | jobId: {result.get('id')}", "data": result}

            elif verb == "test" and sub == "run":
                suite_idx = parts.index("--suite") + 1 if "--suite" in parts else -1
                suite = parts[suite_idx] if suite_idx > 0 else "default"
                config = self._load_local_config()
                result = self.run_test_suite(suite, config["active_story_id"])
                return {"status": "success", "message": f"Test triggered | executionId: {result['executionId']}", "data": result}

            elif verb == "promote":
                env_idx = parts.index("--env") + 1 if "--env" in parts else -1
                env     = parts[env_idx] if env_idx > 0 else "UAT"
                validate = "--validate" in parts
                config  = self._load_local_config()
                result  = self.promote(config["active_story_id"], env, validate)
                return {"status": "success", "message": f"Promoted to {env} | {result.get('status')}", "data": result}

            else:
                return {"status": "error", "message": f"Unknown command verb: {verb}"}

        except requests.HTTPError as e:
            return {"status": "error", "message": f"API error: {e.response.status_code} - {e.response.text}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------

    def _load_local_config(self) -> dict:
        import yaml
        config_path = ".copado-hx/config.yml"
        if os.path.exists(config_path):
            with open(config_path) as f:
                return yaml.safe_load(f)
        return {}
