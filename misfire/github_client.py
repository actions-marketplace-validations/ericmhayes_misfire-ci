"""All GitHub REST I/O lives here, isolated so it can be faked in tests.

Nothing else in the package should import `httpx` or hit the network directly.
The shared tools in `tools.py` call into this module; the tools are what
the offline test harness mocks, so these functions are only exercised on the live path.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import httpx

from .log_utils import truncate_logs

_API_ROOT = "https://api.github.com"


@dataclass(frozen=True)
class RunRef:
    """Lightweight reference to a workflow run (used for flaky-history lookups)."""

    run_id: int
    workflow_id: int
    head_sha: str
    conclusion: str  # "success", "failure", "cancelled", ... ("" if still running)
    head_branch: str = ""  # branch the run built; identifies the PR under test


@dataclass
class GitHubClient:
    """Thin wrapper over the GitHub REST API for a single repo."""

    token: str
    repo: str  # "owner/name"
    transport: httpx.BaseTransport | None = None  # test seam; None = real network

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=_API_ROOT,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
            # The logs endpoint 302s to a signed download URL; follow it.
            follow_redirects=True,
            transport=self.transport,
        )

    def _download_run_logs(self, run_id: int) -> str:
        """Fetch and concatenate the raw per-step logs for a run (untruncated).

        The API returns a zip of per-step log files; we concatenate them, each
        prefixed with its path. Kept separate from `fetch_failing_logs` so the
        flaky-history path can search full logs for a test id without the
        model-facing truncation applied.
        """
        with self._client() as client:
            resp = client.get(f"/repos/{self.repo}/actions/runs/{run_id}/logs")
            resp.raise_for_status()
        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        parts = []
        for name in sorted(archive.namelist()):
            if name.endswith("/"):  # directory entry
                continue
            text = archive.read(name).decode("utf-8", errors="replace")
            parts.append(f"===== {name} =====\n{text}")
        return "\n".join(parts)

    def fetch_failing_logs(self, run_id: int) -> str:
        """Return the logs for a workflow run, trimmed for the model.

        Runs the raw logs through `log_utils.truncate_logs` so a multi-MB CI log
        never gets dumped into the model context wholesale (cost
        guardrail). The trimming keeps the failing tail plus the first
        error/traceback block.
        """
        return truncate_logs(self._download_run_logs(run_id))

    def get_run(self, run_id: int) -> RunRef:
        """Fetch metadata (workflow, head SHA, conclusion) for a single run."""
        with self._client() as client:
            resp = client.get(f"/repos/{self.repo}/actions/runs/{run_id}")
            resp.raise_for_status()
        data = resp.json()
        return RunRef(
            run_id=data["id"],
            workflow_id=data["workflow_id"],
            head_sha=data["head_sha"],
            conclusion=data.get("conclusion") or "",
            head_branch=data.get("head_branch") or "",
        )

    def list_workflow_runs(self, workflow_id: int, *, limit: int = 20) -> list[RunRef]:
        """Return the most recent completed runs of a workflow, newest first.

        Bounded by `limit`: flaky detection samples a recent window rather
        than the whole history. Only completed runs are returned so in-flight
        runs don't skew the pass/fail tally.
        """
        with self._client() as client:
            resp = client.get(
                f"/repos/{self.repo}/actions/workflows/{workflow_id}/runs",
                params={"status": "completed", "per_page": limit},
            )
            resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])
        return [
            RunRef(
                run_id=r["id"],
                workflow_id=r["workflow_id"],
                head_sha=r["head_sha"],
                conclusion=r.get("conclusion") or "",
                head_branch=r.get("head_branch") or "",
            )
            for r in runs
        ]

    def fetch_pr_diff(self, pr_number: int) -> str:
        """Return the unified diff for a pull request."""
        with self._client() as client:
            resp = client.get(
                f"/repos/{self.repo}/pulls/{pr_number}",
                headers={"Accept": "application/vnd.github.diff"},
            )
            resp.raise_for_status()
        return resp.text

    def create_pr_comment(self, pr_number: int, body: str) -> str:
        """Post an issue comment on the PR; return the created comment URL."""
        with self._client() as client:
            resp = client.post(
                f"/repos/{self.repo}/issues/{pr_number}/comments",
                json={"body": body},
            )
            resp.raise_for_status()
        return resp.json()["html_url"]

    def upsert_pr_comment(self, pr_number: int, body: str, *, marker: str) -> str:
        """Create or update the single advisory comment on the PR.

        Finds a prior **bot-authored** comment whose body carries `marker` (a
        hidden HTML marker Misfire embeds in every advisory) and PATCHes it;
        otherwise posts a new one. Requiring the author to be a Bot stops a human
        who pastes the marker from hijacking the advisory. Scans paginated
        comments (bounded) so the upsert still finds it on busy PRs. Returns the
        comment URL.
        """
        with self._client() as client:
            existing = None
            page = 1
            while existing is None and page <= 10:
                resp = client.get(
                    f"/repos/{self.repo}/issues/{pr_number}/comments",
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                existing = next(
                    (
                        c
                        for c in batch
                        if marker in (c.get("body") or "")
                        and (c.get("user") or {}).get("type") == "Bot"
                    ),
                    None,
                )
                page += 1
            if existing is not None:
                updated = client.patch(
                    f"/repos/{self.repo}/issues/comments/{existing['id']}",
                    json={"body": body},
                )
                updated.raise_for_status()
                return updated.json()["html_url"]
            created = client.post(
                f"/repos/{self.repo}/issues/{pr_number}/comments",
                json={"body": body},
            )
            created.raise_for_status()
        return created.json()["html_url"]

    def find_pr_number_for_run(self, run_id: int) -> int | None:
        """Resolve the PR a failed run belongs to, via the run's head commit.

        `workflow_run.pull_requests` is empty for PRs from forks, so the Action
        can't rely on it. The commit→pulls endpoint works for fork PRs too (the
        PR lives in the base repo), so we resolve from the run's head SHA.
        Prefers an open PR; returns None when the commit has no associated PR
        (e.g. a direct push to a branch).
        """
        head_sha = self.get_run(run_id).head_sha
        with self._client() as client:
            resp = client.get(f"/repos/{self.repo}/commits/{head_sha}/pulls")
            resp.raise_for_status()
        pulls = resp.json()
        if not pulls:
            return None
        for pr in pulls:
            if pr.get("state") == "open":
                return pr["number"]
        return pulls[0]["number"]
